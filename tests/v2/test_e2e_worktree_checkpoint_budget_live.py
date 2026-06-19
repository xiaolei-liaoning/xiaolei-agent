"""真实场景 E2E 测试：Worktree 隔离 + Checkpoint + Budget 共享

直接在真实 git 仓库、真实 SQLite、真实 BudgetTracker 上运行。
可独立执行：python3 -m pytest 本文件 -v --tb=short
"""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

# ╔══════════════════════════════════════════════════════════════╗
# ║  场景 1: Worktree 隔离                                      ║
# ║  真实 git repo → 创建 worktree → 写文件 → merge → 清理     ║
# ╚══════════════════════════════════════════════════════════════╝


class TestWorktreeE2E:
    """真实的 git worktree 隔离 E2E"""

    @pytest.fixture
    def git_repo(self):
        """创建临时 git 仓库作为测试环境"""
        tmp = Path(tempfile.mkdtemp(suffix="_e2e_wt"))
        subprocess.run(["git", "init"], cwd=tmp, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"],
                       cwd=tmp, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"],
                       cwd=tmp, capture_output=True)
        # 创建初始 commit（git worktree 需要）
        (tmp / "README.md").write_text("# Test Repo")
        subprocess.run(["git", "add", "-A"], cwd=tmp, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"],
                       cwd=tmp, capture_output=True, check=True)
        yield tmp
        shutil.rmtree(tmp, ignore_errors=True)

    def test_worktree_create_and_resolve_path(self, git_repo):
        """① 创建 worktree → resolve_path 映射到 worktree 内"""
        from core.multi_agent_v2.infrastructure.worktree_isolator import (
            WorktreeIsolator,
        )

        wt = WorktreeIsolator.create(str(git_repo), "e2e_write_file")
        assert wt is not None, "git repo 应成功创建 worktree"
        assert os.path.isdir(wt.worktree_path), "worktree 目录应存在"

        # resolve_path：repo 内路径映射到 worktree
        original = os.path.join(git_repo, "Desktop", "test.txt")
        resolved = wt.resolve_path(original)
        assert resolved.startswith(wt.worktree_path), f"应映射到 worktree: {resolved}"
        assert resolved.endswith("Desktop/test.txt"), f"应保留相对路径: {resolved}"

        # resolve_path：repo 外路径（如 ~/Desktop）不映射
        home_file = os.path.expanduser("~/Desktop/outside.txt")
        assert wt.resolve_path(home_file) == home_file, "repo 外路径不应映射"

        wt.cleanup()
        assert not os.path.isdir(wt.worktree_path), "worktree 目录应被清理"

    def test_worktree_write_file_redirect(self, git_repo):
        """② 通过 worktree 重定向写文件，主仓库不受影响"""
        from core.multi_agent_v2.infrastructure.worktree_isolator import (
            WorktreeIsolator,
            set_active_worktree,
            get_active_worktree,
        )

        wt = WorktreeIsolator.create(str(git_repo), "e2e_write")
        assert wt is not None

        set_active_worktree(wt)
        assert get_active_worktree() is not None

        # 模拟 write_file 的行为：通过 resolve_path 重定向
        target_in_repo = os.path.join(git_repo, "src", "output.txt")
        actual_path = wt.resolve_path(target_in_repo)

        # 确保 worktree 内的 src/ 目录存在
        os.makedirs(os.path.dirname(actual_path), exist_ok=True)
        with open(actual_path, "w") as f:
            f.write("worktree content")

        # 验证：主仓库没有该文件
        assert not os.path.exists(target_in_repo), "主仓库不应有 worktree 写入的文件"

        # 验证：worktree 里有
        assert os.path.exists(actual_path), "worktree 内应有文件"
        assert open(actual_path).read() == "worktree content", "文件内容应正确"

        set_active_worktree(None)
        wt.cleanup()

    def test_worktree_merge_back(self, git_repo):
        """③ merge_back 将 worktree 变更合并回主仓库"""
        from core.multi_agent_v2.infrastructure.worktree_isolator import (
            WorktreeIsolator,
        )

        wt = WorktreeIsolator.create(str(git_repo), "e2e_merge")
        assert wt is not None

        # 在 worktree 里写文件
        test_file = os.path.join(git_repo, "merged_file.txt")
        wt_path = wt.resolve_path(test_file)
        os.makedirs(os.path.dirname(wt_path), exist_ok=True)
        with open(wt_path, "w") as f:
            f.write("merged content")
        with open(os.path.join(str(git_repo), "worktree_marker.txt"), "w") as f:
            f.write("wt marker")

        # merge_back
        asyncio.get_event_loop().run_until_complete(wt.merge_back())

        # 验证：主仓库有了，且文件名相同
        # cherry-pick --no-commit 会把文件放到工作区但不会 commit
        status = subprocess.run(["git", "status", "--porcelain"],
                                cwd=str(git_repo), capture_output=True, text=True)
        assert "merged_file.txt" in status.stdout, \
            f"合并后主仓库应有 merged_file.txt\n{status.stdout}"

        wt.cleanup()


