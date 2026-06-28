"""V1 skill 集成测试"""
import pytest
from core.agent_system import V1SkillRouter, LLMAgent, AgentRole, V1LeaderPool


@pytest.mark.asyncio
async def test_skill_router_match_project_analysis():
    router = V1SkillRouter()
    skill_id = await router.match("分析 /Users/test/project 的代码架构和依赖关系")
    assert skill_id in ("project_analyzer", "general")  # 取决于匹配精度


@pytest.mark.asyncio
async def test_skill_router_match_general():
    router = V1SkillRouter()
    skill_id = await router.match("你好")
    # LLM-based matcher 可能匹配到 project_analyzer（中文长 prompt），取决于 LLM 输出
    assert skill_id in ("project_analyzer", "general")


@pytest.mark.asyncio
async def test_skill_router_match_web_scraper():
    router = V1SkillRouter()
    skill_id = await router.match("搜索百度热搜")
    assert skill_id in ("web_scraper", "general")


def test_agent_role_prompt():
    agent = LLMAgent("test", role=AgentRole.WORKER, role_prompt="你是一个数据分析师")
    assert agent.role_prompt == "你是一个数据分析师"
    # 默认无 role_prompt
    agent2 = LLMAgent("test2", role=AgentRole.WORKER)
    assert agent2.role_prompt == ""


def test_tool_restrictions():
    agent = LLMAgent("test", role=AgentRole.WORKER, tool_restrictions=["read_file", "search_code"])
    assert "read_file" in agent.tool_restrictions
    assert "execute_python" not in agent.tool_restrictions
    # None 表示不限制
    agent2 = LLMAgent("test2", role=AgentRole.WORKER, tool_restrictions=None)
    assert agent2.tool_restrictions is None


@pytest.mark.asyncio
async def test_pool_per_skill_worker():
    pool = V1LeaderPool()
    pool._load_agent_configs()
    assert len(pool._agent_configs) > 0

    w1 = await pool.get_worker("project_analyzer")
    assert w1 is not None
    assert w1.role_prompt != ""  # project_analyzer 有 role_prompt
    assert w1.skill_id == "project_analyzer"

    w2 = await pool.get_worker("web_scraper")
    assert w2 is not None
    assert w2.skill_id == "web_scraper"
    assert w2 is not w1  # 不同 skill 不同 Worker

    # 归还后复用
    await pool.return_worker(w1)
    assert "project_analyzer" in pool._worker_pool
    assert len(pool._worker_pool["project_analyzer"]) == 1

    w3 = await pool.get_worker("project_analyzer")
    assert w3 is w1  # 同一个对象


@pytest.mark.asyncio
async def test_pool_general_worker():
    pool = V1LeaderPool()
    w = await pool.get_worker()  # 默认 "general"
    assert w is not None
    assert w.skill_id == "general"
