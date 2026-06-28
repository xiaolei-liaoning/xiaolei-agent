"""V1SkillRouter 增强后单元测试"""

import pytest


class TestV1SkillRouter:
    @pytest.mark.asyncio
    async def test_at_skill_routing(self):
        from core.agent_system import V1SkillRouter
        router = V1SkillRouter()
        result = await router.match("@weather 今天天气怎么样")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_general_fallback(self):
        from core.agent_system import V1SkillRouter
        router = V1SkillRouter()
        result = await router.match("你好")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_at_skill_unknown(self):
        from core.agent_system import V1SkillRouter
        router = V1SkillRouter()
        result = await router.match("@nonexistent_skill_12345 做点什么")
        assert isinstance(result, str)
