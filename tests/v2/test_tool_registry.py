"""
ToolRegistry 单元测试

覆盖:
  - _SANDBOX_TOOL_DEFS 包含所有核心工具（含 web_search）
  - _HANDLER_MAP 与 ToolDefinition handler 一致性
  - get_handler 返回正确的 handler
  - get_tools_for_task 筛选逻辑
"""
import pytest
from unittest.mock import MagicMock, patch


class TestSandboxToolDefs:
    """测试 _SANDBOX_TOOL_DEFS 包含所有核心工具"""

    def test_core_tools_present(self):
        from core.multi_agent_v2.tools.tool_registry import _SANDBOX_TOOL_DEFS
        names = {td.name for td in _SANDBOX_TOOL_DEFS}
        required = {"write_file", "execute_python", "execute_shell", "fetch_url", "web_search"}
        assert required.issubset(names), f"缺失: {required - names}"

    def test_web_search_has_handler(self):
        from core.multi_agent_v2.tools.tool_registry import _SANDBOX_TOOL_DEFS
        ws = [td for td in _SANDBOX_TOOL_DEFS if td.name == "web_search"]
        assert len(ws) == 1, "web_search 应有且仅有一个 ToolDefinition"
        assert ws[0].handler is not None, "web_search 的 handler 不应为 None"

    def test_sandbox_count_minimum(self):
        """至少有 9 个内置工具"""
        from core.multi_agent_v2.tools.tool_registry import _SANDBOX_TOOL_DEFS
        assert len(_SANDBOX_TOOL_DEFS) >= 9


class TestHandlerMap:
    """测试 _HANDLER_MAP 一致性"""

    def test_web_search_handler_exists(self):
        from core.multi_agent_v2.tools.tool_registry import _HANDLER_MAP
        assert "web_search" in _HANDLER_MAP
        assert callable(_HANDLER_MAP["web_search"])

    def test_handler_map_no_search(self):
        """旧的 'search' key 不应在 _HANDLER_MAP 中"""
        from core.multi_agent_v2.tools.tool_registry import _HANDLER_MAP
        assert "search" not in _HANDLER_MAP


class TestGetHandler:
    """测试 ToolRegistry.get_handler"""

    def test_get_handler_returns_callable(self, mock_tool_registry):
        handler = mock_tool_registry.get_handler("web_search")
        assert handler is not None
        assert callable(handler)

    def test_get_handler_unknown_returns_none(self, mock_tool_registry):
        handler = mock_tool_registry.get_handler("nonexistent_tool")
        assert handler is None


class TestGetToolsForTask:
    """测试 ToolRegistry.get_tools_for_task"""

    @pytest.mark.asyncio
    async def test_returns_list(self, mock_tool_registry):
        tools = await mock_tool_registry.get_tools_for_task("搜索百度热搜")
        assert isinstance(tools, list)
        assert len(tools) > 0

    @pytest.mark.asyncio
    async def test_max_tools_limit(self, mock_tool_registry):
        tools = await mock_tool_registry.get_tools_for_task("任意任务", max_tools=2)
        assert len(tools) <= 2

    @pytest.mark.asyncio
    async def test_disallowed_tools_param_accepted(self, mock_tool_registry):
        """验证 disallowed 参数被接受且不报错"""
        tools = await mock_tool_registry.get_tools_for_task(
            "任务", disallowed=["web_search"]
        )
        assert isinstance(tools, list)
