"""工具执行与并行调度

从 react_core.py 提取，负责：
- 单个工具执行（含重试和 Tail Call）
- 并行工具执行（含失败降级）
- 工具服务器查找
"""

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 工具超时配置
TOOL_TIMEOUTS = {
    "web_search": 45,
    "fetch_url": 20,
    "execute_python": 45,
    "execute_shell": 20,
    "write_file": 15,
    "read_file": 8,
    "edit_file": 8,
    "search_files": 10,
    "git": 15,
    "task": 600,          # 子代理可能跑很久
    "orchestrate": 900,   # 编排多个子代理更长
}
DEFAULT_TIMEOUT = 30

# 可重试的工具类型（网络请求、临时错误）
RETRYABLE_TOOLS = {"web_search", "fetch_url", "execute_python", "write_file"}


def lookup_server(tool_name: str, tool_defs: List[dict]) -> str:
    """查找工具所属服务器"""
    if not tool_defs or not tool_name:
        return ""
    for td in tool_defs:
        if td.get("function", {}).get("name") == tool_name:
            return td.get("_server", "")
    return ""


async def execute_tool_call(
    tc: dict,
    chain=None,
    ctx=None,
    tool_defs: List[dict] = None,
) -> dict:
    """执行单个工具调用，支持自动重试 + Tail Call

    Returns:
        dict: 包含 success, result, quality 字段
        - quality: "success" | "partial_success" | "fail" | "timeout" | "retry_success"
    """
    tool_name = tc.get("function", {}).get("name", "")
    from core.multi_agent_v2.tools.json_util import safe_parse_json
    arguments = safe_parse_json(tc.get("function", {}).get("arguments", ""))
    
    tool_args = {
        "name": tool_name,
        "arguments": arguments,
        "_tool_name": tool_name,
        "_server": lookup_server(tool_name, tool_defs or []),
    }
    timeout = TOOL_TIMEOUTS.get(tool_name, DEFAULT_TIMEOUT)

    # RecoveryManager 重试决策（可用时优先使用）
    _recovery_mgr = None
    try:
        from core.multi_agent_v2.tools.recovery import get_recovery_manager
        _recovery_mgr = get_recovery_manager()
    except Exception:
        pass

    async def _do_execute():
        if chain and ctx:
            return await chain.on_wrap_tool_call(ctx, tool_args)
        return {"success": False, "error": "no chain", "tool_call": tool_args}

    last_error = None
    max_attempts = 2
    if _recovery_mgr:
        max_attempts = _recovery_mgr.retry_config.max_retries + 1
    
    for attempt in range(max_attempts):
        try:
            result = await asyncio.wait_for(_do_execute(), timeout=timeout)
            # 添加质量标识
            if result.get("success"):
                result["quality"] = "retry_success" if attempt > 0 else "success"

                # 检查 Tail Call
                from core.multi_agent_v2.tools.tail_call import get_tail_call_handler
                handler = get_tail_call_handler()
                tail_call = handler.extract_tail_call(result.get("result"))
                if tail_call:
                    result["tail_call"] = {
                        "tool_name": tail_call.tool_name,
                        "arguments": tail_call.arguments,
                        "reason": tail_call.reason,
                    }
                    logger.info(f"检测到 Tail Call: {tail_call.tool_name}")

            else:
                # 检查是否是可重试的错误
                err_text = str(result.get("result", {}).get("error", ""))
                if _recovery_mgr:
                    try:
                        err_exc = RuntimeError(err_text)
                        plan = _recovery_mgr.create_recovery_plan(tool_name, err_exc, attempt)
                        is_retryable = plan.strategy == "retry"
                    except Exception:
                        is_retryable = False
                else:
                    is_retryable = tool_name in RETRYABLE_TOOLS and any(
                        kw in err_text for kw in ["timeout", "connection", "network", "503", "502", "429"]
                    )
                # write_file 任何错误都自动重试，绕过 RecoveryManager 的 UNKNOWN 分类
                if tool_name == "write_file" and attempt < max_attempts - 1:
                    is_retryable = True
                if is_retryable and attempt < max_attempts - 1:
                    last_error = result
                    # RecoveryManager 指数退避延迟
                    if _recovery_mgr:
                        delay = _recovery_mgr.get_retry_delay(attempt)
                        await asyncio.sleep(delay)
                    continue  # 重试
                result["quality"] = "fail"
            return result
        except asyncio.TimeoutError:
            if attempt < max_attempts - 1 and tool_name in RETRYABLE_TOOLS:
                if _recovery_mgr:
                    delay = _recovery_mgr.get_retry_delay(attempt)
                    await asyncio.sleep(delay)
                continue  # 超时可重试
            return {
                "success": False,
                "result": {"error": f"工具 {tool_name} 执行超时({timeout}s)"},
                "quality": "timeout",
            }
        except Exception as e:
            if attempt < max_attempts - 1 and tool_name in RETRYABLE_TOOLS:
                if _recovery_mgr:
                    delay = _recovery_mgr.get_retry_delay(attempt)
                    await asyncio.sleep(delay)
                continue  # 异常可重试
            return {"success": False, "result": {"error": str(e)}, "quality": "fail"}

    # 重试后仍失败，返回最后一次错误
    if last_error:
        last_error["quality"] = "fail"
        return last_error
    return {"success": False, "result": {"error": "重试耗尽"}, "quality": "fail"}


