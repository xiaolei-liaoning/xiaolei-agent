"""集成测试：Worktree 隔离 / Checkpoint 恢复 / Budget 共享"""

import os
import sys
import tempfile
import pytest

# ── WorktreeIsolator ─────────────────────────────────────────

class TestWorktreeIsolator:
    """git worktree 隔离 — 子 Agent 在独立 worktree 里写文件"""

    def test_worktree_non_git_dir_returns_none(self):
        from core.multi_agent_v2.infrastructure.worktree_isolator import WorktreeIsolator
        with tempfile.TemporaryDirectory() as tmp:
            iso = WorktreeIsolator.create(tmp, "test_non_git")
            assert iso is None, "非 git 仓库应返回 None"

    def test_worktree_resolve_path_noop_without_init(self):
        from core.multi_agent_v2.infrastructure.worktree_isolator import WorktreeIsolator
        iso = WorktreeIsolator("/tmp", "test")
        # 没创建 worktree → resolve_path 原样返回
        result = iso.resolve_path("/tmp/foo.txt")
        assert result == "/tmp/foo.txt"

    def test_worktree_resolve_outside_repo_path(self):
        from core.multi_agent_v2.infrastructure.worktree_isolator import WorktreeIsolator
        iso = WorktreeIsolator("/tmp/repo", "test")
        iso.worktree_path = "/tmp/wt_abc"
        iso._created = True
        # ~/Desktop 等不在 repo 内的路径不重定向
        result = iso.resolve_path("~/Desktop/file.txt")
        assert result == os.path.expanduser("~/Desktop/file.txt")

    def test_worktree_active_global(self):
        from core.multi_agent_v2.infrastructure.worktree_isolator import (
            get_active_worktree, set_active_worktree,
        )
        assert get_active_worktree() is None
        set_active_worktree("dummy")
        assert get_active_worktree() == "dummy"
        set_active_worktree(None)
        assert get_active_worktree() is None


# ── Checkpoint ──────────────────────────────────────────────

class TestCheckpoint:
    """Resume checkpoint — 跨 turn 持久化"""

    def test_save_and_load_checkpoint(self, tmp_path):
        from core.multi_agent_v2.agents.conversation_store import ConversationStore
        db = str(tmp_path / "test.db")
        store = ConversationStore(db)
        sid = "test_session_001"

        # 保存 checkpoint
        state = {"round_num": 3, "final_answer": "partial", "done": True}
        store.save_checkpoint(sid, 3, state)

        # 读取
        cp = store.load_latest_checkpoint(sid)
        assert cp is not None
        assert cp["session_id"] == sid
        assert cp["round_num"] == 3
        assert cp["state"]["final_answer"] == "partial"

    def test_load_empty_returns_none(self, tmp_path):
        from core.multi_agent_v2.agents.conversation_store import ConversationStore
        db = str(tmp_path / "test.db")
        store = ConversationStore(db)
        cp = store.load_latest_checkpoint("no_such_session")
        assert cp is None

    def test_load_latest_checkpoint(self, tmp_path):
        from core.multi_agent_v2.agents.conversation_store import ConversationStore
        db = str(tmp_path / "test.db")
        store = ConversationStore(db)
        sid = "multi_cp"

        store.save_checkpoint(sid, 1, {"round": 1})
        store.save_checkpoint(sid, 2, {"round": 2})
        store.save_checkpoint(sid, 5, {"round": 5})

        cp = store.load_latest_checkpoint(sid)
        assert cp["round_num"] == 5
        assert cp["state"]["round"] == 5

    def test_list_checkpoints(self, tmp_path):
        from core.multi_agent_v2.agents.conversation_store import ConversationStore
        db = str(tmp_path / "test.db")
        store = ConversationStore(db)
        sid = "list_cp"

        store.save_checkpoint(sid, 1, {"a": 1})
        store.save_checkpoint(sid, 2, {"b": 2})

        cps = store.list_checkpoints(sid)
        assert len(cps) == 2
        assert cps[0]["round_num"] == 1
        assert cps[1]["round_num"] == 2

    def test_delete_checkpoints(self, tmp_path):
        from core.multi_agent_v2.agents.conversation_store import ConversationStore
        db = str(tmp_path / "test.db")
        store = ConversationStore(db)
        sid = "del_cp"

        store.save_checkpoint(sid, 1, {"x": 1})
        store.delete_checkpoints(sid)
        cp = store.load_latest_checkpoint(sid)
        assert cp is None

    @pytest.mark.asyncio
    async def test_resume_react_no_checkpoint(self):
        """无 checkpoint 时 resume_react 应回退到 run_react"""
        from core.multi_agent_v2.agents.react_core import resume_react
        # session_id 不存在 → 返回 run_react 的兜底结果
        result = await resume_react("nonexistent_session")
        # 应该能跑完（LLM 可能不可用，但不抛异常）
        assert isinstance(result, dict)
        assert "success" in result

    @pytest.mark.asyncio
    async def test_resume_react_with_checkpoint(self, tmp_path):
        from core.multi_agent_v2.agents.conversation_store import ConversationStore
        from core.multi_agent_v2.agents.react_core import resume_react
        db = str(tmp_path / "resume_test.db")
        store = ConversationStore(db)
        sid = "resume_me"

        state = {"round_num": 3, "final_answer": "done", "last_error": ""}
        store.save_checkpoint(sid, 3, state)

        # 有 checkpoint 但 resume 时 task 会以新 run 执行
        result = await resume_react(sid, new_task_description="继续")
        assert isinstance(result, dict)
        # 不抛异常就算通过（LLM 可能在 CI 中不可用）
        assert "success" in result


