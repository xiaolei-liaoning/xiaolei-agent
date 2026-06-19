"""
ReActCore 单元测试

覆盖:
  - format_tool_result 成功/失败格式化
  - get_error_suggestion 错误建议映射
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestFormatToolResult:
    """测试工具结果格式化"""

    def test_success_format(self):
        from core.multi_agent_v2.agents.tool_evaluator import format_tool_result
        result = format_tool_result(
            "web_search", {"result": {"content": [{"text": "搜索结果"}]}}, True, {"query": "test"}
        )
        assert "[web_search] OK" in result
        assert "搜索结果" in result

    def test_failure_format(self):
        from core.multi_agent_v2.agents.tool_evaluator import format_tool_result
        result = format_tool_result(
            "execute_python", {"error": "SyntaxError: invalid syntax"}, False, {"code": "bad"}
        )
        assert "[execute_python] FAIL" in result
        assert "SyntaxError" in result

    def test_long_content_truncation(self):
        from core.multi_agent_v2.agents.tool_evaluator import format_tool_result
        long_text = "x" * 5000
        result = format_tool_result("fetch_url", {"result": long_text}, True, {})
        assert "省略" in result
        assert len(result) < 5000

    def test_empty_result(self):
        from core.multi_agent_v2.agents.tool_evaluator import format_tool_result
        result = format_tool_result("write_file", {"result": ""}, True, {})
        assert "(无输出)" in result

    def test_string_result(self):
        from core.multi_agent_v2.agents.tool_evaluator import format_tool_result
        result = format_tool_result("web_search", "搜索结果文本", True, {})
        assert "[web_search] OK" in result
        assert "搜索结果文本" in result


class TestErrorSuggestion:
    """测试错误建议映射"""

    def test_syntax_error(self):
        from core.multi_agent_v2.agents.tool_evaluator import get_error_suggestion
        suggestion = get_error_suggestion("SyntaxError: unexpected token")
        assert "语法" in suggestion

    def test_name_error(self):
        from core.multi_agent_v2.agents.tool_evaluator import get_error_suggestion
        suggestion = get_error_suggestion("NameError: name 'x' is not defined")
        assert "变量名" in suggestion

    def test_timeout_error(self):
        from core.multi_agent_v2.agents.tool_evaluator import get_error_suggestion
        suggestion = get_error_suggestion("TimeoutError: request timed out")
        assert "超时" in suggestion

    def test_unknown_error(self):
        from core.multi_agent_v2.agents.tool_evaluator import get_error_suggestion
        suggestion = get_error_suggestion("SomeRandomError")
        assert "检查" in suggestion


