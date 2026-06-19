"""V1 架构 LLM 工具调用格式解析测试

测试范围:
  1. _extract_tool_calls_from_text 从文本提取工具调用
  2. _handle_message 中的工具调用分支逻辑
  3. _llm_with_tools 的响应解析
  4. 工具调用格式的各种边界情况
"""

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from core.agent_system import LLMAgent, LeaderAgent, AgentRole, OUTPUT_FORMATS


# =============================================================================
# 1. _extract_tool_calls_from_text 测试
# =============================================================================

class TestExtractToolCallsFromText:
    """从 LLM 文本响应中提取工具调用"""

    def setup_method(self):
        self.agent = LLMAgent("test_worker", AgentRole.WORKER)

    def test_extract_write_file_format(self):
        """提取 write_file(path=xxx, content=xxx) 格式"""
        text = '我将使用 write_file(path="~/Desktop/test.txt", content="Hello World") 来创建文件'
        result = self.agent._extract_tool_calls_from_text(text)

        assert len(result["tool_calls"]) == 1
        tc = result["tool_calls"][0]
        assert tc["name"] == "write_file"
        assert tc["arguments"]["path"] == "~/Desktop/test.txt"
        assert tc["arguments"]["content"] == "Hello World"

    def test_extract_execute_python_format(self):
        """提取 execute_python(code=xxx) 格式"""
        text = '执行代码: execute_python(code="print(1+1)")'
        result = self.agent._extract_tool_calls_from_text(text)

        assert len(result["tool_calls"]) == 1
        tc = result["tool_calls"][0]
        assert tc["name"] == "execute_python"
        assert tc["arguments"]["code"] == "print(1+1)"

    def test_extract_no_tool_calls(self):
        """没有工具调用时返回空列表"""
        text = "这是普通的文本回复，不包含任何工具调用"
        result = self.agent._extract_tool_calls_from_text(text)

        assert len(result["tool_calls"]) == 0

    def test_extract_multiple_tool_calls(self):
        """提取多个工具调用"""
        text = (
            '先搜索再写文件: execute_python(code="data = 1") '
            '然后 write_file(path="out.txt", content="result")'
        )
        result = self.agent._extract_tool_calls_from_text(text)

        # 应该至少提取到 write_file
        names = [tc["name"] for tc in result["tool_calls"]]
        assert "write_file" in names

    def test_extract_multiline_content(self):
        """提取多行 content 的 write_file"""
        text = '''write_file(path="test.py", content="def hello():
    print('hello')
    return True")'''
        result = self.agent._extract_tool_calls_from_text(text)

        assert len(result["tool_calls"]) == 1
        assert "def hello():" in result["tool_calls"][0]["arguments"]["content"]

    def test_extract_with_single_quotes(self):
        """使用单引号的格式"""
        text = "write_file(path='test.txt', content='Hello')"
        result = self.agent._extract_tool_calls_from_text(text)

        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["arguments"]["path"] == "test.txt"


# =============================================================================
# 2. 工具调用 JSON 格式测试
# =============================================================================

class TestToolCallJsonFormat:
    """测试 LLM 返回的 JSON 工具调用格式"""

    def test_valid_tool_calls_json(self):
        """标准 tool_calls JSON 格式"""
        response = {
            "tool_calls": [
                {"name": "write_file", "arguments": {"path": "test.txt", "content": "hello"}}
            ],
            "reasoning": "需要创建文件"
        }

        assert "tool_calls" in response
        assert len(response["tool_calls"]) == 1
        assert response["tool_calls"][0]["name"] == "write_file"

    def test_tool_calls_with_multiple_tools(self):
        """多个工具调用"""
        response = {
            "tool_calls": [
                {"name": "web_search", "arguments": {"query": "python"}},
                {"name": "write_file", "arguments": {"path": "result.txt", "content": "data"}}
            ]
        }

        assert len(response["tool_calls"]) == 2

    def test_empty_tool_calls_list(self):
        """空工具调用列表"""
        response = {"tool_calls": [], "result": "无需工具"}

        assert len(response["tool_calls"]) == 0

    def test_missing_tool_calls_key(self):
        """缺少 tool_calls 键"""
        response = {"result": "直接完成"}

        tool_calls = response.get("tool_calls", [])
        assert tool_calls == []