# ╔══════════════════════════════════════════════════════════════╗
# ║  场景 2: Resume Checkpoint                                  ║
# ║  真实 SQLite → 多次保存 → 读取 → 恢复                       ║
# ╚══════════════════════════════════════════════════════════════╝


class TestCheckpointE2E:
    """真实的 checkpoint 持久化 E2E"""

    def test_checkpoint_persists_across_store_instances(self, tmp_path):
        """① 不同 ConversationStore 实例间数据持久"""
        from core.multi_agent_v2.agents.conversation_store import (
            ConversationStore,
        )

        db = str(tmp_path / "persist_test.db")
        sid = "e2e_persist"

        # 实例 A：保存
        store_a = ConversationStore(db)
        store_a.save_checkpoint(sid, 5, {"round": 5, "answer": "partial"})

        # 实例 B：读取（不同实例，同一 db 文件）
        store_b = ConversationStore(db)
        cp = store_b.load_latest_checkpoint(sid)
        assert cp is not None, "跨实例应能读取 checkpoint"
        assert cp["round_num"] == 5
        assert cp["state"]["answer"] == "partial"

    def test_checkpoint_incremental_saves(self, tmp_path):
        """② 多轮保存，最新覆盖旧"""
        from core.multi_agent_v2.agents.conversation_store import (
            ConversationStore,
        )

        db = str(tmp_path / "incr_test.db")
        store = ConversationStore(db)
        sid = "e2e_incremental"

        for i in range(1, 6):
            store.save_checkpoint(sid, i, {"round": i, "ts": time.time()})

        cp = store.load_latest_checkpoint(sid)
        assert cp["round_num"] == 5, f"应读取到最新，实际是 {cp['round_num']}"

        cps = store.list_checkpoints(sid)
        assert len(cps) == 5, "所有 checkpoint 都应保留"

        store.delete_checkpoints(sid)
        assert store.load_latest_checkpoint(sid) is None, "删除后应为空"

    def test_checkpoint_ignores_other_sessions(self, tmp_path):
        """③ 不同 session_id 的 checkpoint 互不干扰"""
        from core.multi_agent_v2.agents.conversation_store import (
            ConversationStore,
        )

        db = str(tmp_path / "multi_session.db")
        store = ConversationStore(db)

        store.save_checkpoint("session_a", 1, {"data": "a1"})
        store.save_checkpoint("session_a", 2, {"data": "a2"})
        store.save_checkpoint("session_b", 1, {"data": "b1"})

        cp_a = store.load_latest_checkpoint("session_a")
        assert cp_a["round_num"] == 2
        assert cp_a["state"]["data"] == "a2"

        cp_b = store.load_latest_checkpoint("session_b")
        assert cp_b["round_num"] == 1
        assert cp_b["state"]["data"] == "b1"

        # session_b 有自己的 checkpoint，不受 session_a 影响
        assert len(store.list_checkpoints("session_b")) == 1
        assert len(store.list_checkpoints("session_a")) == 2

    def test_checkpoint_with_large_state(self, tmp_path):
        """④ 大状态数据正常序列化"""
        from core.multi_agent_v2.agents.conversation_store import (
            ConversationStore,
        )

        db = str(tmp_path / "large_state.db")
        store = ConversationStore(db)
        sid = "e2e_large"

        large_state = {
            "round_num": 10,
            "big_string": "x" * 5000,
            "list_data": [{"tool": "write_file", "path": f"/tmp/test_{i}.txt"}
                          for i in range(100)],
            "nested": {"a": {"b": {"c": "deep"}}},
        }
        store.save_checkpoint(sid, 10, large_state)

        cp = store.load_latest_checkpoint(sid)
        assert cp["state"]["round_num"] == 10
        assert len(cp["state"]["big_string"]) == 5000
        assert len(cp["state"]["list_data"]) == 100
        assert cp["state"]["nested"]["a"]["b"]["c"] == "deep"


# ╔══════════════════════════════════════════════════════════════╗
# ║  场景 3: Budget 共享                                        ║
# ║  真实共享额度 → 主+子 Agent 扣费 → 耗尽后阻断              ║
# ╚══════════════════════════════════════════════════════════════╝


