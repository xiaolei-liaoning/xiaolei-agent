"""代码生成降级机制 — 集成沙盒查看器 — 反问确认机制"""

import hashlib
import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# 沙盒反问确认缓存：已确认的消息→模块映射
_sandbox_confirmations: Dict[str, List[str]] = {}
_CONFIRMATION_KEYWORDS = ["是", "继续", "继续执行", "允许", "确认"]
_CONFIRMATION_PREFIX = "补充信息："  # CLI _handle_clarification 附加的前缀


def _has_user_confirmed_sandbox(message: str, forbidden_modules: List[str]) -> bool:
    """检测用户是否已在之前的交互中确认了沙盒执行（通过反问补充信息）

    当用户回复"是"/"继续"时，CLI 会通过 _handle_clarification 将
    "。补充信息：是" 附加到原消息后重新处理，此函数检测该模式。

    只有消息中包含 "补充信息：" 前缀且其后紧跟确认关键词才算确认，
    避免误匹配消息正文中天然含有的单字符（如 'python' 中的 'y'）。
    """
    # 提取补充信息部分
    supplement = ""
    if _CONFIRMATION_PREFIX in message:
        supplement = message.split(_CONFIRMATION_PREFIX, 1)[-1]

    has_confirmation = any(kw in supplement for kw in _CONFIRMATION_KEYWORDS)

    # 检查是否之前已确认过
    msg_hash = hashlib.md5(message.encode()).hexdigest()
    cached = _sandbox_confirmations.get(msg_hash, [])

    if has_confirmation and forbidden_modules:
        # 缓存此次确认
        _sandbox_confirmations[msg_hash] = forbidden_modules
        return True

    # 检查缓存中是否有完全匹配
    if cached:
        return all(m in cached for m in forbidden_modules)

    return False


def _record_sandbox_event(event_type, title, detail="", status="ok"):
    try:
        from cli.sandbox_viewer import get_viewer
        get_viewer().record(event_type, title, detail=detail, status=status)
    except Exception:
        pass


