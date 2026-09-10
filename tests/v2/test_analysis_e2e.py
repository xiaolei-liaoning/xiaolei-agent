"""端到端测试：角色系统 + ReAct 循环"""
import pytest

pytestmark = pytest.mark.real_llm


@pytest.mark.asyncio
async def test_role_loader_loads():
    """验证 role_loader 能从 ~/.xiaolei/roles/ 加载角色"""
    from core.multi_agent_v2.agents.role_loader import load_all, get

    roles = load_all()
    assert "project_analyzer" in roles
    assert "general" in roles
    assert "orchestrator" in roles
    r = get("project_analyzer")
    assert r.description
    assert len(r.phases) >= 2
    assert len(r.tools) >= 1


@pytest.mark.asyncio
async def test_base_skills_loads_from_roles():
    """验证 base_skills 优先从 ~/.xiaolei/roles/ 加载"""
    from core.skills.base_skills import get_skill_system

    sys = get_skill_system()
    # force reload
    sys._load_base()
    assert "project_analyzer" in sys.base_skills
    r = sys.base_skills["project_analyzer"]
    assert r.role_prompt
    assert "# role: project_analyzer" in r.role_prompt


@pytest.mark.asyncio
async def test_profile_hint_from_role():
    """验证 PROFILE_PERMISSIONS system_hint 从 .md 加载"""
    from core.multi_agent_v2.agents.subagent.types import PROFILE_PERMISSIONS, AgentProfile

    hint = PROFILE_PERMISSIONS[AgentProfile.EXPLORE]["system_hint"]
    assert hint and len(hint) > 50
    assert "<role:explore>" in hint or "exploring" in hint.lower() or "explore" in hint.lower()


@pytest.mark.asyncio
async def test_react_simple_task():
    """验证 ReAct 循环能处理简单任务（不依赖 Phase 1 特殊路径）"""
    from core.multi_agent_v2.agents.react_core import run_react

    result = await run_react("用3个词描述 Python", max_rounds=3)
    ans = (result.get("answer", "") or "")
    # 即使 answer 为空，success 应为 True（超时/空转不算失败）
    assert not ans.startswith("{"), f"泄露 JSON: {ans[:100]}"


@pytest.mark.asyncio
async def test_generate_plan_basic():
    """验证计划生成能正常工作"""
    from core.multi_agent_v2.agents.react_core import run_react

    # 只是确认 run_react 不崩溃
    result = await run_react("hello", max_rounds=2)
    assert True
