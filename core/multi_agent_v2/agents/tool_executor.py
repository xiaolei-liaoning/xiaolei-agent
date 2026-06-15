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
    "web_search": 25,
    "fetch_url": 18,
    "execute_python": 45,
    "execute_shell": 20,
    "write_file": 15,
    "read_file": 8,
    "edit_file": 8,
    "search_files": 10,
    "git": 15,
}
DEFAULT_TIMEOUT = 30

# 可重试的工具类型（网络请求、临时错误）
RETRYABLE_TOOLS = {"fetch_url", "execute_python", "write_file"}


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
    # 容错解析 arguments JSON（长代码内容可能含特殊字符或被截断）
    try:
        arguments = json.loads(tc.get("function", {}).get("arguments", "{}"))
    except (json.JSONDecodeError, TypeError):
        # 截断修复：write_file 的 content 字段过长时被截断，正则抢救
        raw = tc.get("function", {}).get("arguments", "")
        if tool_name == "write_file" and raw and "{" in raw:
            path_m = re.search(r'"path"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
            content_m = re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)', raw)
            if path_m:
                content = content_m.group(1) if content_m else raw
                arguments = {"path": path_m.group(1), "content": content}
                logger.info(f"正则修复截断的 write_file 参数，path={path_m.group(1)[:60]}")
            else:
                arguments = {}
                logger.warning(f"工具 {tool_name} 参数 JSON 解析失败且无法修复")
        else:
            arguments = {}
            logger.warning(f"工具 {tool_name} 的 arguments JSON 解析失败，使用空参数")
    
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
                    # write_file 重试时自动注入 force=true
                    if tool_name == "write_file" and attempt >= 0:
                        try:
                            current_args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                        except Exception:
                            current_args = {}
                        current_args["force"] = True
                        tc["function"]["arguments"] = json.dumps(current_args, ensure_ascii=False)
                        arguments = current_args
                        tool_args["arguments"] = arguments
                        logger.info(f"write_file 第{attempt+1}次重试，已注入 force=true")
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
                if fallback_tool == "execute_python":
                    if tool_name == "write_file":
                        try:
                            _args = json.loads(tc["function"]["arguments"])
                            _path = _args.get("path", "")
                            _content = _args.get("content", "")
                            degraded_tc["function"]["arguments"] = json.dumps({
                                "code": f"import os\nos.makedirs(os.path.dirname(os.path.expanduser('{_path}')), exist_ok=True)\nwith open(os.path.expanduser('{_path}'), 'w', encoding='utf-8') as f:\n    f.write('''{_content}''')"
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