class TestBudgetSharingE2E:
    """真实的 budget 共享 E2E"""

    def test_shared_budget_blocks_sub_agent_when_exhausted(self):
        """① 主 Agent 花光预算 → 子 Agent 应被阻断"""
        from core.multi_agent_v2.orchestration.orchestrator import (
            set_budget, get_budget, BudgetTracker,
        )

        # 模拟主 Agent 启动时设置共享预算
        set_budget(1000)
        bt = get_budget()
        assert bt is not None

        # 主 Agent 执行，花了 900
        bt.spend(500, "main_round_1")
        bt.spend(400, "main_round_2")
        assert bt.remaining() == 100

        # 子 Agent 启动前检查
        assert bt.has_budget() is True  # 还有 100

        # 子 Agent 执行，花了 100
        bt.spend(100, "sub_agent")
        assert bt.remaining() == 0
        assert bt.has_budget() is False

        # 第二个子 Agent 启动前检查 → 被阻断
        assert bt.has_budget() is False, "预算已耗尽，子 Agent 应被阻断"

    def test_budget_does_not_go_negative(self):
        """② overspend 后 remaining 为 0，不出现负数"""
        from core.multi_agent_v2.orchestration.orchestrator import BudgetTracker
        bt = BudgetTracker(total_budget=100)
        bt.spend(200)
        assert bt.remaining() == 0
        assert bt.has_budget() is False

    def test_unlimited_budget_never_exhausts(self):
        """③ total_budget=None 永不耗尽"""
        from core.multi_agent_v2.orchestration.orchestrator import BudgetTracker
        bt = BudgetTracker(total_budget=None)
        for _ in range(1000):
            bt.spend(10000, "heavy_call")
        assert bt.has_budget() is True
        assert bt.remaining() == float("inf")

    def test_global_budget_is_singleton(self):
        """④ set_budget/get_budget 是全局单例"""
        from core.multi_agent_v2.orchestration.orchestrator import (
            set_budget, get_budget,
        )

        set_budget(50000)
        bt1 = get_budget()
        bt2 = get_budget()
        assert bt1 is bt2, "get_budget 应返回同一实例"

        bt1.spend(10000)
        assert bt2.remaining() == 40000, "通过 bt1 扣费后 bt2 也应看到"

    def test_budget_exceeded_exception_works(self):
        """⑤ BudgetExceeded 异常可被捕获"""
        from core.multi_agent_v2.orchestration.orchestrator import (
            BudgetExceeded,
        )

        try:
            raise BudgetExceeded("额度耗尽")
        except BudgetExceeded as e:
            assert "额度耗尽" in str(e)

    def test_budget_records_by_label(self):
        """⑥ 按 label 追踪每笔花费"""
        from core.multi_agent_v2.orchestration.orchestrator import BudgetTracker
        bt = BudgetTracker(total_budget=10000)
        bt.spend(3000, "search_agent")
        bt.spend(2000, "coding_agent")
        labels = [r["label"] for r in bt._records]
        assert "search_agent" in labels
        assert "coding_agent" in labels


# ╔══════════════════════════════════════════════════════════════╗
# ║  场景 4: 三者组合                                            ║
# ║  worktree + checkpoint + budget 同时运作不冲突              ║
# ╚══════════════════════════════════════════════════════════════╝


class TestAllThreeCombined:
    """三者同时工作的集成验证"""

    def test_three_features_independent_globals(self):
        """worktree/budget/checkpoint 用各自独立全局变量，互不冲突"""
        from core.multi_agent_v2.infrastructure.worktree_isolator import (
            set_active_worktree, get_active_worktree,
        )
        from core.multi_agent_v2.orchestration.orchestrator import (
            set_budget, get_budget,
        )
        from core.multi_agent_v2.agents.conversation_store import (
            ConversationStore,
        )

        # 同时设置三者
        set_budget(50000)
        set_active_worktree("my_wt")
        store = ConversationStore("/tmp/_e2e_combined_test.db")
        try:
            store.save_checkpoint("combined_session", 1, {"step": 1})

            # 验证各自独立
            assert get_budget().remaining() == 50000
            assert get_active_worktree() == "my_wt"
            cp = store.load_latest_checkpoint("combined_session")
            assert cp["state"]["step"] == 1
        finally:
            set_active_worktree(None)
            store.delete_checkpoints("combined_session")
            if os.path.exists("/tmp/_e2e_combined_test.db"):
                os.remove("/tmp/_e2e_combined_test.db")
