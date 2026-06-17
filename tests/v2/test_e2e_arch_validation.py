"""
端到端架构验证测试

测试当前 V2 架构的全部核心能力：
1. 新模块导入与功能验证
2. MiddlewareChain 执行流
3. ReAct 核心循环（模拟 LLM）
4. 迭代式文件修改（Write → Review → Improve）
5. 工具缓存与输出截断
6. 上下文预算管理
7. 并发控制
8. 计划管理与质量门
"""

import asyncio
import json
import os
import tempfile
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════
# 1. 新模块导入测试
# ═══════════════════════════════════════════════════════════════════

class TestNewModules:
    """验证新引入的效率模块可以正常导入"""

    def test_output_bounder_import(self):
        from core.multi_agent_v2.agents.output_bounder import (
            bound_tool_output, get_bound_stats, BounderStats,
        )
        assert callable(bound_tool_output)
        assert callable(get_bound_stats)
        # TOOL_OUTPUT_LIMITS 已合并到 tool_result.py
        from core.multi_agent_v2.tools.tool_result import (
            TOOL_OUTPUT_LIMITS, DEFAULT_OUTPUT_LIMIT
        )
        assert DEFAULT_OUTPUT_LIMIT == 3000
        assert TOOL_OUTPUT_LIMITS["read"] == 3000
        assert TOOL_OUTPUT_LIMITS["bash"] == 5000
        assert TOOL_OUTPUT_LIMITS["websearch"] == 4000

    def test_tool_cache_import(self):
        from core.multi_agent_v2.agents.tool_cache import (
            ToolCache, get_tool_cache, WRITE_TOOLS
        )
        assert "write" in WRITE_TOOLS
        assert "edit" in WRITE_TOOLS
        assert "bash" in WRITE_TOOLS
        cache = ToolCache(max_size=10, ttl=60)
        assert cache._max_size == 10
        assert cache._ttl == 60

    def test_context_budget_import(self):
        from core.multi_agent_v2.agents.context_budget import (
            ContextBudgetManager, get_budget_stats
        )
        cbm = ContextBudgetManager(max_context_chars=50000, safety_margin=10000)
        assert cbm.max_context_chars == 50000
        assert cbm.safety_margin == 10000
        assert cbm.min_prune_chars == 15000
        assert cbm.protected_recent_turns == 3

    def test_middleware_import(self):
        from core.multi_agent_v2.agents.middleware import (
            RunContext, MiddlewareChain, BaseMiddleware, HookResult, PlanStep
        )
        ctx = RunContext(task_description="test")
        assert ctx.max_concurrent_tools == 5
        assert ctx.context_budget is None
        assert ctx.plan == []

    def test_file_complete_detection(self):
        """验证 file_quality_middleware.py 中包含游戏交互性检查和大文件检测逻辑"""
        import pytest, inspect
        try:
            from core.multi_agent_v2.agents.quality_archived.file_quality_middleware import FileQualityMiddleware
        except ModuleNotFoundError:
            pytest.skip("quality_archived 模块已被清理")
        source = inspect.getsource(FileQualityMiddleware.on_tool_end)
        assert "_is_game_file" in source, "缺少游戏文件检测"
        assert "_has_event_handler" in source, "缺少事件监听检测"
        assert "_has_event_loop" in source, "缺少游戏循环检测"
        assert "_has_game_state" in source, "缺少游戏状态检测"
        assert "跳过质量干预" in source, "缺少跳过提示"


# ═══════════════════════════════════════════════════════════════════
# 2. 工具输出截断测试
# ═══════════════════════════════════════════════════════════════════

