"""V1MCPAdapter 单元测试"""

import pytest
from unittest.mock import patch, AsyncMock


class TestV1MCPAdapter:
    @patch("core.mcp.mcp_client.mcp_client")
    def test_discover_servers(self, mock_client):
        mock_client.list_servers = AsyncMock(return_value=[])
        mock_client.connect_server = AsyncMock(return_value=True)
        from core.agent_v1_tools.v1_mcp_adapter import V1MCPAdapter
        import asyncio
        adapter = V1MCPAdapter()
        servers = asyncio.run(adapter.discover_servers())
        assert isinstance(servers, list)

    @patch("core.mcp.mcp_client.mcp_client")
    def test_call_tool_retry_success(self, mock_client):
        mock_client.call_tool = AsyncMock(side_effect=[
            Exception("busy"),
            "success result"
        ])
        from core.agent_v1_tools.v1_mcp_adapter import V1MCPAdapter
        import asyncio
        adapter = V1MCPAdapter()
        result = asyncio.run(adapter.call_tool("test-server", "test-tool", {}))
        assert result == "success result"
        assert mock_client.call_tool.call_count == 2

    @patch("core.mcp.mcp_client.mcp_client")
    def test_call_tool_all_fail(self, mock_client):
        mock_client.call_tool = AsyncMock(side_effect=Exception("always fails"))
        from core.agent_v1_tools.v1_mcp_adapter import V1MCPAdapter
        import asyncio
        adapter = V1MCPAdapter()
        result = asyncio.run(adapter.call_tool("test-server", "test-tool", {}))
        assert "❌" in result

    def test_no_v2_imports(self):
        import importlib
        mod = importlib.import_module("core.agent_v1_tools.v1_mcp_adapter")
        with open(mod.__file__) as f:
            src = f.read()
        assert "core.multi_agent_v2" not in src
