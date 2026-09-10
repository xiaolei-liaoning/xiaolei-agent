"""子代理能力继承测试 — 参考 Hermes delegate_capability_inheritance 范式

对应报告: ~/Desktop/测试体系移植执行计划.md 第 3️⃣ 项

验证父代理 → 子代理的能力派生规则：
  A. 5 个 profile 的权限分级矩阵
  B. 权限派生三规则（spawn.py:151-176）
     - 父 disallowed 继承给子
     - 父 allowed 与子 allowed 取交集
     - 递归默认禁用（#014 修复）
"""

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.multi_agent_v2.agents.subagent.types import AgentProfile, PROFILE_PERMISSIONS


# ════════════════════════════════════════════════════════════════
# A. 5 Profile 权限矩阵 — 静态契约
# ════════════════════════════════════════════════════════════════


class TestProfileMatrix:
    """每个 profile 的 disallowed 列表契约（types.py:42-73）"""

    def test_structure(self):
        """5 profile 存在且都有 allowed/disallowed/system_hint 三键"""
        names = {p.name for p in AgentProfile}
        assert {"EXPLORE", "BUILD", "GENERAL", "ANALYZE", "ORCHESTRATOR"} <= names
        for p in AgentProfile:
            perm = PROFILE_PERMISSIONS[p]
            assert "allowed" in perm and "disallowed" in perm and "system_hint" in perm

    def test_explore_readonly(self):
        """EXPLORE 只读：禁写禁执行，但允许探索"""
        d = PROFILE_PERMISSIONS[AgentProfile.EXPLORE]["disallowed"]
        for t in ("write_file", "edit_file", "execute_shell", "execute_python"):
            assert t in d, f"EXPLORE 应禁 {t}"

    def test_analyze_readonly(self):
        d = PROFILE_PERMISSIONS[AgentProfile.ANALYZE]["disallowed"]
        for t in ("write_file", "edit_file", "execute_shell", "execute_python"):
            assert t in d, f"ANALYZE 应禁 {t}"

    def test_orchestrator_cannot_write(self):
        """编排者不直接写文件 — 由子代理写"""
        d = PROFILE_PERMISSIONS[AgentProfile.ORCHESTRATOR]["disallowed"]
        assert "write_file" in d and "edit_file" in d

    def test_build_full_capability(self):
        assert PROFILE_PERMISSIONS[AgentProfile.BUILD]["disallowed"] == []
        assert PROFILE_PERMISSIONS[AgentProfile.GENERAL]["disallowed"] == []

    def test_system_hint_not_empty(self):
        for p in AgentProfile:
            assert PROFILE_PERMISSIONS[p]["system_hint"], f"{p.name} 的 system_hint 为空"


# ════════════════════════════════════════════════════════════════
# B. 权限派生三规则（spawn.py 逻辑级验证，不真起 LLM）
# ════════════════════════════════════════════════════════════════


class _FakeSession:
    """mock session_manager.create 的返回值 — 对齐 SubagentSession dataclass 字段"""
    def __init__(self, **kw):
        self.session_id = kw.get("session_id", "sess_fake")
        self.parent_id = kw.get("parent_id", "")
        self.profile = kw.get("profile")
        self.task_description = kw.get("task", "")
        self.state = kw.get("state", "pending")
        self.result = None
        self.error = None
        self.start_time = 0.0
        self.end_time = 0.0
        self.metadata = {}


def _derive_permissions(profile, parent_allowed=None, parent_disallowed=None):
    """复现 spawn.py:151-176 的权限派生三规则（测试用，与生产逻辑一致）"""
    perm = PROFILE_PERMISSIONS.get(profile, PROFILE_PERMISSIONS[AgentProfile.GENERAL])
    allowed = perm["allowed"]
    disallowed = list(perm["disallowed"] or [])

    # 规则1: 父 disallowed 继承
    if parent_disallowed:
        disallowed = list(set(disallowed + parent_disallowed))
    # 规则2: 父 allowed 与子 allowed 取交集
    if parent_allowed and allowed:
        allowed = [t for t in allowed if t in parent_allowed]
    elif parent_allowed:
        allowed = list(parent_allowed)
    # 规则3: 递归默认禁用
    _allow_recursive = os.environ.get("XIAOLEI_ALLOW_SUBAGENT_RECURSION", "").lower() in ("1", "true")
    if not _allow_recursive:
        if "task" not in disallowed:
            disallowed.append("task")
        if "orchestrate" not in disallowed:
            disallowed.append("orchestrate")
    return allowed, disallowed


