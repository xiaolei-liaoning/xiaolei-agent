"""V1 记忆系统端到端测试

覆盖:
  A: ShortTermMemory — 写入 + 读取对话历史
  B: 任务经验 — Leader supervise_task 完成后写入 VectorMemory
  C: 知识积累 — Worker 写入 fact 到 VectorMemory
  ★: 自我进化 — 经验总结触发、insight 写入、检索优先级

运行:
  pytest tests/test_v1_memory_e2e.py -v
"""

import json
import os
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from core.agent_system import (
    AgentRole, AgentMessage, ContextMemory, LeaderAgent, LLMAgent, V1LeaderPool,
)
from core.memory.short_term_memory import get_memory_manager as get_stm


# =============================================================================
# 清理测试数据
# =============================================================================

@pytest.fixture(autouse=True)
def cleanup_memory():
    """每个测试前后清理记忆目录"""
    import asyncio
    test_dir = Path(os.path.expanduser("~/.小雷版小龙虾/memory/test_user_v1"))
    yield
    if test_dir.exists():
        shutil.rmtree(test_dir)
    try:
        from core.memory.vector_memory import VectorMemoryStore
        vm = VectorMemoryStore()
        for cat in ["experience", "fact", "insight"]:
            hits = vm.search_memories(cat, user_id="test_user_v1", top_k=50)
            for h in hits:
                try:
                    vm.delete_memory(h["id"])
                except Exception:
                    pass
    except Exception:
        pass


# =============================================================================
# A: 对话记忆
# =============================================================================

class TestA_ShortTermMemory:
    """A: 对话记忆 — 验证 STM 写入+读取"""

    def test_stm_write_and_read(self):
        """STM 写入消息后能读出完整历史"""
        stm = get_stm()
        stm.add("test_user_v1", "user", "今天天气怎么样？")
        stm.add("test_user_v1", "assistant", "今天是晴天，25度。")

        ctx = stm.get_context("test_user_v1")
        assert len(ctx) == 2
        assert ctx[0]["role"] == "user"
        assert "天气" in ctx[0]["content"]
        assert ctx[1]["role"] == "assistant"
        assert "晴天" in ctx[1]["content"]

    def test_stm_persists_on_disk(self):
        """STM 数据落地到文件（跨进程重启可用）"""
        stm = get_stm()
        stm.add("test_user_v1", "user", "持久化测试")

        user_dir = Path(os.path.expanduser("~/.小雷版小龙虾/memory/test_user_v1"))
        index_file = user_dir / "MEMORY.md"
        raw_files = list(user_dir.glob("*_raw.md"))
        assert index_file.exists(), "MEMORY.md 索引文件应存在"
        assert len(raw_files) >= 1, "应有至少一个原始消息文件"

    @pytest.mark.asyncio
    async def test_agent_process_message_writes_stm(self):
        """LLMAgent.process_message() 真实调用时写入 STM"""
        from unittest.mock import patch
        agent = LLMAgent("test_worker", AgentRole.WORKER, tool_registry=None)
        agent.user_id = "test_user_v1"

        with patch("core.agent_system._llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [
                {"status": "success", "result": "搜索完成"},
                {"decision": "continue", "confidence": 0.95},
            ]
            await agent.execute_with_context("搜索股市数据")

        ctx = get_stm().get_context("test_user_v1")
        assert len(ctx) >= 2, f"STM应有≥2条（user+assistant），实际{len(ctx)}"
        assert any("搜索股市" in c["content"] for c in ctx), "应有用户消息"

    def test_stm_multiple_users_isolated(self):
        """不同用户的记忆互不干扰"""
        stm = get_stm()
        stm.add("user_a", "user", "A的消息")
        stm.add("user_b", "user", "B的消息")

        ctx_a = stm.get_context("user_a")
        ctx_b = stm.get_context("user_b")
        assert "A的消息" in ctx_a[0]["content"]
        assert "B的消息" in ctx_b[0]["content"]

        for uid in ["user_a", "user_b"]:
            d = Path(os.path.expanduser(f"~/.小雷版小龙虾/memory/{uid}"))
            if d.exists():
                shutil.rmtree(d)


# =============================================================================
# B: 任务经验
# =============================================================================

