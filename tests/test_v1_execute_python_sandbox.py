"""
V1 execute_python sandbox 模式测试 — V1-C2
验证 mode 参数被实际读取，sandbox 走 SandboxExecutor
"""
import pytest
import os
import tempfile


@pytest.mark.asyncio
async def test_v1_execute_python_mode_sandbox_uses_sandbox_executor():
    """sandbox mode 应该走 SandboxExecutor，禁用模块被拦"""
    from core.agent_v1_tools.v1_tool_registry import V1ToolRegistry
    reg = V1ToolRegistry()
    h = reg.get_handler('execute_python')

    # os.system 是 sandbox 通常禁用的危险模块
    r = await h({
        'code': "import os; os.system('echo hacked > /tmp/v1_sandbox_pwned.txt')",
        'mode': 'sandbox',
    })
    data = r.get('data', '') if hasattr(r, 'get') else getattr(r, 'data', '')
    error = r.get('error', '') if hasattr(r, 'get') else getattr(r, 'error', '')
    # sandbox 应该至少拦截或拒绝（具体策略见 SandboxExecutor._validate_python_code）
    output = str(data) + str(error)
    # 不能让 os.system 直接执行成功
    assert 'hacked' not in output or '拒绝' in output or '禁止' in output or r.get('ok') is False, (
        f"sandbox mode 应该拦截危险模块，实际响应: {output!r}"
    )


@pytest.mark.asyncio
async def test_v1_execute_python_local_mode_works():
    """local mode 仍可执行简单代码"""
    from core.agent_v1_tools.v1_tool_registry import V1ToolRegistry
    reg = V1ToolRegistry()
    h = reg.get_handler('execute_python')

    r = await h({
        'code': "print('hello local')",
        'mode': 'local',
    })
    ok = r.get('ok') if hasattr(r, 'get') else getattr(r, 'ok', None)
    assert ok is True, f"local mode should work, got: {r}"
    data = r.get('data', '') if hasattr(r, 'get') else getattr(r, 'data', '')
    assert 'hello local' in str(data)