# =============================================================================
# 3. OUTPUT_FORMATS 工具调用格式定义测试
# =============================================================================

class TestOutputFormatsToolCalling:
    """测试 OUTPUT_FORMATS"""

    def test_execute_format_exists(self):
        """execute 输出格式存在"""
        assert "execute" in OUTPUT_FORMATS
        assert "status" in OUTPUT_FORMATS["execute"]
        assert "result" in OUTPUT_FORMATS["execute"]


# =============================================================================
# 4. _llm_with_tools 响应解析测试
# =============================================================================

class TestLlmWithToolsParsing:
    """测试 _llm_with_tools 的响应解析逻辑"""

    def setup_method(self):
        self.agent = LLMAgent("test_parse", AgentRole.WORKER)

    @pytest.mark.asyncio
    async def test_dict_response_returned_directly(self):
        """dict 响应直接返回"""
        mock_response = {"tool_calls": [{"name": "write_file", "arguments": {}}]}

        with patch("core.agent_system._get_llm_router") as mock_router:
            mock_router.return_value = MagicMock()
            mock_router.return_value.chat = AsyncMock(return_value=mock_response)

            result = await self.agent._llm_with_tools("system", "user", [])

        assert result == mock_response

    @pytest.mark.asyncio
    async def test_json_string_response_parsed(self):
        """JSON 字符串响应被正确解析"""
        json_str = json.dumps({"tool_calls": [{"name": "execute_python", "arguments": {"code": "1+1"}}]})

        with patch("core.agent_system._get_llm_router") as mock_router:
            mock_router.return_value = MagicMock()
            mock_router.return_value.chat = AsyncMock(return_value=json_str)

            result = await self.agent._llm_with_tools("system", "user", [])

        assert result["tool_calls"][0]["name"] == "execute_python"

    @pytest.mark.asyncio
    async def test_markdown_wrapped_json_parsed(self):
        """被 ```json ``` 包裹的 JSON 被正确解析"""
        json_str = '```json\n{"tool_calls": [{"name": "write_file", "arguments": {"path": "a.txt", "content": "hi"}}]}\n```'

        with patch("core.agent_system._get_llm_router") as mock_router:
            mock_router.return_value = MagicMock()
            mock_router.return_value.chat = AsyncMock(return_value=json_str)

            result = await self.agent._llm_with_tools("system", "user", [])

        assert result["tool_calls"][0]["name"] == "write_file"

    @pytest.mark.asyncio
    async def test_invalid_json_falls_back_to_text_extraction(self):
        """无效 JSON 回退到文本提取"""
        text = '我来执行: execute_python(code="print(42)")'

        with patch("core.agent_system._get_llm_router") as mock_router:
            mock_router.return_value = MagicMock()
            mock_router.return_value.chat = AsyncMock(return_value=text)

            result = await self.agent._llm_with_tools("system", "user", [])

        # 回退到文本提取
        assert len(result.get("tool_calls", [])) > 0
        assert result["tool_calls"][0]["name"] == "execute_python"


# =============================================================================
# 5. _handle_message 工具调用分支测试
# =============================================================================