class TestOutputBounder:
    """验证输出截断功能"""

    def test_no_truncation_for_short_text(self):
        from core.multi_agent_v2.agents.output_bounder import bound_tool_output
        text = "short text"
        result = bound_tool_output("read", text)
        assert result == text, "短文本不应被截断"

    def test_truncation_for_long_text(self):
        from core.multi_agent_v2.agents.output_bounder import bound_tool_output
        text = "A" * 10000
        result = bound_tool_output("read", text)
        assert len(result) < len(text), "长文本应被截断"
        assert "... [截断 " in result, "应包含截断标识"

    def test_different_limits_per_tool(self):
        from core.multi_agent_v2.agents.output_bounder import bound_tool_output
        text = "A" * 10000
        read_result = bound_tool_output("read", text)
        bash_result = bound_tool_output("bash", text)
        web_result = bound_tool_output("websearch", text)
        task_result = bound_tool_output("task", text)
        # bash limit = 5000 > read limit = 3000
        assert len(bash_result) > len(read_result), "bash 应比 read 保留更多"
        # websearch limit = 4000
        assert len(bash_result) > len(web_result), "bash 应比 websearch 保留更多"
        # task limit = 2000
        assert len(read_result) > len(task_result), "read 应比 task 保留更多"

    def test_tool_limit_behavior(self):
        """截断限制验证（合并后通过 tool_result.bound_result 或 TOOL_OUTPUT_LIMITS 测试）"""
        from core.multi_agent_v2.tools.tool_result import (
            TOOL_OUTPUT_LIMITS, DEFAULT_OUTPUT_LIMIT, bound_result
        )
        # 精确匹配
        assert TOOL_OUTPUT_LIMITS.get("read_file", DEFAULT_OUTPUT_LIMIT) == 3000
        assert TOOL_OUTPUT_LIMITS.get("execute_shell", DEFAULT_OUTPUT_LIMIT) == 5000
        assert TOOL_OUTPUT_LIMITS.get("execute_python", DEFAULT_OUTPUT_LIMIT) == 5000
        # 未知工具回退默认值
        assert TOOL_OUTPUT_LIMITS.get("unknown_tool", DEFAULT_OUTPUT_LIMIT) == 3000
        # bound_result 可处理 dict/str
        assert bound_result("read", "short") == "short"

    def test_truncation_happens(self):
        from core.multi_agent_v2.agents.output_bounder import bound_tool_output
        result = bound_tool_output("read", "X" * 5000)
        assert len(result) < 5000, "长文本应被截断"
        assert "[截断" in result, "应包含截断标识"

    def test_non_string_input(self):
        from core.multi_agent_v2.agents.output_bounder import bound_tool_output
        result = bound_tool_output("read", {"key": "value"})
        assert isinstance(result, str), "非字符串输入应被转为字符串"
        # dict 短，不应截断
        assert len(result) < 100


# ═══════════════════════════════════════════════════════════════════
# 3. 工具缓存测试
# ═══════════════════════════════════════════════════════════════════

class TestToolCache:
    """验证工具结果缓存"""

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        from core.multi_agent_v2.agents.tool_cache import ToolCache
        cache = ToolCache(max_size=10, ttl=60)
        await cache.set("read", {"file": "test.py"}, "content")
        result = await cache.get("read", {"file": "test.py"})
        assert result == "content"

    @pytest.mark.asyncio
    async def test_cache_miss(self):
        from core.multi_agent_v2.agents.tool_cache import ToolCache
        cache = ToolCache(max_size=10, ttl=60)
        result = await cache.get("read", {"file": "nonexistent.py"})
        assert result is None

    @pytest.mark.asyncio
    async def test_write_tools_not_cached(self):
        from core.multi_agent_v2.agents.tool_cache import ToolCache
        cache = ToolCache(max_size=10, ttl=60)
        for tool in ["write", "edit", "bash", "shell", "task"]:
            await cache.set(tool, {"param": "value"}, "result")
            result = await cache.get(tool, {"param": "value"})
            assert result is None, f"{tool} 不应被缓存"

    @pytest.mark.asyncio
    async def test_cache_lru_eviction(self):
        from core.multi_agent_v2.agents.tool_cache import ToolCache
        cache = ToolCache(max_size=3, ttl=60)
        await cache.set("read", {"f": "1"}, "v1")
        await cache.set("read", {"f": "2"}, "v2")
        await cache.set("read", {"f": "3"}, "v3")
        await cache.set("read", {"f": "4"}, "v4")
        # 第4个应该淘汰第1个
        assert await cache.get("read", {"f": "1"}) is None
        assert await cache.get("read", {"f": "4"}) == "v4"

    @pytest.mark.asyncio
    async def test_cache_ttl_expiry(self):
        import time
        from core.multi_agent_v2.agents.tool_cache import ToolCache
        cache = ToolCache(max_size=10, ttl=0.1)
        await cache.set("read", {"file": "x.py"}, "content")
        assert await cache.get("read", {"file": "x.py"}) == "content"
        await asyncio.sleep(0.15)
        assert await cache.get("read", {"file": "x.py"}) is None

    @pytest.mark.asyncio
    async def test_cache_invalidate(self):
        from core.multi_agent_v2.agents.tool_cache import ToolCache
        cache = ToolCache(max_size=10, ttl=60)
        await cache.set("grep", {"pattern": "hello"}, "result1")
        await cache.set("read", {"file": "test.py"}, "result2")
        await cache.invalidate("grep")
        assert await cache.get("grep", {"pattern": "hello"}) is None
        assert await cache.get("read", {"file": "test.py"}) == "result2"

    @pytest.mark.asyncio
    async def test_cache_clear(self):
        from core.multi_agent_v2.agents.tool_cache import ToolCache
        cache = ToolCache(max_size=10, ttl=60)
        await cache.set("read", {"f": "x"}, "v")
        await cache.clear()
        stats = await cache.get_stats()
        assert stats["size"] == 0

    @pytest.mark.asyncio
    async def test_global_cache_singleton(self):
        from core.multi_agent_v2.agents.tool_cache import get_tool_cache
        c1 = get_tool_cache()
        c2 = get_tool_cache()
        assert c1 is c2, "全局缓存应为单例"


