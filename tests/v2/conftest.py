"""
V2 架构测试公共 fixtures

提供 mock LLM、mock ToolRegistry、RunContext 等测试基础设施。
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict, List, Optional

import pytest

from core.multi_agent_v2.agents.middleware import (
    BaseMiddleware,
    HookResult,
    MiddlewareChain,
    PlanStep,
    RunContext,
)


# ════════════════════════════════════════════════════════════════
# RunContext Fixtures
# ════════════════════════════════════════════════════════════════


@pytest.fixture
def base_ctx():
    """创建一个基础 RunContext，不绑定 agent/chain"""
    return RunContext(task_description="测试任务", max_iterations=10)


@pytest.fixture
def ctx_with_tool_results(base_ctx):
    """带有模拟工具结果的 RunContext"""
    base_ctx.tool_results = [
        {"success": True, "result": "ok", "tool_call": {"name": "web_search", "arguments": {"query": "test"}}},
        {"success": False, "error": "timeout", "tool_call": {"name": "fetch_url", "arguments": {"url": "http://x"}}},
    ]
    base_ctx.react_depth = 2
    base_ctx.iteration = 2
    return base_ctx


# ════════════════════════════════════════════════════════════════
# Middleware Fixtures
# ════════════════════════════════════════════════════════════════


class PassthroughMiddleware(BaseMiddleware):
    """透传中间件，不做任何操作，用于测试链顺序"""
    HOOKS = ()

    def __init__(self, name: str = "passthrough"):
        super().__init__()
        self.name = name
        self.calls: List[str] = []

    async def on_start(self, ctx):
        self.calls.append("on_start")
        return None

    async def on_think_start(self, ctx):
        self.calls.append("on_think_start")
        return None

    async def on_think_end(self, ctx):
        self.calls.append("on_think_end")
        return None

    async def on_tool_end(self, ctx):
        self.calls.append("on_tool_end")
        return None

    async def on_finish(self, ctx):
        self.calls.append("on_finish")
        return None


class InterruptMiddleware(BaseMiddleware):
    """会在指定钩子中断执行的中间件"""
    HOOKS = ()

    def __init__(self, interrupt_hook: str = "on_think_end"):
        super().__init__()
        self.interrupt_hook = interrupt_hook

    async def on_think_end(self, ctx):
        if self.interrupt_hook == "on_think_end":
            ctx.interrupted = True
            ctx.final_answer = "中断测试"
            return HookResult(jump_to="end", reason="测试中断")
        return None

    async def on_start(self, ctx):
        if self.interrupt_hook == "on_start":
            ctx.interrupted = True
            return HookResult(jump_to="end", reason="测试中断")
        return None


@pytest.fixture
def passthrough_mw():
    return PassthroughMiddleware()


@pytest.fixture
def interrupt_mw():
    return InterruptMiddleware()


@pytest.fixture
def chain_with_passthrough():
    """包含 3 个透传中间件的链，用于测试执行顺序"""
    chain = MiddlewareChain()
    chain.add(PassthroughMiddleware("first"))
    chain.add(PassthroughMiddleware("second"))
    chain.add(PassthroughMiddleware("third"))
    return chain


# ════════════════════════════════════════════════════════════════
# Mock LLM
# ════════════════════════════════════════════════════════════════


class MockLLMRouter:
    """Mock LLM Router，返回预设回复"""

    def __init__(self, responses: List[str] = None):
        self.responses = responses or ["测试回复"]
        self._call_count = 0
        self.is_available_return = True

    def is_available(self) -> bool:
        return self.is_available_return

    async def chat(self, messages, **kwargs):
        idx = min(self._call_count, len(self.responses) - 1)
        self._call_count += 1
        return self.responses[idx]


@pytest.fixture
def mock_llm_router():
    return MockLLMRouter()


# ════════════════════════════════════════════════════════════════
# Mock ToolRegistry
# ════════════════════════════════════════════════════════════════


def make_mock_tool_def(name: str, description: str = "", domains=None):
    """创建一个 mock ToolDefinition"""
    td = MagicMock()
    td.name = name
    td.description = description
    td.server = "__builtin__"
    td.tool_name = name
    td.tags = []
    td.domains = domains or set()
    td.parameters = {"type": "object", "properties": {}}
    td.handler = AsyncMock(return_value={"result": f"{name} 执行成功"})
    return td


@pytest.fixture
def mock_tool_registry():
    """Mock ToolRegistry，预置常用工具"""
    reg = MagicMock()
    reg._tools = {}

    tools = {
        "web_search": make_mock_tool_def("web_search", "搜索"),
        "fetch_url": make_mock_tool_def("fetch_url", "抓取网页"),
        "write_file": make_mock_tool_def("write_file", "写文件"),
        "execute_python": make_mock_tool_def("execute_python", "执行Python"),
        "execute_shell": make_mock_tool_def("execute_shell", "执行Shell"),
    }
    reg._tools = tools
    reg._mcp_tools = {}

    async def mock_discover_all():
        pass

    reg.discover_all = mock_discover_all

    def mock_get_handler(name):
        td = reg._tools.get(name)
        if td and td.handler:
            return td.handler
        return None

    reg.get_handler = mock_get_handler

    async def mock_get_tools_for_task(task, max_tools=20, allowed=None, disallowed=None):
        result = list(reg._tools.values())[:max_tools]
        return result

    reg.get_tools_for_task = mock_get_tools_for_task

    return reg
