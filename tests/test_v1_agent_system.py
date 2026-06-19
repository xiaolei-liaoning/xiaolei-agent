"""V1 队长-队员模式单元测试

覆盖:
  1. ContextMemory 最大 20 条
  2. LLMAgent 角色配置
  3. LeaderAgent supervise_task 主循环（mock LLM）
  4. _assign 轮询分配
  5. V1LeaderPool create_team
  6. discard / get_agent / get_all_agents
  7. execute_with_context 消息处理（mock LLM）
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from core.agent_system import (
    AgentRole,
    ContextMemory,
    LeaderAgent,
    LLMAgent,
    V1LeaderPool,
)


# =============================================================================
# 1. ContextMemory 测试
# =============================================================================

class TestContextMemory:
    """ContextMemory — 最多保留 20 条记录"""

    def test_add_25_entries_max_20(self):
        """添加 25 条记录后只保留后 20 条"""
        mem = ContextMemory()
        for i in range(25):
            mem.add(f"entry_{i}")

        assert len(mem.entries) == 20
        assert mem.entries[0] == "entry_5"
        assert mem.entries[-1] == "entry_24"

    def test_get_recent_empty(self):
        """空记忆返回默认提示文本"""
        mem = ContextMemory()
        assert mem.get_recent() == "（无上下文）"

    def test_get_recent_returns_last_n(self):
        """get_recent(n) 返回最近 n 条记录"""
        mem = ContextMemory()
        for i in range(10):
            mem.add(f"entry_{i}")

        recent = mem.get_recent(3)
        assert "entry_7" in recent
        assert "entry_8" in recent
        assert "entry_9" in recent
        assert "entry_6" not in recent

    def test_get_recent_default_n(self):
        """get_recent 默认返回最近 5 条（n=5）"""
        mem = ContextMemory()
        for i in range(10):
            mem.add(f"entry_{i}")

        recent = mem.get_recent()
        assert "entry_5" in recent
        assert "entry_9" in recent

    def test_clear_empties_entries(self):
        """clear 后 entries 为空列表"""
        mem = ContextMemory()
        mem.add("something")
        mem.clear()
        assert mem.entries == []
        assert mem.get_recent() == "（无上下文）"


# =============================================================================
# 2. LLMAgent 测试
# =============================================================================

class TestLLMAgent:
    """LLMAgent 创建与角色配置"""

    def test_worker_creation_and_role_config(self):
        """创建 Worker Agent，验证角色、状态和配置字符串"""
        agent = LLMAgent("worker_xiaoming", AgentRole.WORKER)

        assert agent.name == "worker_xiaoming"
        assert agent.role == AgentRole.WORKER
        assert agent.status == "idle"
        assert isinstance(agent.context, ContextMemory)

        role_name, description, fmt_type = agent._get_role_config()
        assert "队员" in role_name
        assert "执行" in description
        assert fmt_type == "execute"

    def test_leader_creation_and_role_config(self):
        """创建 Leader Agent 验证角色配置"""
        agent = LLMAgent("leader_zhang", AgentRole.LEADER)

        assert agent.role == AgentRole.LEADER

        role_name, description, fmt_type = agent._get_role_config()
        assert "队长" in role_name
        assert "拆解" in description
        assert fmt_type == "decompose"

    def test_unknown_role_fallback(self):
        """未识别的角色回退到通用配置"""
        # AgentRole 是枚举，但可以通过扩展方式测试默认分支
        # 仅确保 _get_role_config 不会抛异常
        agent = LLMAgent("generic_agent", AgentRole.WORKER)
        agent.role = None  # 人为制造异常路径
        # 内部用 configs.get(self.role, ...) 兜底
        # 由于 role=None，会匹配到默认值
        role_name, description, fmt_type = agent._get_role_config()
        assert "通用" in role_name


# =============================================================================
# 3. LeaderAgent 测试
# =============================================================================

class TestLeaderAgent:
    """LeaderAgent supervise_task 主循环测试（mock LLM）"""

    @pytest.mark.asyncio
    async def test_supervise_task_completes_in_one_round(self):
        """mock 分解与 worker 响应，队长首轮判定完成"""
        leader = LeaderAgent("captain_test")
        workers = [LLMAgent(f"worker_{i}", AgentRole.WORKER) for i in range(3)]

        # 1. mock 分解：返回预定子任务
        leader._decompose_task = AsyncMock(return_value=["sub1", "sub2", "sub3"])

        # 2. mock Worker 的 response（通过 process_message 接口）
        for w in workers:
            w.process_message = AsyncMock(
                return_value=json.dumps(
                    {"success": True, "status": "success", "result": f"{w.name} 完成"}
                )
            )

        # 3. mock 分析：首轮即 complete
        leader._analyze_results = AsyncMock(
            return_value={"decision": "complete", "reason": "满意"}
        )

        # 4. mock LLM 决策使用批量分配，然后判定完成
        leader._react_think = AsyncMock(side_effect=[
            {
                "done": False,
                "thinking": "需要并行执行多个子任务",
                "action": {"type": "batch_delegate", "tasks": ["sub1", "sub2", "sub3"]}
            },
            {
                "done": True,
                "thinking": "所有子任务已完成",
            }
        ])

        result = await leader.supervise_task("原始任务描述", workers)

        assert result["success"] is True
        assert result["rounds"] == 2
        assert result["total_subtasks"] == 3
        # batch_delegate 返回单个结果，内含 3 个子任务
        assert len(result["results"]) == 1
        batch_data = result["results"][0]["result"]
        assert batch_data["success_count"] == 3

    @pytest.mark.asyncio
    async def test_supervise_task_retry_then_complete(self):
        """队长在重试后判定完成，验证多轮调度能力"""
        leader = LeaderAgent("captain_retry")
        workers = [LLMAgent(f"w_{i}", AgentRole.WORKER) for i in range(2)]

        leader._decompose_task = AsyncMock(return_value=["t1", "t2"])

        for w in workers:
            w.process_message = AsyncMock(
                return_value=json.dumps({"success": True, "status": "success", "result": "ok"})
            )

        # 第一次 retry，第二次 complete
        leader._analyze_results = AsyncMock(
            side_effect=[
                {
                    "decision": "retry",
                    "retry_tasks": ["t1"],
                    "reason": "需要更多细节",
                },
                {"decision": "complete"},
            ]
        )

        # mock LLM 决策：第一轮使用批量分配，第二轮任务完成
        leader._react_think = AsyncMock(side_effect=[
            {
                "done": False,
                "thinking": "需要并行执行子任务",
                "action": {"type": "batch_delegate", "tasks": ["t1", "t2"]}
            },
            {
                "done": True,
                "thinking": "任务已完成",
            }
        ])

        result = await leader.supervise_task("需要迭代的任务", workers, max_rounds=3)

        assert result["success"] is True
        assert result["rounds"] == 2

    @pytest.mark.asyncio
    async def test_supervise_task_hits_max_rounds(self):
        """队长持续判定 retry 直到 max_rounds 限制"""
        leader = LeaderAgent("captain_forever")
        workers = [LLMAgent(f"w_{i}", AgentRole.WORKER) for i in range(2)]

        leader._decompose_task = AsyncMock(return_value=["sub1"])

        for w in workers:
            w.process_message = AsyncMock(
                return_value=json.dumps({"status": "success", "result": "ok"})
            )

        # 永远 retry
        leader._analyze_results = AsyncMock(
            return_value={
                "decision": "retry",
                "retry_tasks": ["sub1"],
                "reason": "不满足",
            }
        )

        result = await leader.supervise_task(
            "永远重试的任务", workers, max_rounds=3
        )

        # max_rounds=3 耗尽后，remaining 不为空 → success=False
        assert result["success"] is False
        assert result["rounds"] == 3

    @pytest.mark.asyncio
    async def test_supervise_task_pipeline_concurrent_to_serial(self):
        """测试混合调度：并发→串行（pipeline模式）
        
        场景：
        1. 第1轮：batch_delegate 并发执行3个子任务
        2. 第2轮：process_results 串行处理并发结果
        3. 第3轮：任务完成
        """
        leader = LeaderAgent("captain_pipeline")
        workers = [LLMAgent(f"w_{i}", AgentRole.WORKER) for i in range(3)]

        # mock 分解任务
        leader._decompose_task = AsyncMock(return_value=["搜索A", "搜索B", "搜索C"])

        # mock Worker 的响应
        for i, w in enumerate(workers):
            w.process_message = AsyncMock(
                return_value=json.dumps({
                    "success": True, 
                    "status": "success", 
                    "result": f"搜索结果{i+1}"
                })
            )

        # mock 分析结果
        leader._analyze_results = AsyncMock(
            return_value={"decision": "complete", "reason": "所有结果已处理"}
        )

        # mock LLM 决策：第1轮并发，第2轮串行处理，第3轮完成
        leader._react_think = AsyncMock(side_effect=[
            {
                "done": False,
                "thinking": "数据收集阶段：需要并发搜索多个来源",
                "action": {"type": "batch_delegate", "tasks": ["搜索A", "搜索B", "搜索C"]}
            },
            {
                "done": False,
                "thinking": "处理阶段：基于上一轮并发结果，串行生成综合报告",
                "action": {"type": "process_results", "task": "综合分析搜索结果并生成报告"}
            },
            {
                "done": True,
                "thinking": "任务完成：报告已生成",
            }
        ])

        result = await leader.supervise_task("搜索并生成报告", workers, max_rounds=5)

        assert result["success"] is True
        assert result["rounds"] == 3
        # 第1轮 batch_delegate 产生1个结果，第2轮 process_results 产生1个结果
        assert len(result["results"]) == 2
        
        # 验证 process_results 被调用时正确处理了前一轮结果
        process_results_result = result["results"][1]
        assert process_results_result["success"] is True
        assert process_results_result["processed_count"] == 3


# =============================================================================
# 4. _assign 轮询分配测试
# =============================================================================

class TestAssign:
    """_assign 轮询 (round-robin) 分配逻辑"""

    def test_5_tasks_3_workers_round_robin(self):
        """5 个任务轮询分配给 3 个 Worker"""
        leader = LeaderAgent("assign_leader")
        workers = [LLMAgent(f"w{i}", AgentRole.WORKER) for i in range(3)]
        tasks = [f"task_{i}" for i in range(5)]

        assignments = leader._assign(tasks, workers)

        assert len(assignments) == 5
        # round-robin: 索引 0→w0, 1→w1, 2→w2, 3→w0, 4→w1
        expected_order = ["w0", "w1", "w2", "w0", "w1"]
        for i, (a, exp_name) in enumerate(zip(assignments, expected_order)):
            assert a["worker"].name == exp_name, (
                f"task[{i}] 应分配给 {exp_name}，实际分配给 {a['worker'].name}"
            )
            assert a["task"] == tasks[i]
            assert a["index"] == i

    def test_3_tasks_3_workers(self):
        """3 个任务 3 个 Worker 各分配一个"""
        leader = LeaderAgent("assign_even")
        workers = [LLMAgent(f"w{i}", AgentRole.WORKER) for i in range(3)]
        tasks = ["a", "b", "c"]

        assignments = leader._assign(tasks, workers)

        assert len(assignments) == 3
        assert assignments[0]["worker"].name == "w0"
        assert assignments[1]["worker"].name == "w1"
        assert assignments[2]["worker"].name == "w2"

    def test_2_tasks_5_workers_only_first_2_used(self):
        """任务数少于 Worker 数时，只使用前 N 个 Worker"""
        leader = LeaderAgent("assign_few_tasks")
        workers = [LLMAgent(f"w{i}", AgentRole.WORKER) for i in range(5)]
        tasks = ["x", "y"]

        assignments = leader._assign(tasks, workers)

        assert len(assignments) == 2
        assert assignments[0]["worker"].name == "w0"
        assert assignments[1]["worker"].name == "w1"

    def test_empty_tasks(self):
        """空任务列表返回空分配"""
        leader = LeaderAgent("assign_empty")
        workers = [LLMAgent(f"w{i}", AgentRole.WORKER) for i in range(3)]

        assignments = leader._assign([], workers)
        assert assignments == []


# =============================================================================
# 5-7. V1LeaderPool 测试
# =============================================================================

class TestV1LeaderPool:
    """V1LeaderPool — 队长 Agent 池"""

    @pytest.mark.asyncio
    async def test_create_team_3_5_returns_1_leader_plus_5_workers(self):
        """create_team(3,5) 返回 1 个 Leader + 5 个 Worker"""
        pool = V1LeaderPool()
        leader, workers = await pool.create_team(worker_count=3, max_workers=5)

        # Leader 属性验证
        assert leader.role == AgentRole.LEADER
        assert leader.active_worker_count == 3  # 默认激活 3 个
        assert leader.max_workers == 5

        # Worker 数量
        assert len(workers) == 5
        assert all(w.role == AgentRole.WORKER for w in workers)

        # Worker 命名格式: 队员1_<id>, 队员2_<id>, ...
        for i, w in enumerate(workers):
            assert w.name.startswith(f"队员{i+1}_")

    @pytest.mark.asyncio
    async def test_create_team_defaults(self):
        """create_team() 默认参数: worker_count=3, max_workers=5"""
        pool = V1LeaderPool()
        leader, workers = await pool.create_team()

        assert len(workers) == 5
        assert leader.active_worker_count == 3

    @pytest.mark.asyncio
    async def test_create_team_worker_count_equals_max(self):
        """worker_count == max_workers 时激活全部 Worker"""
        pool = V1LeaderPool()
        leader, workers = await pool.create_team(worker_count=7, max_workers=7)

        assert len(workers) == 7
        assert leader.active_worker_count == 7

    @pytest.mark.asyncio
    async def test_discard_removes_leader_from_pool(self):
        """discard 后 Leader 从 _all_agents 移除，Worker 归还池中"""
        pool = V1LeaderPool()
        leader, workers = await pool.create_team(3, 5)

        # 清理队长
        await pool.discard([leader])
        assert pool.get_agent(leader.name) is None

        # Worker 归还池中（仍在 _all_agents）
        await pool.discard(workers)
        for w in workers:
            assert pool.get_agent(w.name) is not None

    @pytest.mark.asyncio
    async def test_get_agent_returns_correct_instance(self):
        """get_agent 按名称查找并返回正确的 Agent 实例"""
        pool = V1LeaderPool()
        leader, workers = await pool.create_team(3, 5)

        # 按名字查找队长
        found = pool.get_agent(leader.name)
        assert found is leader

        # 按名字查找队员
        for w in workers:
            found = pool.get_agent(w.name)
            assert found is w

    @pytest.mark.asyncio
    async def test_get_agent_nonexistent_returns_none(self):
        """查找不存在的名字返回 None"""
        pool = V1LeaderPool()
        await pool.create_team(3, 5)

        assert pool.get_agent("不存在的Agent") is None

    @pytest.mark.asyncio
    async def test_get_all_agents_returns_all_registered(self):
        """get_all_agents 返回全部 6 个已注册 Agent"""
        pool = V1LeaderPool()
        await pool.create_team(3, 5)  # 1 + 5 = 6

        all_agents = pool.get_all_agents()
        assert len(all_agents) == 6

        # 每个 Agent 都能通过 get_agent 再次找到
        names = {a.name for a in all_agents}
        for name in names:
            assert pool.get_agent(name) is not None


# =============================================================================
# 8. execute_with_context 测试
# =============================================================================

class TestExecuteWithContext:
    """execute_with_context 消息处理（mock LLM）"""

    @pytest.mark.asyncio
    async def test_mocked_llm_processing(self):
        """mock _llm_json 后 execute_with_context 正常处理并更新 context"""
        agent = LLMAgent("worker_exec", AgentRole.WORKER)

        with patch("core.agent_system._llm_json", new_callable=AsyncMock) as mock_llm:
            # side_effect 按调用顺序: 主LLM调用 → KEPA反思调用
            mock_llm.side_effect = [
                {"status": "success", "result": "done", "details": {"key": "val"}},
                {"decision": "continue", "confidence": 0.95},
            ]

            result = await agent.execute_with_context("执行测试指令")

        parsed = json.loads(result)

        # 验证主回复内容
        assert parsed["status"] == "success"
        assert parsed["result"] == "done"
        assert parsed["details"] == {"key": "val"}

        # 验证 KEPA 反思添加的字段
        assert parsed["confidence"] == 0.95
        assert parsed["kepa_iterations"] == 1

        # 验证 context 记忆更新
        recent = agent.context.get_recent(2)
        assert "收到" in recent and "执行测试指令" in recent
        assert "回复" in recent

    @pytest.mark.asyncio
    async def test_kepa_low_confidence_triggers_retry(self):
        """KEPA 置信度低时触发反思重试逻辑"""
        agent = LLMAgent("worker_kepa", AgentRole.WORKER)

        with patch("core.agent_system._llm_json", new_callable=AsyncMock) as mock_llm:
            # 主回复结果，然后 KEPA 低置信度两次后到 0.9
            mock_llm.side_effect = [
                {"status": "success", "result": "partial"},
                {"decision": "continue", "confidence": 0.5},   # 低 → 重试
                {"decision": "continue", "confidence": 0.7},   # 仍不够 → 重试
                {"decision": "continue", "confidence": 0.9},   # OK
            ]

            result = await agent.execute_with_context("低置信度任务")

        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["result"] == "partial"
        assert parsed["confidence"] == 0.9
        assert parsed["kepa_iterations"] == 3  # 第 3 次才通过

    @pytest.mark.asyncio
    async def test_kepa_decision_fail_marks_failed(self):
        """KEPA 判断 fail 时标记为失败"""
        agent = LLMAgent("worker_fail", AgentRole.WORKER)

        with patch("core.agent_system._llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [
                # attempt 0: main + kepa
                {"status": "success", "result": "bad result"},
                {"decision": "fail", "confidence": 0.2, "reason": "结果不完整"},
                # attempt 1: main + kepa (on_task_failed returns retry by default)
                {"status": "failed", "result": "retry failed"},
                {"decision": "fail", "confidence": 0.1, "reason": "仍然失败"},
                # attempt 2: main + kepa (final)
                {"status": "failed", "result": "final failure"},
                {"decision": "fail", "confidence": 0.1, "reason": "最终失败"},
            ]

            result = await agent.execute_with_context("应失败的任务")

        parsed = json.loads(result)
        assert parsed["status"] == "failed"
        assert parsed["success"] is False

    @pytest.mark.asyncio
    async def test_context_isolation_between_agents(self):
        """不同 Agent 的 context 互不干扰"""
        a1 = LLMAgent("agent_a", AgentRole.WORKER)
        a2 = LLMAgent("agent_b", AgentRole.WORKER)

        with patch("core.agent_system._llm_json", new_callable=AsyncMock) as mock_llm:
            # a1: 2 calls, a2: 2 calls = 4 total
            mock_llm.side_effect = [
                {"status": "success", "result": "a1_result"},
                {"decision": "continue", "confidence": 0.95},
                {"status": "success", "result": "a2_result"},
                {"decision": "continue", "confidence": 0.92},
            ]

            r1 = await a1.execute_with_context("任务A")
            r2 = await a2.execute_with_context("任务B")

        assert json.loads(r1)["result"] == "a1_result"
        assert json.loads(r2)["result"] == "a2_result"

        # context 隔离验证
        ctx_a1 = a1.context.get_recent()
        ctx_a2 = a2.context.get_recent()
        assert "任务A" in ctx_a1
        assert "任务B" in ctx_a2
        assert "任务B" not in ctx_a1  # a1 不知道 a2 的任务
        assert "任务A" not in ctx_a2  # a2 不知道 a1 的任务