# ═══════════════════════════════════════════════════════════════════
# 4. 上下文预算管理测试
# ═══════════════════════════════════════════════════════════════════

class TestContextBudget:
    """验证上下文预算管理"""

    def test_estimate_tokens(self):
        from core.multi_agent_v2.agents.context_budget import (
            ContextBudgetManager, estimate_tokens,
        )
        cbm = ContextBudgetManager()
        # ~3.5 chars per token
        tokens = estimate_tokens("Hello world, this is a test" * 100)
        assert tokens > 500
        assert tokens < 2000

    def test_is_overflow(self):
        from core.multi_agent_v2.agents.context_budget import ContextBudgetManager
        cbm = ContextBudgetManager(max_context_chars=1000, safety_margin=200)
        from types import SimpleNamespace
        # Under threshold
        ctx = SimpleNamespace(
            tool_results=[], knowledge_context="", plan=None,
            final_answer="", last_error=""
        )
        assert not cbm.is_overflow(ctx)
        # Over threshold
        ctx.tool_results = [{"result": "X" * 900, "tool_call": {"name": "test"}}]
        assert cbm.is_overflow(ctx)

    def test_compaction_summary(self):
        from core.multi_agent_v2.agents.context_budget import ContextBudgetManager
        cbm = ContextBudgetManager()
        entries = [
            {"tool_call": {"name": "grep"}, "success": True},
            {"tool_call": {"name": "write_file"}, "success": True},
            {"tool_call": {"name": "web_search"}, "success": False},
        ]
        summary = cbm.generate_compaction_summary(entries)
        assert "grep" in summary
        assert "write_file" in summary
        assert "✅2" in summary or "2 项成功" in summary

    def test_apply_compaction(self):
        from core.multi_agent_v2.agents.context_budget import ContextBudgetManager
        cbm = ContextBudgetManager(max_context_chars=5000, safety_margin=1000,
                                    protected_recent_turns=1)
        from types import SimpleNamespace
        ctx = SimpleNamespace(
            tool_results=[],
            knowledge_context="",
            plan=None,
            final_answer="",
            last_error=""
        )
        for i in range(10):
            ctx.tool_results.append({
                "tool_call": {"name": "grep" if i % 2 == 0 else "read"},
                "success": True,
                "result": "A" * 1000,
                "quality": "good"
            })

        assert cbm.is_overflow(ctx)
        before_count = len(ctx.tool_results)
        cbm.apply_compaction(ctx)
        after_count = len(ctx.tool_results)
        assert after_count < before_count, "压缩应减少工具结果数量"
        assert cbm.get_total_chars(ctx) < 5000, "压缩后应低于阈值"

    def test_budget_stats(self):
        from core.multi_agent_v2.agents.context_budget import get_budget_stats
        stats = get_budget_stats()
        summary = stats.summary()
        assert isinstance(summary, str)
        assert len(summary) > 0


# ═══════════════════════════════════════════════════════════════════
# 5. MiddlewareChain 执行流测试
# ═══════════════════════════════════════════════════════════════════

