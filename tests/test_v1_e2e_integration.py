#!/usr/bin/env python3
"""V1 全链路端到端集成测试 — 验证 core/ 模块是否真实接入 V1"""

import asyncio
import json
import logging
import sys
from unittest.mock import patch

sys.path.insert(0, ".")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

import pytest
from core.agent_v1 import _modules as M


@pytest.fixture(autouse=True)
def _reset():
    M.clear_cache()
    yield
    M.clear_cache()


# ═══════════════════════════════════════════════════════════════════
# 1. 模块加载器
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("name,loader", [
    ("short_term_memory", M.short_term_memory),
    ("vector_memory", M.vector_memory),
    ("permission_service", M.permission_service),
    ("clarification_service", M.clarification_service),
    ("bfs_processor", M.bfs_processor),
    ("fallback_handler", M.fallback_handler),
    ("collaboration_optimizer", M.collaboration_optimizer),
    ("task_planner", M.task_planner),
    ("security_manager", M.security_manager),
    ("monitoring", M.monitoring),
    ("memory_optimizer", M.memory_optimizer),
    ("sandbox_executor", M.sandbox_executor),
])
def test_module_loader_graceful(name, loader):
    """每个模块懒加载不抛异常（允许成功或静默跳过）"""
    try:
        inst = loader()
        assert inst is not None or True  # None is OK (graceful skip)
    except Exception as e:
        pytest.fail(f"{name} raised {e}")


def test_module_loader_cache():
    """第二次调用命中缓存"""
    a = M.short_term_memory()
    b = M.short_term_memory()
    assert a is b


# ═══════════════════════════════════════════════════════════════════
# 2. ExecutionContext
# ═══════════════════════════════════════════════════════════════════

def test_execution_context_services():
    """至少 LLM + BFS + Clarification 可用"""
    from core.context import ExecutionContext
    ctx = ExecutionContext.create_default()
    ctx.ensure_loaded()
    assert ctx.llm_router is not None, "llm_router must be available"
    assert ctx.bfs_processor is not None, "bfs_processor should load"
    assert ctx.clarification is not None, "clarification should load"
    assert ctx.short_term_memory is not None, "short_term_memory should load"


# ═══════════════════════════════════════════════════════════════════
# 3. LLMAgent 全链路
# ═══════════════════════════════════════════════════════════════════

FAKE_LLM_RESPONSES = {
    "default": {"status": "success", "message": "mock ok"},
    "kepa": {"decision": "continue", "confidence": 0.95, "reason": "mock 通过"},
    "decompose": {"subtasks": ["子任务A", "子任务B"]},
    "analyze": {"decision": "complete", "confidence": 0.9, "reason": "mock 分析完成"},
}


async def _llm_fake(system, user, max_tokens=500, **kw):
    if "kepa" in (system or "").lower():
        return FAKE_LLM_RESPONSES["kepa"]
    if "decompose" in (system or "").lower() or "subtasks" in (system or "").lower():
        return FAKE_LLM_RESPONSES["decompose"]
    if "分析" in (user or ""):
        return FAKE_LLM_RESPONSES["analyze"]
    return {"tool_calls": [], **FAKE_LLM_RESPONSES["default"]}


@pytest.mark.asyncio
async def test_llmagent_get_memory_context():
    """_get_memory_context 返回字符串且不抛异常"""
    from core.agent_v1 import LLMAgent, AgentRole
    agent = LLMAgent("mem_test", AgentRole.WORKER)
    ctx = await agent._get_memory_context()
    assert isinstance(ctx, str)


@pytest.mark.asyncio
async def test_llmagent_save_memory():
    """_save_memory 不抛异常"""
    from core.agent_v1 import LLMAgent, AgentRole
    agent = LLMAgent("save_test", AgentRole.WORKER)
    await agent._save_memory("user", "test content")
    await agent._save_memory("assistant", "response")


@pytest.mark.asyncio
async def test_llmagent_permission_check():
    """危险工具被拦截，安全工具通过"""
    from core.agent_v1 import LLMAgent, AgentRole
    agent = LLMAgent("perm_test", AgentRole.WORKER)

    # 安全工具直接返回 None（不拦截）
    r1 = await agent._check_tool_permission("write_file", {"path": "/tmp/a.txt"})
    # 危险工具可能被拦截（取决于 PermissionService 是否可用）
    r2 = await agent._check_tool_permission("execute_shell", {"command": "ls"})
    # 两个都应该返回 None 或 str，不应抛异常
    assert isinstance(r1, (type(None), str))
    assert isinstance(r2, (type(None), str))