class TestHandleMessageToolBranch:
    """测试 _handle_message 中工具调用分支"""

    def setup_method(self):
        self.agent = LLMAgent("test_branch", AgentRole.WORKER)

    @pytest.mark.asyncio
    async def test_with_tools_calls_llm_with_tools(self):
        """有工具时调用 _llm_with_tools"""
        tools = [{"type": "function", "function": {"name": "write_file"}}]

        with patch.object(self.agent, "_get_tools_for_task", new_callable=AsyncMock, return_value=tools), \
             patch.object(self.agent, "_llm_with_tools", new_callable=AsyncMock) as mock_lwt, \
             patch.object(self.agent, "_kepa_reflect", new_callable=AsyncMock) as mock_kepa:

            mock_lwt.return_value = {"tool_calls": [], "status": "success"}
            mock_kepa.return_value = {"success": True, "status": "success"}

            from core.agent_system import AgentMessage
            msg = AgentMessage(from_agent="test", content="写一个文件")

            await self.agent._handle_message(msg)

            mock_lwt.assert_called_once()

    @pytest.mark.asyncio
    async def test_without_tools_calls_llm_json(self):
        """无工具时调用 _llm_json"""
        with patch.object(self.agent, "_get_tools_for_task", new_callable=AsyncMock, return_value=[]), \
             patch("core.agent_system._llm_json", new_callable=AsyncMock) as mock_json, \
             patch.object(self.agent, "_kepa_reflect", new_callable=AsyncMock) as mock_kepa:

            mock_json.return_value = {"status": "success", "result": "完成"}
            mock_kepa.return_value = {"success": True, "status": "success"}

            from core.agent_system import AgentMessage
            msg = AgentMessage(from_agent="test", content="简单任务")

            await self.agent._handle_message(msg)

            mock_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_tool_calls_executed_and_injected(self):
        """工具调用被执行并注入到结果中"""
        tool_calls = [{"name": "write_file", "arguments": {"path": "a.txt", "content": "hi"}}]
        tool_result = {"success": True, "result": {"content": "文件已创建"}}

        with patch.object(self.agent, "_get_tools_for_task", new_callable=AsyncMock, return_value=[{"type": "function"}]), \
             patch.object(self.agent, "_llm_with_tools", new_callable=AsyncMock) as mock_lwt, \
             patch.object(self.agent, "_execute_tool_calls", new_callable=AsyncMock) as mock_exec, \
             patch.object(self.agent, "_process_tool_results", new_callable=AsyncMock) as mock_proc, \
             patch.object(self.agent, "_kepa_reflect", new_callable=AsyncMock) as mock_kepa:

            mock_lwt.return_value = {"tool_calls": tool_calls}
            mock_exec.return_value = [tool_result]
            mock_proc.return_value = {"status": "success", "tool_result_summary": "done"}
            mock_kepa.return_value = {"success": True, "status": "success"}

            from core.agent_system import AgentMessage
            msg = AgentMessage(from_agent="test", content="创建文件")

            result = await self.agent._handle_message(msg)

            mock_exec.assert_called_once_with(tool_calls)
            assert "tool_results" in mock_lwt.return_value


# =============================================================================
# 6. _execute_tool_calls 并行执行测试
# =============================================================================

