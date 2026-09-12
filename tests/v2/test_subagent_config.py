"""子代理配置验证 — 不依赖LLM，只验证配置正确性

测试目标：
  1. 所有 profile 能正确加载
  2. task/orchestrate 工具描述包含触发条件
  3. read_write profile 存在且权限正确
  4. prompts 文件存在且可加载
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class TestSubagentProfiles:
    """验证子代理 profile 配置"""

    def test_all_profiles_exist(self):
        from core.multi_agent_v2.agents.subagent.types import AgentProfile
        expected = {"explore", "build", "general", "analyze", "read_write", "orchestrator"}
        actual = {p.value for p in AgentProfile}
        assert expected == actual, f"Profile 不匹配: expected={expected}, actual={actual}"

    def test_read_write_permissions(self):
        from core.multi_agent_v2.agents.subagent.types import AgentProfile, PROFILE_PERMISSIONS
        perm = PROFILE_PERMISSIONS[AgentProfile.READ_WRITE]
        # read_write 应该只禁 execute_python
        assert perm["disallowed"] == ["execute_python"], f"Unexpected disallowed: {perm['disallowed']}"
        # 应该能读文件、写文件、执行shell、调子代理
        assert "write_file" not in perm["disallowed"]
        assert "edit_file" not in perm["disallowed"]
        assert "execute_shell" not in perm["disallowed"]
        assert "task" not in perm["disallowed"]
        assert "orchestrate" not in perm["disallowed"]

    def test_analyze_permissions(self):
        from core.multi_agent_v2.agents.subagent.types import AgentProfile, PROFILE_PERMISSIONS
        perm = PROFILE_PERMISSIONS[AgentProfile.ANALYZE]
        # analyze 是只读的
        assert "write_file" in perm["disallowed"]
        assert "edit_file" in perm["disallowed"]
        assert "execute_shell" in perm["disallowed"]
        assert "execute_python" in perm["disallowed"]
        # 但能调子代理
        assert "task" not in perm["disallowed"]
        assert "orchestrate" not in perm["disallowed"]

    def test_explore_permissions(self):
        from core.multi_agent_v2.agents.subagent.types import AgentProfile, PROFILE_PERMISSIONS
        perm = PROFILE_PERMISSIONS[AgentProfile.EXPLORE]
        # explore 也是只读的
        assert "write_file" in perm["disallowed"]
        assert "edit_file" in perm["disallowed"]
        assert "execute_shell" in perm["disallowed"]

    def test_build_permissions(self):
        from core.multi_agent_v2.agents.subagent.types import AgentProfile, PROFILE_PERMISSIONS
        perm = PROFILE_PERMISSIONS[AgentProfile.BUILD]
        # build 全能力但不能派更深子代理（防递归由 spawn.py 保证）
        assert perm["disallowed"] == []

    def test_orchestrator_permissions(self):
        from core.multi_agent_v2.agents.subagent.types import AgentProfile, PROFILE_PERMISSIONS
        perm = PROFILE_PERMISSIONS[AgentProfile.ORCHESTRATOR]
        # orchestrator 不能直接写文件
        assert "write_file" in perm["disallowed"]
        assert "edit_file" in perm["disallowed"]
        # 但能调子代理
        assert "task" not in perm["disallowed"]
        assert "orchestrate" not in perm["disallowed"]


class TestPromptFiles:
    """验证 prompts 文件存在且可加载"""

    def test_read_write_prompt_exists(self):
        from core.multi_agent_v2.prompts.builder import get_builder
        builder = get_builder()
        prompt = builder.get_agent_prompt("read_write")
        assert len(prompt) > 500, f"read_write prompt too short: {len(prompt)}"
        assert "read-write" in prompt.lower() or "分析" in prompt or "analyst" in prompt.lower()

    def test_analyze_prompt_has_subagent_guidance(self):
        from core.multi_agent_v2.prompts.builder import get_builder
        builder = get_builder()
        prompt = builder.get_agent_prompt("analyze")
        assert "CRITICAL" in prompt or "sub-agent" in prompt.lower() or "task tool" in prompt

    def test_task_tool_desc_has_triggers(self):
        from core.multi_agent_v2.prompts.builder import get_builder
        builder = get_builder()
        desc = builder.get_tool_desc("task")
        # 应该包含触发条件
        assert len(desc) > 2000, f"task description too short: {len(desc)}"
        assert "子代理" in desc or "sub-agent" in desc.lower()
        assert "analyze" in desc.lower()
        assert "read_write" in desc

    def test_orchestrate_tool_desc_loaded(self):
        from core.multi_agent_v2.prompts.builder import get_builder
        builder = get_builder()
        desc = builder.get_tool_desc("orchestrate")
        assert len(desc) > 1000, f"orchestrate description too short: {len(desc)}"


class TestToolRegistry:
    """验证工具注册表"""

    def test_task_tool_registered(self):
        from core.multi_agent_v2.tools.tool_registry import ToolRegistry
        reg = ToolRegistry()
        # 不需要 await discover_all，直接检查工具定义
        task_def = reg._tools.get("task") if hasattr(reg, '_tools') else None
        # 如果 _tools 为空（未初始化），检查 class-level 定义
        if task_def is None:
            # 从源码检查是否有 task 定义
            import core.multi_agent_v2.tools.tool_registry as tr
            assert hasattr(tr, '_SANDBOX_TOOL_DEFS')
            names = [t.name for t in tr._SANDBOX_TOOL_DEFS]
            assert "task" in names, "task 工具未注册"

    def test_read_write_in_tool_choices(self):
        """read_write 应该是 task 工具的合法 subagent_type"""
        from core.multi_agent_v2.agents.subagent.types import AgentProfile
        assert AgentProfile.READ_WRITE == "read_write"
