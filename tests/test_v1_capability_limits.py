"""V1 架构能力上限全维度测试 — 从最难到最简单

阶梯:
  Tier 1: 多Agent全链路编排 (最难)
  Tier 2: CognitivePipeline 认知闭环
  Tier 3: Worker 深度执行
  Tier 4: 上下文与记忆系统
  Tier 5: 基础组件 (最简单)
  Bonus:  边界情况

运行:
  pytest tests/test_v1_capability_limits.py -v --timeout=120
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from core.agent_system import (
    AgentRole, AgentMessage, ContextMemory, LeaderAgent, LLMAgent, V1LeaderPool,
)


def _mock_worker_response(task_hint="ok"):
    return json.dumps({
        "success": True, "status": "success",
        "result": f"{task_hint} 完成",
        "tool_result_summary": f"工具执行结果: {task_hint}",
        "kepa_iterations": 1, "confidence": 0.95,
    })


# =========================================================================
# ★★★ Tier 1: 多Agent全链路编排 (最难) ★★★
# =========================================================================

class TestTier1_MultiAgentOrchestration:
    """Leader 全链路编排 — 所有测试 mock _react_think + _decompose_task + worker"""

    @pytest.mark.asyncio
    async def test_01_full_react_cycle(self):
        """完整 ReAct 闭环: 分解→批量委派→处理结果→完成"""
        leader = LeaderAgent("captain_full")
        workers = [LLMAgent(f"w{i}", AgentRole.WORKER) for i in range(3)]
        leader._decompose_task = AsyncMock(return_value=["搜索天气", "搜索新闻", "分析趋势"])
        for w in workers:
            w.process_message = AsyncMock(return_value=_mock_worker_response(f"w_{w.name}"))

        leader._react_think = AsyncMock(side_effect=[
            {"done": False, "thinking": "需要并行搜索", "action": {
                "type": "batch_delegate",
                "tasks": ["搜索天气", "搜索新闻", "分析趋势"]
            }},
            {"done": False, "thinking": "综合分析结果", "action": {
                "type": "process_results", "task": "综合分析搜索和新闻结果"
            }},
            {"done": True, "thinking": "所有任务已完成", "final_result": "报告已生成"},
        ])

        result = await leader.supervise_task("搜索天气和新闻并生成报告", workers)

        assert result["success"] is True
        assert result["rounds"] == 3
        # batch(3) + process(1) + done final(1) = 5 subtasks
        assert result["total_subtasks"] == 5

    @pytest.mark.asyncio
    async def test_02_mixed_action_types(self):
        """混合行动类型: tool → delegate → process_results → done"""
        leader = LeaderAgent("captain_mixed")
        workers = [LLMAgent(f"w{i}", AgentRole.WORKER) for i in range(2)]
        leader._decompose_task = AsyncMock(return_value=["搜索热榜"])
        for w in workers:
            w.process_message = AsyncMock(return_value=_mock_worker_response("热榜结果"))
        leader._execute_tool = AsyncMock(return_value={
            "success": True, "result": {"content": "当前天气晴朗 25°C"},
        })

        leader._react_think = AsyncMock(side_effect=[
            {"done": False, "thinking": "先直接查天气", "action": {
                "type": "tool", "tool_name": "web_search", "args": {"query": "北京天气"}
            }},
            {"done": False, "thinking": "再让Worker搜索热榜", "action": {
                "type": "delegate", "task": "搜索今日热榜", "skill": "web_scraper"
            }},
            {"done": False, "thinking": "综合结果生成报告", "action": {
                "type": "process_results", "task": "综合以上结果"
            }},
            {"done": True, "thinking": "全部完成"},
        ])

        result = await leader.supervise_task("查天气和热榜", workers)
        assert result["success"] is True
        assert result["rounds"] == 4

    @pytest.mark.asyncio
    async def test_03_error_recovery_chain(self):
        """错误恢复链: tool失败→强制delegate→Worker成功→process_results"""
        leader = LeaderAgent("captain_recovery")
        workers = [LLMAgent(f"w{i}", AgentRole.WORKER) for i in range(2)]
        leader._decompose_task = AsyncMock(return_value=["执行数据分析"])
        for w in workers:
            w.process_message = AsyncMock(return_value=_mock_worker_response("分析完成"))
        leader._execute_tool = AsyncMock(return_value={
            "success": False, "error": "API 超时",
        })

        leader._react_think = AsyncMock(side_effect=[
            {"done": False, "thinking": "直接调用API", "action": {
                "type": "tool", "tool_name": "fetch_url", "args": {"url": "https://api.example.com/data"}
            }},
            {"done": False, "thinking": "tool失败，委派给Worker", "action": {
                "type": "delegate", "task": "执行数据分析", "skill": "data_analyst"
            }},
            {"done": False, "thinking": "处理Worker结果", "action": {
                "type": "process_results", "task": "综合分析结果"
            }},
            {"done": True, "thinking": "任务完成"},
        ])

        result = await leader.supervise_task("分析数据并生成报告", workers, max_rounds=5)
        assert result["success"] is True
        assert result["rounds"] == 4

    @pytest.mark.asyncio
    async def test_04_all_subtasks_done_force_process(self):
        """全部子任务完成→系统强制注入 process_results"""
        leader = LeaderAgent("captain_force_process")
        workers = [LLMAgent(f"w{i}", AgentRole.WORKER) for i in range(3)]
        leader._decompose_task = AsyncMock(return_value=["子任务A", "子任务B", "子任务C"])
        for w in workers:
            w.process_message = AsyncMock(return_value=_mock_worker_response(f"结果_{w.name}"))

        leader._react_think = AsyncMock(side_effect=[
            {"done": False, "thinking": "并行执行子任务", "action": {
                "type": "batch_delegate", "tasks": ["子任务A", "子任务B", "子任务C"]
            }},
            {"done": True, "thinking": "发现系统强制process_results，已处理完成"},
        ])

        result = await leader.supervise_task("并行任务测试", workers)
        assert result["success"] is True
        assert result["rounds"] == 2

        system_overrides = [
            h for h in result["react_history"]
            if h.get("action_type") == "system_override"
        ]
        assert len(system_overrides) >= 1

    @pytest.mark.asyncio
    async def test_05_ten_subtask_batch_delegate(self):
        """10个以上子任务并发委派"""
        leader = LeaderAgent("captain_10tasks")
        workers = [LLMAgent(f"w{i}", AgentRole.WORKER) for i in range(3)]
        subtasks = [f"任务_{i}" for i in range(10)]
        leader._decompose_task = AsyncMock(return_value=subtasks)

        call_count = [0]
        async def _mock_process(msg):
            call_count[0] += 1
            return _mock_worker_response(f"t{call_count[0]}")
        for w in workers:
            w.process_message = AsyncMock(side_effect=_mock_process)

        leader._react_think = AsyncMock(side_effect=[
            {"done": False, "thinking": "批量执行10个子任务", "action": {
                "type": "batch_delegate", "tasks": subtasks
            }},
            {"done": True, "thinking": "所有子任务已完成"},
        ])

        result = await leader.supervise_task("10个并发任务", workers, max_rounds=3)
        assert result["success"] is True
        assert result["rounds"] == 2
        # 10 batch + 1 done final = 11
        assert result["total_subtasks"] == 11

    @pytest.mark.asyncio
    async def test_06_round_4_force_done_guard(self):
        """≥4轮且有成功结果→强制done (防空转)"""
        leader = LeaderAgent("captain_force_done")
        workers = [LLMAgent(f"w{i}", AgentRole.WORKER) for i in range(2)]
        leader._decompose_task = AsyncMock(return_value=["子任务1"])
        for w in workers:
            w.process_message = AsyncMock(return_value=_mock_worker_response("完成"))

        leader._react_think = AsyncMock(side_effect=[
            {"done": False, "thinking": "第1轮", "action": {"type": "delegate", "task": "子任务1"}},
            {"done": False, "thinking": "第2轮", "action": {"type": "process_results", "task": "分析"}},
            {"done": False, "thinking": "第3轮", "action": {"type": "delegate", "task": "额外检查"}},
            {"done": False, "thinking": "第4轮"},
        ])

        result = await leader.supervise_task("测试强制done守卫", workers, max_rounds=5)
        assert result["success"] is True
        assert result["rounds"] == 4

    @pytest.mark.asyncio
    async def test_07_max_rounds_exhaustion(self):
        """max_rounds 耗尽→success=False"""
        leader = LeaderAgent("captain_forever")
        workers = [LLMAgent(f"w{i}", AgentRole.WORKER) for i in range(1)]
        leader._decompose_task = AsyncMock(return_value=["sub1"])
        for w in workers:
            w.process_message = AsyncMock(
                return_value=json.dumps({"status": "failed", "success": False})
            )

        leader._react_think = AsyncMock(side_effect=[
            {"done": False, "thinking": f"第{i}轮重试", "action": {"type": "delegate", "task": "sub1"}}
            for i in range(1, 6)
        ])

        result = await leader.supervise_task("永远重试的任务", workers, max_rounds=3)
        assert result["success"] is False
        assert result["rounds"] == 3

    @pytest.mark.asyncio
    async def test_08_pipeline_concurrent_serial(self):
        """并发收集→串行合成: batch_delegate → process_results"""
        leader = LeaderAgent("captain_async_pipe")
        workers = [LLMAgent(f"w{i}", AgentRole.WORKER) for i in range(3)]
        leader._decompose_task = AsyncMock(return_value=["搜索A", "搜索B", "搜索C"])
        for w in workers:
            w.process_message = AsyncMock(
                return_value=_mock_worker_response(f"搜索结果{workers.index(w)+1}")
            )

        leader._react_think = AsyncMock(side_effect=[
            {"done": False, "thinking": "第1轮收集数据", "action": {
                "type": "batch_delegate", "tasks": ["搜索A", "搜索B", "搜索C"]
            }},
            {"done": False, "thinking": "第2轮合成报告", "action": {
                "type": "process_results", "task": "综合分析并生成报告"
            }},
            {"done": True, "thinking": "完成"},
        ])

        result = await leader.supervise_task("搜索并生成报告", workers, max_rounds=4)
        assert result["success"] is True
        assert result["rounds"] == 3
        assert len(result["results"]) >= 2

    @pytest.mark.asyncio
    async def test_09_leader_direct_tool_execution(self):
        """Leader 直接执行工具（单步工具场景）"""
        leader = LeaderAgent("captain_tool")
        workers = [LLMAgent("w1", AgentRole.WORKER)]
        leader._decompose_task = AsyncMock(return_value=["查天气"])
        leader._execute_tool = AsyncMock(return_value={
            "success": True, "result": {"content": "北京天气: 晴, 25°C"},
        })

        leader._react_think = AsyncMock(side_effect=[
            {"done": False, "thinking": "直接查天气", "action": {
                "type": "tool", "tool_name": "fetch_url", "args": {"url": "https://wttr.in/Beijing"}
            }},
            {"done": True, "thinking": "天气结果已获取"},
        ])

        result = await leader.supervise_task("查北京天气", workers)
        assert result["success"] is True
        assert result["rounds"] == 2

    @pytest.mark.asyncio
    async def test_10_delegate_with_skill_id(self):
        """委派时指定 skill_id"""
        leader = LeaderAgent("captain_skill")
        workers = [LLMAgent(f"w{i}", AgentRole.WORKER) for i in range(2)]
        leader._decompose_task = AsyncMock(return_value=["代码审查"])
        for w in workers:
            w.process_message = AsyncMock(return_value=_mock_worker_response("代码审查完成"))

        leader._react_think = AsyncMock(side_effect=[
            {"done": False, "thinking": "委派给代码专家", "action": {
                "type": "delegate", "task": "审查代码质量", "skill": "code_reviewer"
            }},
            {"done": True, "thinking": "审查完成"},
        ])

        result = await leader.supervise_task("审查Python代码", workers, skill_id="code_reviewer")
        assert result["success"] is True
        assert result["rounds"] == 2
        assert leader._current_skill_id == "code_reviewer"


# =========================================================================
# ★★★ Tier 2: CognitivePipeline 认知闭环 ★★★
# =========================================================================

class TestTier2_CognitivePipeline:
    """CognitivePipeline —— 需要了解实际API签名"""

    @pytest.mark.asyncio
    async def test_11_cognitive_pipeline_instantiation(self):
        """CognitivePipeline 创建不抛异常"""
        from core.handlers.cognitive_pipeline import CognitivePipeline
        pipe = CognitivePipeline(user_id="test_cog")
        assert pipe.user_id == "test_cog"

    @pytest.mark.asyncio
    async def test_12_enrich_context_graceful(self):
        """_enrich_context 即使组件失败也不抛异常"""
        from core.handlers.cognitive_pipeline import CognitivePipeline
        pipe = CognitivePipeline(user_id="test_ctx")
        ctx = await pipe._enrich_context("测试消息")
        assert isinstance(ctx, dict)
        assert "entities" in ctx
        assert "recent_messages" in ctx
        assert "bfs_tree" in ctx

    @pytest.mark.asyncio
    async def test_13_clarification_service(self):
        """ClarificationService 生成反问问题"""
        from cli.clarification_service import ClarificationService, ClarificationQuestion, QuestionOption
        svc = ClarificationService()
        questions = svc.generate_questions("帮我查个东西")
        # 可能没有匹配到关键词，但不应抛异常
        assert isinstance(questions, list)

    @pytest.mark.asyncio
    async def test_14_run_wraps_exceptions(self):
        """CognitivePipeline.run() 异常→反问响应"""
        from core.handlers.cognitive_pipeline import CognitivePipeline

        pipe = CognitivePipeline(user_id="test_err")
        pipe._enrich_context = AsyncMock(side_effect=ValueError("模拟错误"))

        result = await pipe.run("会出错的任务", skill_name="web_search")
        # run 方法有 try/except 保护，异常转为 clarification
        assert result.get("requires_clarification") is True or "reply" in result


# =========================================================================
# ★★★ Tier 3: Worker 深度执行 ★★★
# =========================================================================

class TestTier3_WorkerDeepExecution:
    """Worker Agent 深度执行 — mock _llm_with_tools_from_conversation"""

    @pytest.mark.asyncio
    async def test_15_worker_kepa_max_retry(self):
        """KEPA 反思最大重试（低置信度→最终通过）"""
        agent = LLMAgent("worker_kepa", AgentRole.WORKER)
        with patch.object(agent, '_llm_with_tools_from_conversation', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"status": "success", "result": "partial"}
            with patch("core.agent_system._llm_json", new_callable=AsyncMock) as mock_kepa:
                mock_kepa.side_effect = [
                    {"decision": "continue", "confidence": 0.3},
                    {"decision": "continue", "confidence": 0.5},
                    {"decision": "continue", "confidence": 0.95},
                ]
                result = await agent.execute_with_context("需要多次反思的任务")

        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["kepa_iterations"] == 3
        assert parsed["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_16_worker_kepa_fail_decision(self):
        """KEPA 判定 fail→标记失败"""
        agent = LLMAgent("worker_fail", AgentRole.WORKER)
        with patch.object(agent, '_llm_with_tools_from_conversation', new_callable=AsyncMock) as mock_llm:
            # process_message retries up to 3 times, provide enough values
            mock_llm.return_value = {"status": "failed", "result": "bad"}
            with patch("core.agent_system._llm_json", new_callable=AsyncMock) as mock_kepa:
                mock_kepa.side_effect = [
                    {"decision": "fail", "confidence": 0.2, "reason": "质量太差"},
                    {"decision": "fail", "confidence": 0.1, "reason": "再次失败"},
                    {"decision": "fail", "confidence": 0.1, "reason": "最终失败"},
                ]
                result = await agent.execute_with_context("应失败的任务")

        parsed = json.loads(result)
        assert parsed["status"] == "failed"
        assert parsed["success"] is False

    @pytest.mark.asyncio
    async def test_17_worker_with_tool_calls(self):
        """Worker 执行工具调用并处理结果"""
        agent = LLMAgent("worker_tool", AgentRole.WORKER)
        with patch.object(agent, '_llm_with_tools_from_conversation', new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [
                {"status": "success", "tool_calls": [
                    {"name": "web_search", "arguments": {"query": "北京天气"}},
                ]},
                {"status": "success", "content": "北京天气 25°C", "tool_calls": []},
            ]
            with patch.object(agent, '_execute_tool_calls', new_callable=AsyncMock) as mock_tool:
                mock_tool.return_value = [
                    {"success": True, "result": {"content": "北京天气 25°C"}},
                ]
                with patch("core.agent_system._llm_json", new_callable=AsyncMock) as mock_kepa:
                    mock_kepa.return_value = {"decision": "continue", "confidence": 0.95}
                    result = await agent.execute_with_context("搜索北京信息")

        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert "北京" in str(parsed)

    @pytest.mark.asyncio
    async def test_18_worker_multiple_llm_calls(self):
        """Worker 执行中 LLM 多次调用（工具→总结）"""
        agent = LLMAgent("worker_multi", AgentRole.WORKER)
        with patch.object(agent, '_llm_with_tools_from_conversation', new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [
                {"status": "success", "tool_calls": [
                    {"name": "web_search", "arguments": {"query": "北京"}},
                ]},
                {"status": "success", "content": "最终回答", "tool_calls": []},
            ]
            with patch.object(agent, '_execute_tool_calls', new_callable=AsyncMock) as mock_tool:
                mock_tool.return_value = [{"success": True, "result": {"content": "北京天气 25°C"}}]
                with patch("core.agent_system._llm_json", new_callable=AsyncMock) as mock_kepa:
                    mock_kepa.return_value = {"decision": "continue", "confidence": 0.95}
                    result = await agent.execute_with_context("搜索北京")

        parsed = json.loads(result)
        assert parsed["status"] == "success"

    @pytest.mark.asyncio
    async def test_19_worker_context_isolation(self):
        """多Worker上下文隔离"""
        a1 = LLMAgent("agent_a", AgentRole.WORKER)
        a2 = LLMAgent("agent_b", AgentRole.WORKER)

        with patch.object(a1, '_llm_with_tools_from_conversation', new_callable=AsyncMock) as m1:
            m1.return_value = {"content": "a1_result", "tool_calls": []}
            with patch.object(a2, '_llm_with_tools_from_conversation', new_callable=AsyncMock) as m2:
                m2.return_value = {"content": "a2_result", "tool_calls": []}
                with patch("core.agent_system._llm_json", new_callable=AsyncMock) as mk:
                    mk.return_value = {"decision": "continue", "confidence": 0.95}

                    r1 = await a1.execute_with_context("任务A")
                    r2 = await a2.execute_with_context("任务B")

        p1, p2 = json.loads(r1), json.loads(r2)
        ctx_a1 = a1.context.get_recent()
        ctx_a2 = a2.context.get_recent()
        assert "任务A" in ctx_a1
        assert "任务B" in ctx_a2
        assert "任务B" not in ctx_a1
        assert "任务A" not in ctx_a2

    @pytest.mark.asyncio
    async def test_20_worker_tool_failure_then_retry(self):
        """Worker 工具失败→KEPA低置信→重试→成功"""
        agent = LLMAgent("worker_retry", AgentRole.WORKER)
        with patch.object(agent, '_llm_with_tools_from_conversation', new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [
                {"content": "", "tool_calls": [
                    {"name": "fetch_url", "arguments": {"url": "https://bad.url"}}
                ]},
                {"content": "retry success", "tool_calls": []},
            ] * 2  # process_message can retry
            with patch.object(agent, '_execute_tool_calls', new_callable=AsyncMock) as mock_tool:
                mock_tool.side_effect = [
                    [{"success": False, "error": "Connection refused"}],
                    [{"success": True, "result": {"content": "retry data"}}],
                ] * 2
                with patch("core.agent_system._llm_json", new_callable=AsyncMock) as mock_kepa:
                    mock_kepa.side_effect = [
                        {"decision": "continue", "confidence": 0.3},
                        {"decision": "continue", "confidence": 0.95},
                    ] * 2
                    result = await agent.execute_with_context("获取远程数据")

        parsed = json.loads(result)
        assert parsed["status"] == "success"


# =========================================================================
# ★★★ Tier 4: 上下文与记忆系统 ★★★
# =========================================================================

class TestTier4_ContextAndMemory:
    """上下文管理与记忆系统"""

    def test_21_context_memory_overflow(self):
        """ContextMemory 25条→保留后20条"""
        mem = ContextMemory()
        for i in range(25):
            mem.add(f"entry_{i}")
        assert len(mem.entries) == 20
        assert mem.entries[0] == "entry_5"
        assert mem.entries[-1] == "entry_24"

    def test_22_context_memory_empty_default(self):
        mem = ContextMemory()
        assert mem.get_recent() == "（无上下文）"

    def test_23_context_memory_get_recent_n(self):
        mem = ContextMemory()
        for i in range(10):
            mem.add(f"entry_{i}")
        recent = mem.get_recent(3)
        assert "entry_7" in recent
        assert "entry_8" in recent
        assert "entry_9" in recent
        assert "entry_6" not in recent

    def test_24_context_memory_clear(self):
        mem = ContextMemory()
        mem.add("something")
        mem.clear()
        assert mem.entries == []
        assert mem.get_recent() == "（无上下文）"

    @pytest.mark.asyncio
    async def test_25_leader_experience_store(self):
        """_store_experience 不抛异常"""
        leader = LeaderAgent("exp_test")
        leader.user_id = "test_user"
        await leader._store_experience("测试任务", {
            "success": True, "rounds": 2, "total_subtasks": 3,
            "react_history": [{"action_type": "delegate"}],
        })

    @pytest.mark.asyncio
    async def test_26_worker_knowledge_store(self):
        """_store_knowledge 不抛异常"""
        worker = LLMAgent("kw_test", AgentRole.WORKER)
        await worker._store_knowledge("搜索北京天气", {
            "success": True, "result": "晴天"
        })

    @pytest.mark.asyncio
    async def test_27_stm_integration(self):
        """STM 写入+读取不抛异常"""
        from core.memory.short_term_memory import get_memory_manager as get_stm
        stm = get_stm()
        uid = "test_v1_stm"
        stm.add(uid, "user", "测试消息")
        ctx = stm.get_context(uid)
        assert isinstance(ctx, list)


# =========================================================================
# ★ Tier 5: 基础组件（最简单） ★
# =========================================================================

class TestTier5_BasicComponents:
    """V1 基础组件"""

    def test_28_agent_role_configs(self):
        worker = LLMAgent("worker_xiao", AgentRole.WORKER)
        assert worker.role == AgentRole.WORKER
        assert worker.status == "idle"
        rn, desc, fmt = worker._get_role_config()
        assert "队员" in rn
        assert fmt == "execute"

        leader = LLMAgent("leader_zhang", AgentRole.LEADER)
        rn, desc, fmt = leader._get_role_config()
        assert "队长" in rn
        assert fmt == "decompose"

    def test_29_round_robin_assignment(self):
        leader = LeaderAgent("assign_test")
        workers = [LLMAgent(f"w{i}", AgentRole.WORKER) for i in range(3)]
        assignments = leader._assign(["a", "b", "c", "d", "e"], workers)
        assert len(assignments) == 5
        assert [a["worker"].name for a in assignments] == ["w0", "w1", "w2", "w0", "w1"]

    def test_30_empty_tasks_return_empty(self):
        leader = LeaderAgent("empty_test")
        assert leader._assign([], [LLMAgent("w1", AgentRole.WORKER)]) == []

    def test_31_fewer_tasks_than_workers(self):
        leader = LeaderAgent("few_test")
        workers = [LLMAgent(f"w{i}", AgentRole.WORKER) for i in range(5)]
        assignments = leader._assign(["x", "y"], workers)
        assert len(assignments) == 2
        assert assignments[0]["worker"].name == "w0"
        assert assignments[1]["worker"].name == "w1"

    @pytest.mark.asyncio
    async def test_32_pool_create_team_defaults(self):
        pool = V1LeaderPool()
        leader, workers = await pool.create_team()
        assert leader.role == AgentRole.LEADER
        assert len(workers) == 5
        assert leader.active_worker_count == 3

    @pytest.mark.asyncio
    async def test_33_pool_worker_reuse(self):
        pool = V1LeaderPool()
        w1 = await pool.get_worker()
        assert w1 is not None
        assert w1.name in pool._busy_workers
        await pool.return_worker(w1)
        assert w1.name not in pool._busy_workers

    @pytest.mark.asyncio
    async def test_34_pool_get_agent(self):
        pool = V1LeaderPool()
        leader, _ = await pool.create_team()
        assert pool.get_agent(leader.name) is leader
        assert pool.get_agent("不存在") is None

    @pytest.mark.asyncio
    async def test_35_pool_discard(self):
        pool = V1LeaderPool()
        leader, workers = await pool.create_team()
        await pool.discard([leader])
        assert pool.get_agent(leader.name) is None

    def test_36_agent_message_model(self):
        msg = AgentMessage(from_agent="tester", content="测试内容")
        assert msg.from_agent == "tester"
        assert msg.timestamp is not None
        assert msg.message_type == "task"

    @pytest.mark.asyncio
    async def test_37_skill_router(self):
        from core.agent_system import V1SkillRouter
        router = V1SkillRouter()
        sid = await router.match("搜索百度热搜")
        assert isinstance(sid, str)

    @pytest.mark.asyncio
    async def test_38_task_decomposition(self):
        """Leader 分解任务返回列表"""
        leader = LeaderAgent("decompose_test")
        with patch("core.agent_system._llm_json", new_callable=AsyncMock) as mock:
            mock.return_value = {"subtasks": ["搜索天气", "分析数据", "生成报告"]}
            tasks = await leader._decompose_task("搜索天气并生成报告")
        assert isinstance(tasks, list)
        assert len(tasks) == 3

    def test_39_agent_status_transitions(self):
        agent = LLMAgent("state_test", AgentRole.WORKER)
        assert agent.status == "idle"
        agent._update_state("executing", "工作中")
        assert agent.status == "executing"
        agent._update_state("completed", "完成")
        assert agent.status == "completed"


# =========================================================================
# 🔥 Bonus: 边界情况
# =========================================================================

class TestBoundary_EdgeCases:
    """边界情况与极端场景"""

    @pytest.mark.asyncio
    async def test_40_empty_worker_pool_delegate(self):
        leader = LeaderAgent("empty_worker")
        result = await leader._react_act("delegate", {"task": "测试"}, [], "原始任务", [])
        assert result["success"] is False
        assert "无可用 Worker" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_41_unknown_action_type(self):
        leader = LeaderAgent("unknown_action")
        result = await leader._react_act("fly", {}, [LLMAgent("w1", AgentRole.WORKER)], "任务", [])
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_42_tool_without_name(self):
        leader = LeaderAgent("no_tool_name")
        result = await leader._react_act("tool", {"tool_name": "", "args": {}}, [], "任务", [])
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_43_delegate_without_task(self):
        leader = LeaderAgent("no_task")
        result = await leader._react_act("delegate", {"task": ""}, [LLMAgent("w1", AgentRole.WORKER)], "任务", [])
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_44_llm_json_retry(self):
        """_llm_json JSONDecodeError→重试→成功"""
        from core.agent_system import _llm_json
        calls = [0]
        async def _mock_chat(messages, **kw):
            calls[0] += 1
            return '{"status": "success"}' if calls[0] > 1 else "not json"

        with patch("core.agent_system._get_llm_router") as r:
            r.return_value.chat = _mock_chat
            result = await _llm_json("system", "user")

        assert result.get("status") == "success"

    def test_45_llm_semaphore_concurrency(self):
        from core.agent_system import _llm_semaphore
        assert _llm_semaphore._value == 3

    @pytest.mark.asyncio
    async def test_46_worker_no_tools(self):
        agent = LLMAgent("no_tool_worker", AgentRole.WORKER)
        agent.tool_registry = None
        with patch.object(agent, '_llm_with_tools_from_conversation', new_callable=AsyncMock) as m:
            m.side_effect = [{"content": "no tools needed", "tool_calls": []}] * 3
            with patch("core.agent_system._llm_json", new_callable=AsyncMock) as mk:
                mk.side_effect = [{"decision": "continue", "confidence": 0.95}] * 3
                result = await agent.execute_with_context("简单对话")
        parsed = json.loads(result)
        assert parsed.get("content") == "no tools needed"

    @pytest.mark.asyncio
    async def test_47_leader_store_experience_no_vm(self):
        """_store_experience 无 vm 不抛异常"""
        leader = LeaderAgent("no_vm")
        await leader._store_experience("测试", {"success": True, "rounds": 1, "total_subtasks": 1})

    @pytest.mark.asyncio
    async def test_48_llm_json_empty_response(self):
        """_llm_json 空响应→空字典"""
        from core.agent_system import _llm_json
        with patch("core.agent_system._get_llm_router") as r:
            r.return_value.chat = AsyncMock(return_value=None)
            result = await _llm_json("system", "user")
        assert result == {}


if __name__ == "__main__":
    async def _manual():
        tests = [
            ("T1-01 full ReAct", TestTier1_MultiAgentOrchestration().test_01_full_react_cycle()),
            ("T1-02 mixed types", TestTier1_MultiAgentOrchestration().test_02_mixed_action_types()),
            ("T1-07 max rounds", TestTier1_MultiAgentOrchestration().test_07_max_rounds_exhaustion()),
            ("T3-19 isolation", TestTier3_WorkerDeepExecution().test_19_worker_context_isolation()),
            ("T5-28 roles", TestTier5_BasicComponents().test_28_agent_role_configs()),
            ("T5-29 assign", TestTier5_BasicComponents().test_29_round_robin_assignment()),
            ("B-44 retry", TestBoundary_EdgeCases().test_44_llm_json_retry()),
        ]
        for name, coro in tests:
            await coro
            print(f"  ✅ {name}")

    asyncio.run(_manual())
    print("\n✅ All manual tests done")