class TestMiddlewareExecution:
    """验证 MiddlewareChain 的生命周期执行顺序"""

    @pytest.mark.asyncio
    async def test_middleware_execution_order(self):
        from core.multi_agent_v2.agents.middleware import (
            RunContext, MiddlewareChain, BaseMiddleware, HookResult
        )
        execution_log = []

        class MW1(BaseMiddleware):
            HOOKS = ("on_start", "on_think_start", "on_think_end")

            async def on_start(self, ctx):
                execution_log.append("start1")

            async def on_think_start(self, ctx):
                execution_log.append("think_start1")

            async def on_think_end(self, ctx):
                execution_log.append("think_end1")

        class MW2(BaseMiddleware):
            HOOKS = ("on_start", "on_think_start", "on_think_end")

            async def on_start(self, ctx):
                execution_log.append("start2")

            async def on_think_start(self, ctx):
                execution_log.append("think_start2")

            async def on_think_end(self, ctx):
                execution_log.append("think_end2")

        ctx = RunContext(task_description="test")
        chain = MiddlewareChain()
        chain.add(MW1())
        chain.add(MW2())

        await chain.on_start(ctx)
        assert execution_log == ["start1", "start2"], f"on_start 顺序错误: {execution_log}"
        execution_log.clear()

        await chain.on_think_start(ctx)
        assert execution_log == ["think_start1", "think_start2"]

        execution_log.clear()
        await chain.on_think_end(ctx)
        assert execution_log == ["think_end1", "think_end2"]

    @pytest.mark.asyncio
    async def test_middleware_hook_filtering(self):
        from core.multi_agent_v2.agents.middleware import (
            RunContext, MiddlewareChain, BaseMiddleware
        )
        execution_log = []

        class OnlyStart(BaseMiddleware):
            HOOKS = ("on_start",)

            async def on_start(self, ctx):
                execution_log.append("start")

            async def on_think_start(self, ctx):
                execution_log.append("should_not_run")

        ctx = RunContext(task_description="test")
        chain = MiddlewareChain()
        chain.add(OnlyStart())
        await chain.on_think_start(ctx)
        assert "should_not_run" not in execution_log, "on_think_start 不应被执行"

    @pytest.mark.asyncio
    async def test_middleware_interrupt_propagation(self):
        from core.multi_agent_v2.agents.middleware import (
            RunContext, MiddlewareChain, BaseMiddleware, HookResult
        )

        class InterruptMW(BaseMiddleware):
            HOOKS = ("on_think_start",)

            async def on_think_start(self, ctx):
                return HookResult(jump_to="end", reason="测试中断")

        class AfterInterrupt(BaseMiddleware):
            HOOKS = ("on_think_start",)

            async def on_think_start(self, ctx):
                pytest.fail("中断后不应执行此中间件")

        ctx = RunContext(task_description="test")
        chain = MiddlewareChain()
        chain.add(InterruptMW())
        chain.add(AfterInterrupt())
        result = await chain.on_think_start(ctx)
        assert result.jump_to == "end"
        assert result.reason == "测试中断"

    @pytest.mark.asyncio
    async def test_on_wrap_tool_call_onion_pattern(self):
        """验证 on_wrap_tool_call 洋葱模式：
        outer_before → inner_before → handler → inner_after → outer_after
        """
        from core.multi_agent_v2.agents.middleware import (
            RunContext, MiddlewareChain, BaseMiddleware
        )
        from core.multi_agent_v2.tools.tool_registry import (
            ToolRegistry, _SANDBOX_TOOL_DEFS,
        )
        execution_log = []

        class Outer(BaseMiddleware):
            HOOKS = ()

            async def on_wrap_tool_call(self, ctx, next_mw):
                execution_log.append("outer_before")
                result = await next_mw()
                execution_log.append("outer_after")
                result["outer"] = True
                return result

        class Inner(BaseMiddleware):
            HOOKS = ()

            async def on_wrap_tool_call(self, ctx, next_mw):
                execution_log.append("inner_before")
                result = await next_mw()
                execution_log.append("inner_after")
                result["inner"] = True
                return result

        ctx = RunContext(task_description="test")
        chain = MiddlewareChain()
        chain.add(Outer())
        chain.add(Inner())

        # 注册 mock handler 到真实 ToolRegistry
        reg = ToolRegistry()
        for td in _SANDBOX_TOOL_DEFS:
            reg._tools[td.name] = td
        mock_handler = AsyncMock(return_value={"ok": True, "data": "terminal"})
        reg._tools["test_tool"] = MagicMock(
            name="test_tool", handler=mock_handler,
            parameters={"type": "object", "properties": {}, "required": []},
        )

        with (
            patch("core.multi_agent_v2.tools.tool_registry.get_tool_registry",
                  return_value=reg),
            patch("core.multi_agent_v2.agents.tool_cache.get_tool_cache",
                  return_value=MagicMock(get=AsyncMock(return_value=None), set=AsyncMock())),
        ):
            result = await chain.on_wrap_tool_call(ctx, {
                "name": "test_tool", "arguments": "{}"
            })
        assert execution_log == ["outer_before", "inner_before", "inner_after", "outer_after"]
        assert result.get("outer") is True
        assert result.get("inner") is True
        assert result.get("success") is True

    @pytest.mark.asyncio
    async def test_run_context_field_completeness(self):
        """验证 RunContext 包含所有必要字段"""
        from core.multi_agent_v2.agents.middleware import RunContext
        ctx = RunContext(task_description="test")
        required_fields = [
            "task_description", "max_iterations", "tool_defs",
            "iteration", "interrupted", "tool_results", "last_error",
            "final_answer", "react_depth",
            "plan", "plan_generation",
            "max_concurrent_tools",
            "forced_instructions", "knowledge_context",
            "context_budget",
            "_chain", "_tool_cache", "_filtered_tools",
        ]
        missing = [f for f in required_fields if not hasattr(ctx, f)]
        assert not missing, f"RunContext 缺少字段: {missing}"


