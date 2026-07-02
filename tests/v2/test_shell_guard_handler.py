"""
ShellGuard handler 测试 — V2-C3 fix
"""
import pytest
from core.multi_agent_v2.tools.tool_registry import get_tool_registry


@pytest.mark.asyncio
async def test_execute_shell_blocks_rmrf():
    """rm -rf / 危险命令应该被 ShellGuard 拦截"""
    reg = get_tool_registry()
    h = reg.get_handler('execute_shell')
    r = await h({'command': 'rm -rf /'})
    text = ""
    if isinstance(r, dict):
        rc = r.get("result", {}).get("content", [])
        if rc:
            text = rc[0].get("text", "")
    assert "执行失败" in text or "blocked" in text.lower() or "安全策略阻止" in text, (
        f"危险命令应被拦截，实际响应: {text!r}"
    )


@pytest.mark.asyncio
async def test_execute_shell_shellguard_called_correctly():
    """ShellGuard.scan 返回 ScanResult 应该用 .safe 字段，不该抛 AttributeError"""
    reg = get_tool_registry()
    h = reg.get_handler('execute_shell')
    # 这个命令不应该让 handler 抛异常
    r = await h({'command': 'echo hello', 'mode': 'sandbox'})
    assert isinstance(r, dict)
    # 至少不应该是 None / exception
    assert r is not None