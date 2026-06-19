"""
E2E 测试: 搜索 + 分析 + 报告生成

验证 search → execute_python → write_file 三种工具链式调用
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestSearchAnalyzeReport:
    """搜索 → 分析 → 写报告 e2e 流程"""

    @pytest.mark.asyncio
    async def test_search_tool_is_callable(self, mock_tool_registry):
        """web_search 工具可以被调用"""
        handler = mock_tool_registry.get_handler("web_search")
        assert handler is not None
        result = await handler({"query": "百度热搜"})
        assert result is not None

    @pytest.mark.asyncio
    async def test_write_file_tool_is_callable(self, mock_tool_registry):
        """write_file 工具可以被调用"""
        handler = mock_tool_registry.get_handler("write_file")
        assert handler is not None
        result = await handler({"path": "/tmp/test_report.txt", "content": "测试报告"})
        assert result is not None

    @pytest.mark.asyncio
    async def test_execute_python_tool_is_callable(self, mock_tool_registry):
        """execute_python 工具可以被调用"""
        handler = mock_tool_registry.get_handler("execute_python")
        assert handler is not None
        result = await handler({"code": "print('hello')"})
        assert result is not None

    @pytest.mark.asyncio
    async def test_chain_tools_sequentially(self, mock_tool_registry):
        """链式调用: search → process → write"""
        search_handler = mock_tool_registry.get_handler("web_search")
        python_handler = mock_tool_registry.get_handler("execute_python")
        write_handler = mock_tool_registry.get_handler("write_file")

        # Step 1: 搜索
        search_result = await search_handler({"query": "测试"})
        assert search_result is not None

        # Step 2: 分析
        python_result = await python_handler({"code": "data = 'analysis'"})
        assert python_result is not None

        # Step 3: 写文件
        write_result = await write_handler({"path": "/tmp/report.txt", "content": "report"})
        assert write_result is not None

    def test_all_three_tools_in_registry(self, mock_tool_registry):
        """三种工具都在注册表中"""
        tools = ["web_search", "execute_python", "write_file"]
        for name in tools:
            assert name in mock_tool_registry._tools