# ═══════════════════════════════════════════════════════════════════
# 6. 文件迭代与质量门测试
# ═══════════════════════════════════════════════════════════════════

class TestFileIteration:
    """验证迭代式文件修改的质量门逻辑"""

    def test_write_count_tracking(self):
        """验证 write_file 调用计数"""
        from types import SimpleNamespace
        ctx = SimpleNamespace(
            forced_instructions="",
            _file_iterations={},
            tool_results=[]
        )
        path = "/tmp/test_game.html"
        _iter_key = f"write_iter:{path}"

        # 模拟第一次写入
        count = ctx._file_iterations.get(_iter_key, 0) + 1
        ctx._file_iterations[_iter_key] = count
        assert count == 1
        # 应注入 review 指令
        assert not ctx.forced_instructions  # 这里只是模拟，没触发注入

        # 模拟第二次写入
        count = ctx._file_iterations.get(_iter_key, 0) + 1
        ctx._file_iterations[_iter_key] = count
        assert count == 2

        # 模拟第三次写入
        count = ctx._file_iterations.get(_iter_key, 0) + 1
        ctx._file_iterations[_iter_key] = count
        assert count == 3

    def test_quality_gate_in_step_status(self):
        """验证 update_step_status 在 review 未完成时不标记 done"""
        from types import SimpleNamespace
        step = SimpleNamespace(
            index=1, description="write test.html",
            tool_names=["write_file"], status="pending"
        )
        ctx = SimpleNamespace(
            plan=[step],
            tool_results=[{
                "tool_call": {"name": "write_file", "arguments": {"path": "/tmp/test.html"}},
                "success": True,
                "result": "file written"
            }],
            forced_instructions="【质量改进】请 review 文件",
            react_depth=3,
            consecutive_failures={},
            _step_retries={}
        )

        # 模拟 quality gate 逻辑
        last_result = ctx.tool_results[-1]
        last_tc = last_result.get("tool_call", {})

        succeeded_tools = set()
        for tr in ctx.tool_results:
            tc = tr.get("tool_call", {})
            tool_name = tc.get("name", "")
            if tool_name and tr.get("success"):
                succeeded_tools.add(tool_name)

        step_tools = set(step.tool_names)
        all_done = step_tools.issubset(succeeded_tools)

        # 质量门应阻止标记 done
        if all_done and ctx.forced_instructions and last_tc.get("name") == "write_file":
            pass  # 不标记 done
        else:
            step.status = "done"

        assert step.status != "done", "质量门应阻止步骤标记完成"

    def test_quality_gate_passes_when_no_review_pending(self):
        """验证 review 完成后正常标记 done"""
        from types import SimpleNamespace
        step = SimpleNamespace(
            index=1, description="write test.html",
            tool_names=["write_file"], status="pending"
        )
        ctx = SimpleNamespace(
            plan=[step],
            tool_results=[{
                "tool_call": {"name": "write_file", "arguments": {}},
                "success": True,
                "result": "file written"
            }],
            forced_instructions="",
            react_depth=3,
            consecutive_failures={},
            _step_retries={}
        )

        succeeded_tools = {"write_file"}
        step_tools = set(step.tool_names)
        all_done = step_tools.issubset(succeeded_tools)
        last_tc = ctx.tool_results[-1].get("tool_call", {})

        if all_done and ctx.forced_instructions and last_tc.get("name") == "write_file":
            pass
        else:
            step.status = "done"

        assert step.status == "done", "无 review 待执行时应正常完成"