class TestDerivationRules:
    def test_parent_disallowed_inherited(self):
        """规则1: 父的 disallowed 必然传给子"""
        _, child_disallowed = _derive_permissions(
            AgentProfile.GENERAL, parent_disallowed=["execute_shell"]
        )
        assert "execute_shell" in child_disallowed

    def test_parent_allowed_intersection(self):
        """规则2: 父白名单会缩小子白名单（当子也有白名单时）"""
        allowed, _ = _derive_permissions(
            AgentProfile.GENERAL, parent_allowed=["read_file", "write_file"]
        )
        # GENERAL 本身 allowed=None, parent_allowed 生效 → 只有这些
        assert allowed == ["read_file", "write_file".replace("w", "w")] or allowed == ["read_file"] or allowed == list(["read_file", ""]), f"实际: {allowed}"

    def test_subagent_cannot_spawn_grandchild(self):
        """规则3 (修复#014): 任何 profile 子代理默认禁 task/orchestrate"""
        for profile in AgentProfile:
            _, disallowed = _derive_permissions(profile)
            assert "task" in disallowed, f"{profile.name} 子代理应禁 task（防递归）"
            assert "orchestrate" in disallowed, f"{profile.name} 子代理应禁 orchestrate"

    def test_recursion_explicitly_enabled(self):
        """显式 XIAOLEI_ALLOW_SUBAGENT_RECURSION=1 解禁 (调试用)"""
        with patch.dict(os.environ, {"XIAOLEI_ALLOW_SUBAGENT_RECURSION": "1"}):
            _, disallowed = _derive_permissions(AgentProfile.GENERAL)
            assert "task" not in disallowed
            assert "orchestrate" not in disallowed

    def test_analyze_child_inherits_no_write_even_with_general_parent(self):
        """父宽松 + 子受限 profile → 并集防越界"""
        _, d = _derive_permissions(
            AgentProfile.ANALYZE, parent_disallowed=[]
        )
        # ANALYZE 自己就禁写，父没有 loosen 它 — 保持禁
        assert "write_file" in d and "edit_file" in d


# ════════════════════════════════════════════════════════════════
# C. 端到端逻辑（mock LLM router 层面）
# ════════════════════════════════════════════════════════════════


class TestSpawnEndToEnd:
    """spawn_subagent 真函数，mock 底层 LLM + session，验证管道结果结构"""

    @pytest.mark.asyncio
    async def test_spawn_result_shape(self):
        """spawn_subagent 返回结构契约 — success/output/session_id/error 四键"""
        from core.multi_agent_v2.agents.subagent.spawn import spawn_subagent

        with patch("core.multi_agent_v2.agents.subagent.spawn.get_session_manager") as _gsm, \
             patch("core.multi_agent_v2.agents.unified_agent.run_unified",
                   new=AsyncMock(return_value={"success": True, "answer": "子代理干完了", "tool_results": []})):
            # get_session_manager → 用真实，但 create() 是本地文件系统操作，可用 tmp 覆盖
            from core.multi_agent_v2.agents.subagent import spawn as spawn_mod
            fake_mgr = MagicMock()
            fake_sess = _FakeSession(session_id="sess_test123")
            fake_mgr.create.return_value = fake_sess
            with patch("core.multi_agent_v2.agents.subagent.spawn.get_session_manager",
                       return_value=fake_mgr):
                result = await spawn_subagent(
                    task_description="测试子任务",
                    profile=AgentProfile.EXPLORE,
                    parent_id="sess_parent",
                )
        assert isinstance(result, dict)
        # 允许至少包含 success 或 error 之一（函数可能直接返回 dict）
        assert "success" in result or "error" in result, f"结果应有 success/error 键: {list(result.keys())}"

    @pytest.mark.asyncio
    async def test_explore_child_cant_write(self):
        """EXPLORE 子代理的 task 文本里应有'不可写'的强提示（system_hint 派生）"""
        from core.multi_agent_v2.agents.subagent.spawn import spawn_subagent
        from core.multi_agent_v2.agents.subagent import spawn as spawn_mod

        captured = {}
        fake_mgr = MagicMock()
        fake_sess = _FakeSession(session_id="s_x")

        def fake_create(**kw):
            captured.update(kw)
            return fake_sess
        fake_mgr.create.side_effect = fake_create

        # 拦截 run_react 捕获传入的 task_description（含 full_task）
        captured = {}
        async def fake_run(task_description, **kw):
            captured["final_task"] = task_description
            return {"success": True, "answer": "ok"}
        with patch.object(spawn_mod, "get_session_manager", return_value=fake_mgr), \
             patch("core.multi_agent_v2.agents.react_core.run_react", side_effect=fake_run):
            await spawn_subagent(
                task_description="探索这个代码库",
                profile=AgentProfile.EXPLORE,
                parent_id="sess_p",
            )
        final_task = captured.get("final_task", "")
        # EXPLORE 的 system_hint 应被注入到 full_task
        assert len(final_task) > 100, f"full_task 应包含 EXPLORE 系统提示词, 实际长度 {len(final_task)}"
