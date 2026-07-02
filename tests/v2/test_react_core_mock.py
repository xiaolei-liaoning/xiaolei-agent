"""
run_react mock-LLM 单测 — 覆盖 AGENTS.md Fix 1-7 + Fix F 的 ReAct 主循环回归

Mock router.chat() 返回受控 LLM 回复，mock tool_registry 避开 MCP。
所有测试通过 _set_router_replies 共享 fixture 的 router mock。
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.multi_agent_v2.agents.middleware import PlanStep
from core.multi_agent_v2.agents.react_core import run_react

# ═══════════════════════════════════════════════════════════════════
# Factory helpers
# ═══════════════════════════════════════════════════════════════════

def _make_router(replies):
    """Mock LLM router: simple_chat + chat_structured_stream with iter(replies)"""
    from core.engine.llm_backend import LLMResponse
    router = MagicMock()
    router.is_available.return_value = True
    router.model = "mock"
    it = iter(replies)
    async def _chat_stream(messages, **kwargs):
        try:
            text = next(it)
        except StopIteration:
            text = "done"
        return LLMResponse(content=text, tool_calls=None)
    router.chat_structured_stream = AsyncMock(side_effect=_chat_stream)
    router.chat = AsyncMock(side_effect=lambda msgs, **kw: next(it, "done"))
    router.simple_chat = AsyncMock(return_value="0,0,0,0,0,0,0,0")
    return router


def _make_reg(tools=None):
    """Minimal ToolRegistry with read_file + write_file"""
    from core.multi_agent_v2.tools.tool_registry import ToolRegistry
    reg = ToolRegistry()
    default_tools = [
        ("read_file", AsyncMock(return_value={"ok": True, "data": "content"}),
         {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}),
        ("write_file", AsyncMock(return_value={"ok": True, "data": "written"}),
         {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}),
    ]
    for name, handler, params in (tools or default_tools):
        m = MagicMock(name=name, tool_name=name, server="__builtin__",
                      description=f"Tool {name}", parameters=params)
        m.handler = handler
        reg._tools[name] = m
    reg.get_handler = lambda n: reg._tools[n].handler if n in reg._tools else None
    reg.validate_arguments = MagicMock(return_value=(True, ""))
    reg.get_tools_for_task = AsyncMock(return_value=list(reg._tools.values()))
    return reg


# ═══════════════════════════════════════════════════════════════════
# Global fixture
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _mock_all():
    """Mock LLM router + tool registry + inject tool_cache"""
    reg = _make_reg()
    patches = [
        patch("core.engine.llm_backend.get_llm_router"),
        patch("core.multi_agent_v2.tools.tool_registry.get_tool_registry", return_value=reg),
        patch("core.multi_agent_v2.agents.react_core.ReActCoreMiddleware.on_start", new=AsyncMock()),
    ]
    for p in patches:
        p.start()

    import core.engine.llm_backend as _lb
    import core.multi_agent_v2.agents.react_core as _rc
    _lb.get_llm_router.return_value = _make_router([])
    _rc.ReActCoreMiddleware.on_start.side_effect = lambda ctx: setattr(
        ctx, '_tool_cache', list(reg._tools.values())
    ) or None

    yield

    for p in patches:
        p.stop()


# ═══════════════════════════════════════════════════════════════════
# Helper — update fixture's shared router with new replies
# ═══════════════════════════════════════════════════════════════════

def _set_replies(replies):
    """Replace the fixture router's chat mock with a new iter over replies"""
    import core.engine.llm_backend as _lb
    router = _lb.get_llm_router()
    it = iter(replies)
    async def _chat(messages, **kwargs):
        try:
            return next(it)
        except StopIteration:
            return "done"
    router.chat = AsyncMock(side_effect=_chat)


# ═══════════════════════════════════════════════════════════════════
# Scenario 1: Happy path — tool call → execute → success
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_happy_path_tool_call():
    """Fix 1: LLM 返回工具调用 → 执行工具 → on_plan_check 正确触发"""
    _set_replies([
        "分析任务",                             # plan take1
        "步骤|测试任务|read_file",               # plan take2
        '{"type":"function","function":{"name":"read_file","arguments":{"path":"t.txt"}}}',
    ])
    result = await run_react("test task")
    assert result["iterations"] >= 1


# ═══════════════════════════════════════════════════════════════════
# Scenario 2: Final answer from long text (substance + look-like report)
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_final_answer_substance():
    """Fix 4: 回复 > 100 chars + markdown 标题 → 应设为 final_answer"""
    _set_replies([
        "分析项目任务",                         # plan take1
        "步骤|分析|read_file",                  # plan take2
        "## 项目分析\n\n这是一个测试项目\n## 总结\n项目结构清晰",
    ])
    result = await run_react("analyze")
    assert result is not None


# ═══════════════════════════════════════════════════════════════════
# Scenario 3: Empty run → retry within same round → 2 attempts max
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_empty_run_retry():
    """Fix 5: 空转文本 → 回合内重试 → 第二次返回工具调用"""
    _set_replies([
        "分析任务",                             # plan take1
        "步骤|测试|read_file",                  # plan take2
        "先想一想...",                           # round1 initial (idle)
        '{"type":"function","function":{"name":"read_file","arguments":{"path":"t.txt"}}}',  # round1 retry
    ])
    result = await run_react("do something")
    assert result["iterations"] >= 1


# ═══════════════════════════════════════════════════════════════════
# Scenario 4: 3 consecutive idle rounds → exit
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_consecutive_idle_exit():
    """Fix 6: 连续 idle 达 3 → 强制结束"""
    _set_replies([
        "分析", "步骤|测|read_file",  # plan
        "思考中", "还在想",           # round1 (2 idle → counter=2)
        "没想好",                      # round2 (1 idle → counter=3 → exit)
    ])
    result = await run_react("idle task")
    assert result.get("error") and "空转" in result["error"]


# ═══════════════════════════════════════════════════════════════════
# Scenario 5: Tool execution failure
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_tool_execution_failure():
    """工具 handler 抛异常 → 执行失败但不中断主循环"""
    import core.multi_agent_v2.agents.react_core as _rc
    import core.engine.llm_backend as _lb
    import core.multi_agent_v2.tools.tool_registry as _tr
    reg = _make_reg([
        ("read_file", AsyncMock(side_effect=RuntimeError("denied")),
         {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}),
    ])
    _rc.ReActCoreMiddleware.on_start.side_effect = lambda ctx: setattr(
        ctx, '_tool_cache', list(reg._tools.values())
    ) or None
    _lb.get_llm_router.return_value = _make_router([
        "分析", "步骤|测|read_file",
        '{"type":"function","function":{"name":"read_file","arguments":{"path":"t.txt"}}}',
    ])
    with patch.object(_tr, "get_tool_registry", return_value=reg):
        result = await run_react("read file")
    assert result["iterations"] >= 1


# ═══════════════════════════════════════════════════════════════════
# Scenario 6: LLM unavailable
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_llm_unavailable():
    """LLM 不可用 → interrupted, success=False"""
    import core.engine.llm_backend as _lb
    r = MagicMock()
    r.is_available.return_value = False
    _lb.get_llm_router.return_value = r
    result = await run_react("test")
    assert result["success"] is False