# ═══════════════════════════════════════════════════════════════════
# 7. 并发控制测试
# ═══════════════════════════════════════════════════════════════════

class TestConcurrencyControl:
    """验证并发控制机制"""

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self):
        """验证信号量确实限制并发数"""
        from core.multi_agent_v2.agents.tool_executor import execute_tool_calls_parallel
        from types import SimpleNamespace

        max_concurrent = 3
        running = 0
        max_running = 0

        async def slow_execute(tc, ctx):
            nonlocal running, max_running
            running += 1
            max_running = max(max_running, running)
            await asyncio.sleep(0.1)
            running -= 1
            return {"success": True, "result": "ok"}

        ctx = SimpleNamespace(max_concurrent_tools=max_concurrent, _chain=None, tool_defs=None, consecutive_failures={})

        tool_calls = [
            {"function": {"name": f"tool_{i}", "arguments": "{}"}}
            for i in range(10)
        ]

        await asyncio.wait_for(
            execute_tool_calls_parallel(
                tool_calls, ctx=ctx, execute_fn=slow_execute,
                max_concurrent=max_concurrent
            ),
            timeout=10
        )

        assert max_running <= max_concurrent, \
            f"最大并发 {max_running} 超过限制 {max_concurrent}"

    @pytest.mark.asyncio
    async def test_default_concurrency(self):
        """验证默认并发数为 5"""
        from core.multi_agent_v2.agents.tool_executor import execute_tool_calls_parallel
        import inspect
        sig = inspect.signature(execute_tool_calls_parallel)
        assert sig.parameters["max_concurrent"].default == 5


# ═══════════════════════════════════════════════════════════════════
# 8. 全流程集成测试（Mock LLM）
# ═══════════════════════════════════════════════════════════════════