class TestExecuteToolCalls:
    """测试 _execute_tool_calls 并行执行逻辑"""

    def setup_method(self):
        self.agent = LLMAgent("test_exec", AgentRole.WORKER)

    @pytest.mark.asyncio
    async def test_single_tool_call(self):
        """单个工具调用"""
        tool_calls = [{"name": "write_file", "arguments": {"path": "a.txt", "content": "hi"}}]

        with patch.object(self.agent, "_execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {"success": True, "result": "ok"}

            results = await self.agent._execute_tool_calls(tool_calls)

        assert len(results) == 1
        assert results[0]["success"] is True
        assert results[0]["tool_call"] == tool_calls[0]

    @pytest.mark.asyncio
    async def test_multiple_parallel_tool_calls(self):
        """多个工具并行执行"""
        tool_calls = [
            {"name": "write_file", "arguments": {"path": "a.txt", "content": "1"}},
            {"name": "write_file", "arguments": {"path": "b.txt", "content": "2"}},
            {"name": "execute_python", "arguments": {"code": "print(1)"}},
        ]

        with patch.object(self.agent, "_execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {"success": True, "result": "ok"}

            results = await self.agent._execute_tool_calls(tool_calls)

        assert len(results) == 3
        assert all(r["success"] for r in results)

    @pytest.mark.asyncio
    async def test_tool_call_exception_handled(self):
        """工具调用异常被正确处理"""
        tool_calls = [{"name": "bad_tool", "arguments": {}}]

        with patch.object(self.agent, "_execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = RuntimeError("tool crashed")

            results = await self.agent._execute_tool_calls(tool_calls)

        assert len(results) == 1
        assert results[0]["success"] is False
        assert "crashed" in results[0]["error"]

    @pytest.mark.asyncio
    async def test_empty_tool_calls(self):
        """空工具调用列表"""
        results = await self.agent._execute_tool_calls([])
        assert results == []


# =============================================================================
# 7. _react_think 工具调用提示测试
# =============================================================================

class TestReactThinkToolHints:
    """测试队长 _react_think 中的工具调用提示"""

    def setup_method(self):
        self.agent = LeaderAgent("test_think")

    @pytest.mark.asyncio
    async def test_weather_task_provides_tool_hint(self):
        """天气任务提供天气工具提示"""
        with patch("core.agent_system._llm_json", new_callable=AsyncMock) as mock_json:
            mock_json.return_value = {"done": False, "thinking": "查询天气", "action": {"type": "tool"}}

            result = await self.agent._react_think(
                "查询北京天气", [], [], 1
            )

        # 验证 LLM 被调用
        mock_json.assert_called_once()
        system_arg = mock_json.call_args[0][0]
        assert "天气" in system_arg or "weather" in system_arg.lower()

    @pytest.mark.asyncio
    async def test_search_task_provides_tool_hint(self):
        """搜索任务提供搜索工具提示"""
        with patch("core.agent_system._llm_json", new_callable=AsyncMock) as mock_json:
            mock_json.return_value = {"done": False, "thinking": "搜索", "action": {"type": "tool"}}

            result = await self.agent._react_think(
                "爬取百度热搜", [], [], 1
            )

        system_arg = mock_json.call_args[0][0]
        assert "搜索" in system_arg or "search" in system_arg.lower()

    @pytest.mark.asyncio
    async def test_write_task_provides_tool_hint(self):
        """写文件任务提供 write_file 工具提示"""
        with patch("core.agent_system._llm_json", new_callable=AsyncMock) as mock_json:
            mock_json.return_value = {"done": False, "thinking": "创建文件", "action": {"type": "tool"}}

            result = await self.agent._react_think(
                "在桌面创建一个游戏", [], [], 1
            )

        system_arg = mock_json.call_args[0][0]
        assert "write_file" in system_arg


# =============================================================================
# 8. ReAct Action 工具执行测试
# =============================================================================

class TestReactActToolExecution:
    """测试 _react_act 中工具执行"""

    def setup_method(self):
        self.agent = LeaderAgent("test_act")

    @pytest.mark.asyncio
    async def test_tool_action_type_calls_execute_tool(self):
        """tool 类型 action 调用 _execute_tool"""
        action = {"type": "tool", "tool_name": "write_file", "args": {"path": "a.txt", "content": "hi"}}

        with patch.object(self.agent, "_execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {"success": True, "result": "ok"}

            result = await self.agent._react_act("tool", action, [], "test task")

        mock_exec.assert_called_once_with("write_file", {"path": "a.txt", "content": "hi"})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_tool_action_without_name_fails(self):
        """tool 类型 action 无工具名时返回失败"""
        action = {"type": "tool", "args": {}}

        result = await self.agent._react_act("tool", action, [], "test task")

        assert result["success"] is False
        assert "未指定" in result["error"]

    @pytest.mark.asyncio
    async def test_delegate_action_type(self):
        """delegate 类型 action 分配任务给 Worker"""
        worker = LLMAgent("worker1", AgentRole.WORKER)
        worker.process_message = AsyncMock(return_value=json.dumps({"success": True, "result": "done"}))

        action = {"type": "delegate", "task": "子任务描述"}

        result = await self.agent._react_act("delegate", action, [worker], "原始任务")

        assert result["success"] is True
        assert result["worker"] == "worker1"

    @pytest.mark.asyncio
    async def test_unknown_action_type_fails(self):
        """未知 action 类型返回失败"""
        result = await self.agent._react_act("unknown", {}, [], "task")

        assert result["success"] is False
        assert "未知" in result["error"]


# =============================================================================
# 9. 工具调用边界情况测试
# =============================================================================

class TestToolCallEdgeCases:
    """工具调用边界情况"""

    def setup_method(self):
        self.agent = LLMAgent("test_edge", AgentRole.WORKER)

    def test_extract_with_empty_text(self):
        """空文本不崩溃"""
        result = self.agent._extract_tool_calls_from_text("")
        assert result["tool_calls"] == []

    def test_extract_with_none_like_text(self):
        """None 风格文本"""
        result = self.agent._extract_tool_calls_from_text("None")
        assert result["tool_calls"] == []

    def test_tool_call_arguments_types(self):
        """工具调用参数类型多样性"""
        response = {
            "tool_calls": [
                {"name": "write_file", "arguments": {"path": "a.txt", "content": "string"}},
                {"name": "execute_python", "arguments": {"code": "1 + 1"}},
                {"name": "web_search", "arguments": {"query": "test", "engine": "google"}},
            ]
        }

        for tc in response["tool_calls"]:
            assert isinstance(tc["name"], str)
            assert isinstance(tc["arguments"], dict)

    def test_output_format_knows_tool_calls(self):
        """OUTPUT_FORMATS 中的 execute 格式可以包含 tool_calls"""
        # 模拟 LLM 可能返回的格式
        possible_responses = [
            {"tool_calls": [{"name": "write_file", "arguments": {}}], "reasoning": "需要写文件"},
            {"status": "success", "result": "完成", "tool_calls": []},
            {"tool_calls": [{"name": "execute_python", "arguments": {"code": "print(1)"}}]},
        ]

        for resp in possible_responses:
            tool_calls = resp.get("tool_calls", [])
            assert isinstance(tool_calls, list)


# =============================================================================
# 10. 端到端工具调用流程测试（mock LLM）
# =============================================================================

class TestE2EToolCallingFlow:
    """端到端工具调用流程（mock LLM）"""

    def setup_method(self):
        self.agent = LLMAgent("e2e_worker", AgentRole.WORKER)

    @pytest.mark.asyncio
    async def test_full_tool_call_flow_with_json_response(self):
        """完整流程：LLM 返回 JSON 工具调用 → 执行 → 结果注入"""
        with patch.object(self.agent, "_get_tools_for_task", new_callable=AsyncMock) as mock_get_tools:

            mock_get_tools.return_value = [{"type": "function", "function": {"name": "write_file"}}]

            with patch("core.agent_system._llm_json", new_callable=AsyncMock) as mock_json, \
                 patch.object(self.agent, "_execute_tool", new_callable=AsyncMock) as mock_exec:

                # LLM 返回工具调用 JSON
                mock_json.return_value = {
                    "tool_calls": [{"name": "write_file", "arguments": {"path": "test.txt", "content": "hello"}}],
                    "reasoning": "需要创建文件"
                }
                mock_exec.return_value = {"success": True, "result": {"content": "文件已创建"}}

                with patch.object(self.agent, "_kepa_reflect", new_callable=AsyncMock) as mock_kepa:
                    mock_kepa.return_value = {"success": True, "status": "success", "confidence": 0.95}

                    from core.agent_system import AgentMessage
                    msg = AgentMessage(from_agent="test", content="创建文件 test.txt")

                    result = await self.agent.process_message(msg)

                result_data = json.loads(result)
                assert result_data.get("success") is True

    @pytest.mark.asyncio
    async def test_full_tool_call_flow_with_text_response(self):
        """完整流程：LLM 返回文本 → 文本提取工具调用 → 执行"""
        with patch.object(self.agent, "_get_tools_for_task", new_callable=AsyncMock) as mock_get_tools:
            mock_get_tools.return_value = [{"type": "function", "function": {"name": "execute_python"}}]

            with patch("core.agent_system._llm_json", new_callable=AsyncMock) as mock_json, \
                 patch.object(self.agent, "_execute_tool", new_callable=AsyncMock) as mock_exec:

                # LLM 返回非 JSON 文本（触发回退）
                mock_json.side_effect = json.JSONDecodeError("err", "", 0)
                mock_exec.return_value = {"success": True, "result": {"content": "42"}}

                # 模拟 _llm_with_tools 的回退逻辑
                with patch.object(self.agent, "_llm_with_tools", new_callable=AsyncMock) as mock_lwt:
                    mock_lwt.return_value = {
                        "tool_calls": [{"name": "execute_python", "arguments": {"code": "print(1)"}}]
                    }

                    with patch.object(self.agent, "_kepa_reflect", new_callable=AsyncMock) as mock_kepa:
                        mock_kepa.return_value = {"success": True, "status": "success"}

                        from core.agent_system import AgentMessage
                        msg = AgentMessage(from_agent="test", content="执行代码")

                        result = await self.agent.process_message(msg)

                    result_data = json.loads(result)
                    assert result_data.get("success") is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