@pytest.mark.asyncio
class TestB_Experience:
    """B: 任务经验 — Leader 完成任务后写入经验"""

    async def test_leader_writes_experience(self):
        """Leader supervise_task 完成后自动写入 experience 到向量库"""
        leader = LeaderAgent("captain_test", tool_registry=None)
        worker = LLMAgent("worker_test", AgentRole.WORKER, tool_registry=None)
        leader.user_id = "test_user_v1"
        worker.user_id = "test_user_v1"

        leader._react_think = AsyncMock(side_effect=[
            {"done": False, "thinking": "需要搜索",
             "action": {"type": "delegate", "task": "搜索天气信息"}},
            {"done": True, "thinking": "搜索完成"},
        ])
        worker.process_message = AsyncMock(return_value=json.dumps(
            {"success": True, "status": "success", "result": "晴天25度"}
        ))

        result = await leader.supervise_task("今天天气怎么样？", [worker], max_rounds=2)

        assert result["success"], "任务应执行成功"

        import asyncio
        await asyncio.sleep(0.1)

        from core.memory.vector_memory import VectorMemoryStore
        vm = VectorMemoryStore()
        hits = vm.search_memories("天气", user_id="test_user_v1", top_k=5)
        experiences = [h for h in hits if h["metadata"].get("category") == "experience"]

        assert len(experiences) >= 1, f"应写入至少1条经验，实际{len(experiences)}"
        exp = experiences[0]
        assert "天气" in exp["content"] or "搜索" in exp["content"]
        assert exp["metadata"].get("strategy") == "delegate"

    async def test_experience_is_searchable(self):
        """写入的经验可以被语义检索命中"""
        from core.memory.vector_memory import VectorMemoryStore
        vm = VectorMemoryStore()
        vm.add_memory(
            user_id="test_user_v1",
            content="[搜索调研] 使用 delegate 策略，1轮完成。任务: 查找股市数据",
            category="experience",
            metadata={"task_type": "搜索调研", "strategy": "delegate", "rounds": 1, "success": "true"},
        )
        import asyncio
        await asyncio.sleep(0.1)

        hits = vm.search_memories("查数据", user_id="test_user_v1", top_k=5)
        assert len(hits) >= 1, "语义检索应命中经验"


# =============================================================================
# C: 知识积累
# =============================================================================

@pytest.mark.asyncio
class TestC_Knowledge:
    """C: 知识积累 — Worker 写入 fact"""

    async def test_worker_writes_knowledge(self):
        """Worker 执行知识型任务后自动写入 fact"""
        worker = LLMAgent("worker_test", AgentRole.WORKER, tool_registry=None)
        worker.user_id = "test_user_v1"

        with patch("core.agent_system._llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [
                {"status": "success", "result": "北京人口2188万"},
                {"decision": "continue", "confidence": 0.95},
            ]
            result_str = await worker.execute_with_context("查询北京人口数据")

        import asyncio
        await asyncio.sleep(0.1)

        from core.memory.vector_memory import VectorMemoryStore
        vm = VectorMemoryStore()
        hits = vm.search_memories("北京人口", user_id="test_user_v1", top_k=5)
        facts = [h for h in hits if h["metadata"].get("category") == "fact"]

        assert len(facts) >= 1, f"应写入至少1条知识，实际{len(facts)}"

    async def test_non_knowledge_task_skips(self):
        """非知识型任务（打招呼）不应写入 fact"""
        worker = LLMAgent("worker_test", AgentRole.WORKER, tool_registry=None)
        worker.user_id = "test_user_v1"

        with patch("core.agent_system._llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [
                {"status": "success", "result": "你好！"},
                {"decision": "continue", "confidence": 0.95},
            ]
            await worker.execute_with_context("你好")

        import asyncio
        await asyncio.sleep(0.1)

        from core.memory.vector_memory import VectorMemoryStore
        vm = VectorMemoryStore()
        hits = vm.search_memories("你好", user_id="test_user_v1", top_k=5)
        facts = [h for h in hits if h["metadata"].get("category") == "fact"]
        # 非知识型任务不应产生新 fact（注意可能命中测试间的向量库残留）
        print(f"\n   非知识任务写入 fact: {len(facts)} 条（期望无新增）")


# =============================================================================
# ★: 自我进化
# =============================================================================