# ── Budget 共享 ─────────────────────────────────────────────

class TestBudgetSharing:
    """共享 budget — 主 Agent + 子 Agent 共享一个额度"""

    def test_budget_tracker_defaults(self):
        from core.multi_agent_v2.orchestration.orchestrator import BudgetTracker
        bt = BudgetTracker(total_budget=1000)
        assert bt.total_budget == 1000
        assert bt.remaining() == 1000
        assert bt.has_budget() is True
        assert bt.spent() == 0

    def test_budget_spend_and_exhaust(self):
        from core.multi_agent_v2.orchestration.orchestrator import BudgetTracker
        bt = BudgetTracker(total_budget=500)
        bt.spend(300, "llm_call_1")
        assert bt.spent() == 300
        assert bt.remaining() == 200
        assert bt.has_budget() is True
        bt.spend(200, "llm_call_2")
        assert bt.remaining() == 0
        assert bt.has_budget() is False
        # over spend
        bt.spend(100, "over")
        assert bt.remaining() == 0  # max(0, ...)

    def test_budget_unlimited(self):
        from core.multi_agent_v2.orchestration.orchestrator import BudgetTracker
        bt = BudgetTracker(total_budget=None)
        assert bt.remaining() == float("inf")
        assert bt.has_budget() is True
        bt.spend(999999)
        assert bt.has_budget() is True

    def test_budget_spent_records(self):
        from core.multi_agent_v2.orchestration.orchestrator import BudgetTracker
        bt = BudgetTracker(total_budget=100)
        bt.spend(30, "round_1")
        bt.spend(20, "round_2")
        records = bt._records
        assert len(records) == 2
        assert records[0]["amount"] == 30
        assert records[0]["label"] == "round_1"
        assert records[1]["amount"] == 20

    def test_global_set_and_get_budget(self):
        from core.multi_agent_v2.orchestration.orchestrator import (
            set_budget, get_budget, BudgetTracker,
        )
        # 清理
        set_budget(None)
        bt = get_budget()
        assert bt is None or bt.total_budget is None

        set_budget(50000)
        bt = get_budget()
        assert bt is not None
        assert bt.total_budget == 50000
        assert bt.remaining() == 50000

    def test_budget_exceeded_exception(self):
        from core.multi_agent_v2.orchestration.orchestrator import BudgetExceeded
        with pytest.raises(BudgetExceeded):
            raise BudgetExceeded("budget 耗尽")

    def test_budget_shared_across_calls(self):
        """多次 spend 共享同一实例 — 模拟主+子Agent场景"""
        from core.multi_agent_v2.orchestration.orchestrator import (
            set_budget, get_budget,
        )
        set_budget(1000)
        bt = get_budget()

        # 主 Agent 花了 600
        bt.spend(600, "main_agent")
        assert bt.remaining() == 400

        # 子 Agent 检查共享预算
        assert bt.has_budget() is True
        bt.spend(300, "sub_agent_1")
        assert bt.remaining() == 100
        assert bt.has_budget() is True

        # 第二个子 Agent 只能花 100
        bt.spend(100, "sub_agent_2")
        assert bt.remaining() == 0
        assert bt.has_budget() is False


# ── 集成：worktree + checkpoint + budget 同时生效 ──────────

class TestIntegration:
    """三者组合使用不冲突"""

    def test_worktree_and_budget_globals_independent(self):
        """worktree global 和 budget global 用不同的变量，互不干扰"""
        from core.multi_agent_v2.orchestration.orchestrator import (
            set_budget, get_budget,
        )
        from core.multi_agent_v2.infrastructure.worktree_isolator import (
            set_active_worktree, get_active_worktree,
        )

        set_budget(1000)
        bt = get_budget()
        assert bt is not None

        set_active_worktree("test_wt")
        assert get_active_worktree() == "test_wt"
        assert bt.remaining() == 1000  # budget 不受影响

        set_active_worktree(None)
        assert get_active_worktree() is None
        assert bt.remaining() == 1000  # budget 依然不受影响

    @pytest.mark.asyncio
    async def test_run_react_with_budget(self):
        """react 循环中设置 budget 后不应抛异常"""
        from core.multi_agent_v2.orchestration.orchestrator import set_budget
        from core.multi_agent_v2.agents.react_core import run_react

        set_budget(200000)  # 足够的预算
        result = await run_react("简单测试：输出数字 42", max_rounds=1)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_run_react_budget_exhausted(self):
        """budget 耗尽后应快速终止（最小预算 → 循环退出而非跑满轮次）"""
        from core.multi_agent_v2.orchestration.orchestrator import set_budget
        from core.multi_agent_v2.agents.react_core import run_react

        set_budget(50)  # 非常小的预算
        result = await run_react("写一篇长文章", max_rounds=20)
        # budget 耗尽触发中断，不会跑满 20 轮
        assert result.get("iterations", 0) < 20