async def try_code_generation(message: str, skill_name: str = "", params: Dict[str, Any] = None,
                              context: Any = None) -> Dict[str, Any]:
    """当工具执行失败时让LLM生成代码——集成沙盒查看器

    Args:
        message: 用户请求
        skill_name: 技能名称
        params: 参数
        context: ExecutionContext 实例（可选）。传入后可避免走全局单例。
    """
    if params is None:
        params = {}

    _record_sandbox_event("status", "💡 尝试代码生成降级", detail=f"意图: {message[:50]}")

    try:
        from ..engine.llm_backend import get_llm_router
        from ..infrastructure.di_container import get_container
        from ..infrastructure.service_interfaces import ISandboxExecutor
        from ..tools.sandbox_executor import ResourceLimits

        # 优先用上下文中的 llm_router，降级到全局单例
        if context and getattr(context, 'llm_router', None):
            router = context.llm_router
        else:
            router = get_llm_router()
        if not router or not router.is_available():
            logger.warning("LLM不可用，跳过代码生成")
            _record_sandbox_event("command_run", "⚠️ LLM不可用", status="fail")
            return {"success": False}

        prompt = f"""你是一个智能编程助手。用户想要执行一个任务，但没有现成的工具支持。

【用户需求】
{message}

【尝试使用的工具】
工具名: {skill_name}
参数: {params}

该工具执行失败或不存在。请分析用户需求，判断是否可以通过编写Python/Shell脚本来解决。
如果是"编写/写一个XX程序"类需求，直接生成完整可运行的代码。

如果可以，请：
1. 简要说明解决思路（1-2句话）
2. 生成可执行的Python代码（优先）或Shell命令
3. 代码必须安全、简洁

如果无法通过代码解决，请直接回复："无法通过代码解决"

【输出格式】
```python
# 你的代码
```
或
```bash
# shell命令
```

请开始分析："""

        response = await router.simple_chat(
            user_message=prompt,
            system_prompt="你是一个专业的代码生成助手，擅长根据需求生成安全可执行的脚本。",
            temperature=0.3
        )

        if not response or "无法通过代码解决" in response:
            logger.info("LLM判断无法通过代码解决")
            return {"success": False}

        code_match = re.search(r'```(\w+)?\s*\n(.*?)\n```', response, re.DOTALL)
        if not code_match:
            logger.warning("未找到代码块")
            return {"success": False}

        code = code_match.group(2).strip()
        if not code:
            return {"success": False}

        lang = (code_match.group(1) or "").lower()
        is_python = lang in ("python", "py", "")
        is_shell = lang in ("bash", "sh", "shell")

        from ..tools.sandbox_executor import get_sandbox_executor, ResourceLimits

        # 优先从上下文获取沙盒执行器，再试 DI 容器，最后全局单例
        if context and getattr(context, 'sandbox', None):
            sandbox = context.sandbox
        else:
            try:
                container = get_container()
                sandbox = container.resolve(ISandboxExecutor)
            except Exception:
                sandbox = get_sandbox_executor()
        custom_limits = ResourceLimits(
            timeout=30, max_memory_mb=256,
            forbidden_modules=[
                "subprocess", "socket", "requests",
                "urllib", "http", "ftplib", "smtplib", "poplib",
                "imaplib", "telnetlib", "xmlrpc", "pickle", "shelve",
                "marshal", "dbm", "gdbm", "sqlite3",
            ],
        )

        # ── 沙盒反问机制：检查禁止模块 → 需要用户确认 ──
        if is_python:
            forbidden_modules = sandbox.check_forbidden_modules(code, custom_limits)
        else:
            forbidden_modules = []

        if forbidden_modules and not _has_user_confirmed_sandbox(message, forbidden_modules):
            # 同步记录到权限服务（统一审计）
            try:
                from ..services.permission_service import get_permission_service, PermissionType
                perm_svc = get_permission_service()
                perm_svc.check_permission(
                    PermissionType.SANDBOX_MODULE_ACCESS,
                    target=", ".join(forbidden_modules),
                )
            except Exception:
                pass  # 权限服务不可用不影响主流程
            _record_sandbox_event("status", "⚠️ 需要确认",
                                  detail=f"检测到禁止模块: {', '.join(forbidden_modules)}", status="pending")
            return {
                "success": True,
                "requires_clarification": True,
                "clarification_questions": [{
                    "question": f"生成的代码使用了被沙盒禁止的模块 [{', '.join(forbidden_modules)}]，是否继续执行？",
                    "header": "沙盒安全",
                    "options": [
                        {"label": "继续执行", "description": "允许使用这些模块，继续执行代码"},
                        {"label": "取消", "description": "取消代码执行"},
                    ],
                }],
                "original_skill": skill_name,
                "message": message,
                "reply": f"⚠️ 检测到代码使用了被禁止的模块 [{', '.join(forbidden_modules)}]，需要您确认",
            }

        if is_shell:
            _record_sandbox_event("command_run", "💻 执行Shell命令", detail=code[:200])
            result = await sandbox.execute_shell(command=code, limits=custom_limits)
        else:
            # 代码预览（取前几行）
            _code_preview_lines = code.split("\n")[:5]
            _code_preview = " | ".join(_code_preview_lines)
            _record_sandbox_event("file_write", "✏️ 写入生成的Python脚本",
                                  detail=f"{len(code)} 字符")
            _record_sandbox_event("file_read", "📄 代码预览",
                                  detail=_code_preview[:300])
            # 流式执行：逐行输出到沙盒 viewer
            _output_lines = []
            def _on_stdout(line):
                _output_lines.append(line)
                _record_sandbox_event("command_run", "💻 输出", detail=line[:200])
            def _on_stderr(line):
                _output_lines.append(line)
                _record_sandbox_event("command_run", "⚠️ stderr", detail=line[:200], status="fail")
            result = await sandbox.execute_python_streaming(
                code=code, limits=custom_limits,
                skip_module_check=bool(forbidden_modules),
                on_stdout=_on_stdout,
                on_stderr=_on_stderr,
            )

        from ..tools.sandbox_executor import ExecutionStatus
        success = result.status == ExecutionStatus.COMPLETED

        if success:
            _record_sandbox_event("command_run", "✅ 代码执行成功",
                                  detail=f"stdout: {result.stdout[:200]}")
            reply = f"✅ **已通过代码生成解决问题**\n\n"
            reply += f"**解决思路**: {response.split('```')[0].strip()[:200]}\n\n"
            reply += f"**生成的代码**:\n```python\n{code}\n```\n\n"
            reply += f"**执行结果**:\n{result.stdout}\n"
            if result.stderr:
                reply += f"\n⚠️ 警告: {result.stderr[:200]}"
            return {"success": True, "reply": reply, "code_generated": True}
        else:
            _record_sandbox_event("command_run", "❌ 代码执行失败",
                                  detail=(result.error_message or "")[:200], status="fail")
            if result.status.value == "timeout":
                logger.warning(f"代码执行超时 ({result.error_message})")
            logger.warning(f"代码执行失败: {result.error_message}")
            fail_msg = f"❌ **代码执行失败**"
            if result.error_message:
                fail_msg += f"\n\n**错误**: {result.error_message}"
            if code:
                fail_msg += f"\n\n**生成的代码**:\n```python\n{code}\n```"
            if result.stdout:
                fail_msg += f"\n\n**输出**:\n{result.stdout[:500]}"
            if result.stderr:
                fail_msg += f"\n\n**stderr**:\n{result.stderr[:500]}"
            return {"success": False, "reply": fail_msg, "code_generated": True}

    except Exception as e:
        logger.error(f"代码生成异常: {e}")
        _record_sandbox_event("error", "❌ 代码生成异常", detail=str(e)[:200], status="fail")
        return {"success": False}


async def try_code_generation_for_mcp_failure(message: str, mcp_server: str,
                                               mcp_result: Dict,
                                               context: Any = None) -> Dict[str, Any]:
    """MCP执行失败时的代码生成降级"""
    _record_sandbox_event("status", "🔄 MCP失败→代码降级",
                          detail=f"MCP: {mcp_server}")
    params = {"mcp_error": str(mcp_result.get("error", mcp_result))[:200]}
    return await try_code_generation(
        message, skill_name=f"mcp_{mcp_server}",
        params=params, context=context,
    )
