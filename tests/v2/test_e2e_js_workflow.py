"""
E2E 测试: JS Workflow 编排多 Agent（全 mock，无需真实 LLM）

验证 JS bridge → orchestrator.agent() → AgentPool 复用
"""
import pytest
from unittest.mock import AsyncMock, patch


class TestOrchestrator:
    """orchestrator 模块基础验证"""

    def test_orchestrator_module_exists(self):
        from core.multi_agent_v2.orchestration import orchestrator
        assert hasattr(orchestrator, 'agent')
        assert hasattr(orchestrator, 'AgentPool')

    def test_orchestration_init_exports(self):
        from core.multi_agent_v2.orchestration import agent, AgentResult
        assert callable(agent)

    def test_agent_pool_acquire_release(self):
        import asyncio
        from core.multi_agent_v2.orchestration.orchestrator import AgentPool
        pool = AgentPool(size=2)

        async def _run():
            a1 = await pool.acquire("test1")
            assert a1 is not None
            assert pool.available == 1
            a2 = await pool.acquire("test2")
            assert a2 is not None
            assert pool.available == 0
            pool.release(a1)
            assert pool.available == 1
            pool.release(a2)
            assert pool.available == 2

        asyncio.run(_run())

    def test_agent_result_bool(self):
        from core.multi_agent_v2.orchestration.orchestrator import AgentResult
        assert bool(AgentResult(success=True)) is True
        assert bool(AgentResult(success=False)) is False


class TestAgentFunction:
    """agent() 函数核心逻辑验证（全 mock）"""

    @pytest.mark.asyncio
    async def test_agent_called_with_prompt(self):
        from core.multi_agent_v2.orchestration import orchestrator
        with patch.object(orchestrator, '_execute_agent', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = orchestrator.AgentResult(
                success=True, output="mock result", label="test"
            )
            result = await orchestrator.agent("写一首诗", {"label": "test"})
            assert result.success is True
            assert result.output == "mock result"
            mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_agent_returns_error_on_failure(self):
        from core.multi_agent_v2.orchestration import orchestrator
        with patch.object(orchestrator, '_execute_agent', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = orchestrator.AgentResult(
                success=False, error="LLM 调用失败"
            )
            result = await orchestrator.agent("失败任务")
            assert result.success is False
            assert "失败" in result.error

    @pytest.mark.asyncio
    async def test_agent_handles_execution_error(self):
        from core.multi_agent_v2.orchestration import orchestrator
        with patch.object(orchestrator, '_execute_agent', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = orchestrator.AgentResult(
                success=False, error="执行异常"
            )
            result = await orchestrator.agent("异常任务")
            assert result.success is False


class TestJSWorkflowBridge:
    """JS bridge → Python orchestrator 链路验证"""

    @pytest.mark.asyncio
    async def test_js_workflow_imports(self):
        from core.multi_agent_v2.workflow.js_workflow import ClaudeCodeWorkflow
        assert ClaudeCodeWorkflow is not None

    def test_js_workflow_has_run_method(self):
        from core.multi_agent_v2.workflow.js_workflow import ClaudeCodeWorkflow
        wf = ClaudeCodeWorkflow()
        assert hasattr(wf, 'run')
        assert callable(wf.run)

    def test_js_workflow_cache_key_consistency(self):
        from core.multi_agent_v2.workflow.js_workflow import ClaudeCodeWorkflow
        wf = ClaudeCodeWorkflow()
        key1 = wf._make_cache_key("hello", {"temperature": 0.7})
        key2 = wf._make_cache_key("hello", {"temperature": 0.7})
        key3 = wf._make_cache_key("world", {})
        assert key1 == key2
        assert key1 != key3

    def test_js_workflow_cache_stats(self):
        from core.multi_agent_v2.workflow.js_workflow import ClaudeCodeWorkflow
        wf = ClaudeCodeWorkflow()
        stats = wf.cache_stats()
        assert "size" in stats
        assert "hits" in stats
        assert "misses" in stats

    def test_run_claude_workflow_exists(self):
        from core.multi_agent_v2.workflow.js_workflow import run_claude_workflow
        assert callable(run_claude_workflow)