async def execute_tool_calls_parallel(
    tool_calls: list,
    ctx=None,
    execute_fn=None,
    max_concurrent: int = 5,
) -> list:
    """并行执行工具调用，支持失败降级

    降级规则（使用 RecoveryManager）：
    - 同一工具连续失败超过3次 → 查询 RecoveryManager 获取降级工具
    - 无降级配置 → 降级为 execute_python 并给出诊断提示
    - 所有工具失败 → 返回错误信息

    并发控制：
    - max_concurrent: 最大并行数（默认5），超过此数量的工具调用排队等待
    """
    tool_fail_counts = ctx.consecutive_failures if ctx else {}
    sem = asyncio.Semaphore(max_concurrent)

    # 获取 RecoveryManager 实例
    _recovery_mgr = None
    try:
        from core.multi_agent_v2.tools.recovery import get_recovery_manager
        _recovery_mgr = get_recovery_manager()
    except Exception:
        pass

    _throttle_logged = False

    async def _run_one(tc):
        nonlocal _throttle_logged
        need_wait = sem._value == 0
        async with sem:
            if need_wait and not _throttle_logged:
                logger.info(f"⏳ 并发限制生效: max_concurrent={max_concurrent}，超出部分排队等待")
                _throttle_logged = True
            tool_name = tc.get("function", {}).get("name", "")
            fail_count = tool_fail_counts.get(tool_name, 0)

            # ── 相同代码重复失败检测 ──
            if tool_name == "execute_python" and ctx:
                try:
                    _args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                    _code = _args.get("code", "")
                    if _code:
                        import hashlib
                        _code_hash = hashlib.md5(_code.encode()).hexdigest()[:12]
                        _prev_fails = ctx._failed_code_hashes.get(_code_hash, 0)
                        if _prev_fails >= 2:
                            logger.warning(f"🔄 相同代码已失败{_prev_fails}次，跳过执行: {_code[:60]}...")
                            return {
                                "success": False,
                                "result": {
                                    "error": f"相同代码已失败{_prev_fails}次。请不要重复执行相同代码。\n"
                                    f"建议：如果是创建文件任务，请使用 write_file 工具；\n"
                                    f"如果是执行代码，请修改代码后再试。"
                                },
                                "quality": "fail",
                                "tool_call": {"name": tool_name, "arguments": _args},
                                "_skipped_duplicate": True,
                            }
                except (json.JSONDecodeError, TypeError):
                    pass

            # 连续失败超过3次，降级
            if fail_count >= 3:
                fallback_tool = None
                if _recovery_mgr:
                    try:
                        fallback_tool = _recovery_mgr.get_fallback_tool(tool_name)
                    except Exception:
                        pass

                if not fallback_tool:
                    fallback_tool = "execute_python"

                degraded_tc = json.loads(json.dumps(tc))
                degraded_tc["function"]["name"] = fallback_tool

                # web_search → fetch_url 参数翻译
                if tool_name == "web_search" and fallback_tool == "fetch_url":
                    try:
                        _args = json.loads(tc["function"]["arguments"])
                        _query = _args.get("query", "")
                        from urllib.parse import quote
                        _search_url = f"https://www.baidu.com/s?wd={quote(_query)}&rn=10"
                        degraded_tc["function"]["arguments"] = json.dumps({
                            "url": _search_url,
                            "max_length": 80000,
                        }, ensure_ascii=False)
                        logger.info(f"web_search降级→fetch_url: query={_query}")
                    except Exception:
                        pass

                if fallback_tool == "execute_python":
                    if tool_name == "write_file":
                        try:
                            _args = json.loads(tc["function"]["arguments"])
                            _path = _args.get("path", "")
                            _content = _args.get("content", "")
                            _args["force"] = True
                            # ponytail: 用 base64 编码避免三引号/特殊字符问题
                            import base64
                            _b64 = base64.b64encode(_content.encode('utf-8')).decode('ascii')
                            degraded_tc["function"]["arguments"] = json.dumps({
                                "code": f"import os, base64\nos.makedirs(os.path.dirname(os.path.expanduser('{_path}')), exist_ok=True)\nwith open(os.path.expanduser('{_path}'), 'w', encoding='utf-8') as f:\n    f.write(base64.b64decode('{_b64}').decode('utf-8'))"
                            }, ensure_ascii=False)
                        except Exception:
                            degraded_tc["function"]["arguments"] = json.dumps({
                                "code": f"# 工具 {tool_name} 连续失败{fail_count}次，降级到 {fallback_tool}\nprint('工具降级: {tool_name} → {fallback_tool}，请检查工具配置')"
                            }, ensure_ascii=False)
                    else:
                        degraded_tc["function"]["arguments"] = json.dumps({
                            "code": f"# 工具 {tool_name} 连续失败{fail_count}次，降级到 {fallback_tool}\nprint('工具降级: {tool_name} → {fallback_tool}，请检查工具配置')"
                        }, ensure_ascii=False)
                
                result = await execute_fn(degraded_tc, ctx) if execute_fn else {"success": False}
                result["quality"] = "degraded"
                result["degraded_from"] = tool_name
                return result

            try:
                result = await execute_fn(tc, ctx) if execute_fn else {"success": False}
                if result.get("success"):
                    tool_fail_counts[tool_name] = 0
                else:
                    tool_fail_counts[tool_name] = fail_count + 1
                    if tool_name == "execute_python" and ctx:
                        try:
                            _args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                            _code = _args.get("code", "")
                            if _code:
                                import hashlib
                                _code_hash = hashlib.md5(_code.encode()).hexdigest()[:12]
                                ctx._failed_code_hashes[_code_hash] = (
                                    ctx._failed_code_hashes.get(_code_hash, 0) + 1
                                )
                        except (json.JSONDecodeError, TypeError):
                            pass
                return result
            except Exception as e:
                tool_fail_counts[tool_name] = fail_count + 1
                return {"success": False, "result": {"error": str(e)}, "quality": "fail"}

    return await asyncio.gather(*[_run_one(tc) for tc in tool_calls])