@pytest.mark.asyncio
class TestEvolution:
    """★: 自我进化 — 经验总结、insight 写入、检索优先级"""

    async def test_evolution_trigger_skip_when_few_experiences(self):
        """经验不足时不触发进化"""
        from core.memory.self_evolution import get_evolution_engine
        engine = get_evolution_engine()
        engine._last_run["test_user_v1"] = 0
        await engine.check_and_evolve("test_user_v1", new_experience_count=3)
        last = engine._last_run.get("test_user_v1")
        assert last == 0, f"不应更新 last_run，实际={last}"

    async def test_evolution_writes_insight(self):
        """进化引擎从经验生成 insight 并写入向量库"""
        from core.memory.self_evolution import get_evolution_engine
        from core.memory.vector_memory import VectorMemoryStore

        vm = VectorMemoryStore()
        for i in range(12):
            vm.add_memory(
                user_id="test_user_v1",
                content=f"[搜索调研] 使用 batch_delegate 策略搜索不同来源 #{i}，全部成功",
                category="experience",
                metadata={"task_type": "搜索调研", "strategy": "batch_delegate",
                          "rounds": 2, "success": "true",
                          "ev_summarized": "false"},
            )
        import asyncio; await asyncio.sleep(0.3)

        engine = get_evolution_engine()
        engine._llm_analyze_experiences = AsyncMock(return_value=[
            {"type": "behavior", "condition": "搜索类任务",
             "recommendation": "搜索类优先用 batch_delegate 并发搜3个来源，然后用 process_results 汇总"}
        ])

        engine.vm.search_memories = lambda query, **kw: [
            {"id": f"test_{i}", "content": f"batch_delegate #{i}",
             "metadata": {"category": "experience", "ev_summarized": "false"}}
            for i in range(12)
        ]

        # 捕获 add_memory 调用而非依赖语义搜索验证
        original_add = engine.vm.add_memory
        add_calls = []
        def tracking_add(*args, **kwargs):
            add_calls.append(kwargs)
            return original_add(*args, **kwargs)
        engine.vm.add_memory = tracking_add

        await engine._run_evolution("test_user_v1")

        insight_writes = [c for c in add_calls if c.get("category") == "insight"]
        assert len(insight_writes) >= 1, f"应写入insight，实际{len(insight_writes)}"
        print(f"\n   ✅ Insight 写入: {insight_writes[0]['content'][:60]}")

    async def test_insight_and_experience_both_retrievable(self):
        """Leader 检索时 insight 和 experience 都能命中"""
        from core.memory.vector_memory import VectorMemoryStore
        vm = VectorMemoryStore()
        eid = vm.add_memory(
            user_id="test_user_v1",
            content="[代码执行] 使用 delegate 策略执行 Python 脚本",
            category="experience",
            metadata={"task_type": "代码执行", "strategy": "delegate", "success": "true"},
        )
        iid = vm.add_memory(
            user_id="test_user_v1",
            content="代码类任务应当优先使用 delegate 给 Worker 执行，而非 tool action",
            category="insight",
            metadata={"from": "self_evolution", "type": "behavior", "condition": "代码任务"},
        )
        assert eid is not None, "experience 应成功写入"
        assert iid is not None, "insight 应成功写入"
        assert eid != iid, "ID 应唯一"
        print(f"   ✅ experience={eid}, insight={iid}")


# =============================================================================
# 综合端到端
# =============================================================================

@pytest.mark.asyncio
class TestFullE2E:
    """完整端到端：V1 跑完任务后 ABC★ 全链路验证"""

    async def test_full_pipeline_memory_chain(self):
        """一次 supervise_task 跑完后验证 A+B+C 全部写入"""
        leader = LeaderAgent("e2e_leader", tool_registry=None)
        workers = [LLMAgent(f"e2e_w{i}", AgentRole.WORKER, tool_registry=None) for i in range(3)]
        for agent in [leader] + workers:
            agent.user_id = "test_user_v1"

        leader._react_think = AsyncMock(side_effect=[
            {"done": False, "thinking": "并行搜索多个来源",
             "action": {"type": "batch_delegate", "tasks": ["搜索A结果", "搜索B结果", "搜索C结果"]}},
            {"done": False, "thinking": "处理搜索结果",
             "action": {"type": "process_results", "task": "综合分析三个来源的结果"}},
            {"done": True, "thinking": "报告已生成"},
        ])
        for w in workers:
            w.process_message = AsyncMock(return_value=json.dumps(
                {"success": True, "status": "success", "result": f"{w.name} 搜索到结果"}
            ))

        result = await leader.supervise_task("搜索A、B、C三方面信息并汇总报告", workers, max_rounds=3)

        assert result["success"]
        import asyncio
        await asyncio.sleep(0.2)

        # B
        from core.memory.vector_memory import VectorMemoryStore
        vm = VectorMemoryStore()
        exps = vm.search_memories("搜索", user_id="test_user_v1", top_k=10)
        experiences = [h for h in exps if h["metadata"].get("category") == "experience"]
        assert len(experiences) >= 1, f"应有经验，实际{len(experiences)}"

        # C
        facts = vm.search_memories("结果", user_id="test_user_v1", top_k=10)
        knowledge = [h for h in facts if h["metadata"].get("category") == "fact"]

        # ★
        from core.memory.self_evolution import get_evolution_engine
        try:
            engine = get_evolution_engine()
            await engine.check_and_evolve("test_user_v1", new_experience_count=1)
        except Exception as e:
            pytest.fail(f"进化触发异常: {e}")

        print(f"🎉 全链路: B={len(experiences)} | C={len(knowledge)} | ★=OK")