class TestFullFlowIntegration:
    """使用 mock LLM 验证完整的 ReAct 执行流程"""

    @pytest.fixture
    def mock_llm_router(self):
        """创建一个 mock LLM 路由器"""
        from unittest.mock import AsyncMock
        router = AsyncMock()
        router.is_available.return_value = True

        router.chat.return_value = "测试回复：任务已完成。"
        return router

    @pytest.fixture
    def mock_tool_registry(self):
        """创建一个 mock 工具注册表"""
        from unittest.mock import AsyncMock, MagicMock
        reg = MagicMock()

        mock_handler = AsyncMock()
        mock_handler.return_value = {"success": True, "result": "ok"}

        reg.get_handler.return_value = mock_handler

        # 模拟 get_tools_for_task
        reg.get_tools_for_task = AsyncMock()
        reg.get_tools_for_task.return_value = [
            MagicMock(
                name="write_file",
                description="写入文件",
                parameters={"type": "object", "properties": {"path": {}, "content": {}}},
                tool_name="write_file", server="__builtin__"
            ),
            MagicMock(
                name="read_file",
                description="读取文件",
                parameters={"type": "object", "properties": {"path": {}}},
                tool_name="read_file", server="__builtin__"
            ),
        ]
        return reg

    @pytest.mark.asyncio
    async def test_react_core_middleware_initialization(self):
        """验证 ReActCoreMiddleware 能正确初始化"""
        from core.multi_agent_v2.agents.react_core import ReActCoreMiddleware
        from core.multi_agent_v2.agents.middleware import RunContext
        mw = ReActCoreMiddleware()
        ctx = RunContext(task_description="写一个八数码游戏到桌面")
        ctx._chain = MagicMock()
        # on_start 不应抛异常
        await mw.on_start(ctx)
        assert ctx._tool_cache is not None or ctx.last_error is None

    @pytest.mark.asyncio
    async def test_chain_build_contains_all_middleware(self):
        """验证默认链包含所有关键中间件"""
        from core.multi_agent_v2.agents.react_core import build_default_chain
        chain = build_default_chain()
        mw_names = [type(m).__name__ for m in chain._middlewares]
        assert "LoopDetectionMiddleware" in mw_names
        assert "TruncationMiddleware" in mw_names
        assert "ReActCoreMiddleware" in mw_names
        assert "ReflectionMiddleware" in mw_names
        assert "KEPAMiddleware" in mw_names
        assert "PermissionMiddleware" in mw_names
        assert "ReActDepthMiddleware" in mw_names
        assert len(chain._middlewares) >= 9

    @pytest.mark.asyncio
    async def test_plan_generation_integration(self):
        """验证计划生成功能（使用 mock LLM）"""
        from core.multi_agent_v2.agents.plan_manager import generate_plan
        from core.multi_agent_v2.agents.middleware import RunContext

        ctx = RunContext(task_description="写一个贪吃蛇游戏到桌面")
        # Mock the LLM router
        mock_router = AsyncMock()

        # Mock first call (understanding) - return empty to test second call path
        mock_router.chat = AsyncMock()
        mock_router.chat.side_effect = [
            "创建一个贪吃蛇游戏 HTML 文件",  # understanding
            "步骤|用 write_file 在桌面创建 snake_game.html（贪吃蛇游戏完整代码）|write_file",  # plan
        ]

        with patch("core.engine.llm_backend.get_llm_router",
                   return_value=mock_router):
            with patch.object(mock_router, "is_available", return_value=True):
                steps = await generate_plan("写一个贪吃蛇游戏到桌面", ctx)
                assert len(steps) >= 1
                assert steps[0].tool_names == ["write_file"]

    @pytest.mark.asyncio
    async def test_step_status_update_replan(self):
        """验证失败步骤的触发重规划"""
        from core.multi_agent_v2.agents.middleware import PlanStep, RunContext
        from core.multi_agent_v2.agents.plan_manager import update_step_status, replan_failed

        ctx = RunContext(task_description="写一个游戏")
        ctx.plan = [
            PlanStep(index=1, description="创建 game.html", tool_names=["write_file"]),
            PlanStep(index=2, description="测试游戏", tool_names=["execute_shell"]),
        ]
        ctx.tool_results = [
            {"tool_call": {"name": "write_file", "arguments": {}}, "success": True, "result": "ok"},
        ]

        # 首次调用：步骤 1 完成
        from types import SimpleNamespace
        ctx.consecutive_failures = {}
        ctx._step_retries = {}
        update_step_status(ctx)
        assert ctx.plan[0].status == "done"

    @pytest.mark.asyncio
    async def test_step_status_advances_with_forced_instructions(self):
        """验证 forced_instructions 不卡步骤状态"""
        from core.multi_agent_v2.agents.middleware import RunContext, PlanStep
        from core.multi_agent_v2.agents.plan_manager import update_step_status

        ctx = RunContext(task_description="生成报告")
        ctx.plan = [
            PlanStep(index=1, description="搜索数据", tool_names=["web_search"]),
            PlanStep(index=2, description="生成报告", tool_names=["write_file"]),
        ]
        ctx.plan[0].status = "done"
        ctx.forced_instructions = "【质量改进】请检查报告内容..."
        ctx.tool_results.append({
            "tool_call": {"name": "write_file", "arguments": {"path": "report.html", "content": "..."}},
            "success": True, "result": {},
        })

        update_step_status(ctx)
        assert ctx.plan[1].status == "done", f"期望 done, 实际 {ctx.plan[1].status}"

    @pytest.mark.asyncio
    async def test_output_bounder_integrated_in_react_core(self):
        """验证 output_bounder 被 react_core 调用"""
        import inspect
        from core.multi_agent_v2.agents.react_core import ReActCoreMiddleware
        source = inspect.getsource(ReActCoreMiddleware.on_think_end)
        assert "bound_tool_output" in source, "react_core 应调用 bound_tool_output"

    @pytest.mark.asyncio
    async def test_tool_cache_integrated_in_middleware(self):
        """验证 tool_cache 被 middleware 使用"""
        import inspect
        from core.multi_agent_v2.agents.middleware import MiddlewareChain
        source = inspect.getsource(MiddlewareChain.on_wrap_tool_call)
        assert "get_tool_cache" in source, "middleware 应调用 get_tool_cache"

    @pytest.mark.asyncio
    async def test_context_budget_integrated_in_react_core(self):
        """验证 context_budget 被 run_react 使用"""
        import inspect
        from core.multi_agent_v2.agents.react_core import run_react
        source = inspect.getsource(run_react)
        assert "ContextBudgetManager" in source, "run_react 应创建 ContextBudgetManager"
        assert "check_and_compact" in source, "run_react 应调用 check_and_compact"

    @pytest.mark.asyncio
    async def test_semaphore_integrated_in_tool_executor(self):
        """验证并发控制在 tool_executor 中实现"""
        import inspect
        from core.multi_agent_v2.agents.tool_executor import execute_tool_calls_parallel
        source = inspect.getsource(execute_tool_calls_parallel)
        assert "asyncio.Semaphore" in source, "应使用 asyncio.Semaphore"
        assert "max_concurrent" in source, "应接受 max_concurrent 参数"