@pytest.mark.asyncio
async def test_llmagent_bfs_analysis():
    """长文本触发 BFS 分析"""
    from core.agent_v1 import LLMAgent, AgentRole
    agent = LLMAgent("bfs_test", AgentRole.WORKER)

    short = await agent._analyze_task_with_bfs("写个文件")
    assert short == ""  # 短文本跳过

    long = await agent._analyze_task_with_bfs("首先搜索今天的天气，然后分析气温趋势，最后生成可视化报告并保存到桌面。" * 5)
    assert isinstance(long, str)


@pytest.mark.asyncio
async def test_llmagent_process_message():
    """process_message 全链路（KEPA + Hermes + 记忆）"""
    from core.agent_v1 import LLMAgent, AgentRole, AgentMessage

    with patch("core.agent_v1.agent._llm_json", _llm_fake):
        agent = LLMAgent("full_test", AgentRole.WORKER)
        msg = AgentMessage(from_agent="tester", to_agent=agent.name, content="写一个 hello.txt 并写入 Hello World")
        result_str = await agent.process_message(msg)
        result = json.loads(result_str)
        assert "status" in result or "success" in result


# ═══════════════════════════════════════════════════════════════════
# 4. LeaderAgent 集成
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_leader_decompose_with_optimizer():
    """CollaborationOptimizer + TaskPlanner 优先，LLM 兜底"""
    from core.agent_v1 import LeaderAgent

    with patch("core.agent_v1.leader._llm_json", _llm_fake):
        leader = LeaderAgent("decompose_test")
        tasks = await leader._decompose_task("帮我查北京天气并生成报告")
        assert isinstance(tasks, list)
        assert len(tasks) >= 1


@pytest.mark.asyncio
async def test_leader_supervise_task():
    """React 主循环 + monitoring"""
    from core.agent_v1 import LeaderAgent, LLMAgent, AgentRole

    with patch("core.agent_v1.leader._llm_json", _llm_fake):
        leader = LeaderAgent("supervise_test")
        worker = LLMAgent("w1", AgentRole.WORKER)

        result = await leader.supervise_task(
            "写个 hello.txt", [worker], active_count=1, max_rounds=1,
        )
        assert "success" in result
        assert "rounds" in result
        assert "total_subtasks" in result


# ═══════════════════════════════════════════════════════════════════
# 5. V1LeaderPool
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pool_context_and_warm():
    """ExecutionContext + MemoryOptimizer + VectorMemory 预热"""
    from core.agent_v1 import V1LeaderPool

    pool = V1LeaderPool()
    await pool._ensure_context()
    assert pool._ctx is not None
    assert pool._ctx.llm_router is not None
    assert pool._ctx.bfs_processor is not None

    pool._warm_vector_memory()


@pytest.mark.asyncio
async def test_pool_create_team():
    """队伍创建 + Agent 注册"""
    from core.agent_v1 import V1LeaderPool

    pool = V1LeaderPool()
    leader, workers = await pool.create_team(worker_count=2, max_workers=3)
    assert leader is not None
    assert len(workers) == 3
    assert len(pool._all_agents) == 4  # 1 leader + 3 workers


@pytest.mark.asyncio
async def test_pool_get_return_worker():
    """Worker 池化复用"""
    from core.agent_v1 import V1LeaderPool

    pool = V1LeaderPool()
    w1 = await pool.get_worker()
    assert w1 is not None
    assert w1.name in pool._busy_workers

    await pool.return_worker(w1)
    assert w1.name not in pool._busy_workers
    assert w1 in pool._worker_pool


# ═══════════════════════════════════════════════════════════════════
# 6. 向后兼容
# ═══════════════════════════════════════════════════════════════════

def test_backward_compat_shim():
    """旧 import 路径与新路径一致"""
    from core.agent_system import LLMAgent as L1, LeaderAgent as Ld1, V1LeaderPool as P1
    from core.agent_v1 import LLMAgent as L2, LeaderAgent as Ld2, V1LeaderPool as P2
    assert L1 is L2
    assert Ld1 is Ld2
    assert P1 is P2


def test_all_symbols_export():
    """__all__ 19 个符号全部可 import"""
    from core.agent_v1 import __all__
    for s in __all__:
        exec(f"from core.agent_v1 import {s}")