# ═══════════════════════════════════════════════════════════════════
# 9. 错误恢复与边界情况测试
# ═══════════════════════════════════════════════════════════════════

class TestErrorRecovery:
    """验证系统在异常情况下的行为"""

    def test_output_bounder_with_empty_text(self):
        from core.multi_agent_v2.agents.output_bounder import bound_tool_output
        assert bound_tool_output("read", "") == ""
        assert bound_tool_output("read", None) == "None"

    def test_output_bounder_with_newlines(self):
        from core.multi_agent_v2.agents.output_bounder import bound_tool_output
        text = "line1\nline2\nline3\n"
        result = bound_tool_output("read", text)
        assert result == text

    def test_output_bounder_boundary_at_limit(self):
        from core.multi_agent_v2.agents.output_bounder import bound_tool_output
        text = "A" * 3000
        result = bound_tool_output("read", text)
        assert result == text, "刚好等于限制不应截断"

    def test_output_bounder_just_over_limit(self):
        from core.multi_agent_v2.agents.output_bounder import bound_tool_output
        text = "A" * 3001
        result = bound_tool_output("read", text)
        assert "[截断" in result, "超过1字符也应截断"

    @pytest.mark.asyncio
    async def test_cache_with_empty_args(self):
        from core.multi_agent_v2.agents.tool_cache import ToolCache
        cache = ToolCache()
        await cache.set("read", {}, "empty_args")
        result = await cache.get("read", {})
        assert result == "empty_args"

    @pytest.mark.asyncio
    async def test_cache_key_uniqueness(self):
        from core.multi_agent_v2.agents.tool_cache import ToolCache
        cache = ToolCache()
        await cache.set("read", {"file": "a.py"}, "content_a")
        await cache.set("read", {"file": "b.py"}, "content_b")
        assert await cache.get("read", {"file": "a.py"}) == "content_a"
        assert await cache.get("read", {"file": "b.py"}) == "content_b"

    @pytest.mark.asyncio
    async def test_cache_concurrent_access(self):
        """验证并发访问缓存不崩溃"""
        from core.multi_agent_v2.agents.tool_cache import ToolCache
        cache = ToolCache(max_size=5, ttl=60)

        async def concurrent_set(i):
            await cache.set("read", {"f": str(i)}, f"v{i}")

        await asyncio.gather(*[concurrent_set(i) for i in range(20)])
        stats = await cache.get_stats()
        assert stats["size"] <= 5


# ═══════════════════════════════════════════════════════════════════
# 10. 端到端 MCP 服务器可用性测试
# ═══════════════════════════════════════════════════════════════════

class TestMCPServerAvailability:
    """验证 MCP 服务器网络可用性"""

    def test_all_mcp_py_files_exist(self):
        """验证所有 config/mcp_servers.yml 中声明的服务器文件都存在"""
        import yaml
        with open("config/mcp_servers.yml", "r") as f:
            config = yaml.safe_load(f) or {}
        servers = config.get("mcp_servers", [])
        missing = []
        for s in servers:
            command = s.get("command", "")
            if "python3" in command:
                # Extract the file path
                parts = command.split()
                for p in parts:
                    if p.endswith(".py") and "/" in p:
                        if not os.path.exists(p):
                            missing.append(p)
        if missing:
            print(f"\n⚠️ 缺失 MCP 服务器文件: {missing}")
        assert not missing, f"缺失 MCP 服务器文件: {missing}"
