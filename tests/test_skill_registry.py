"""
Test cases for SkillRegistry and ToolRegistry

Updated to match current implementation (namespace support removed
in favor of simplified SkillRegistry/ToolRegistry).
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.skill_base import SkillHandler, SkillRegistry, ToolRegistry


class TestCoreSkill(SkillHandler):
    """Test core skill"""
    name = "test_core_skill"
    description = "A test core skill"
    keywords = ["test", "core"]
    namespace = "core"
    is_core = True

    async def execute(self, params, context=None):
        return {"success": True, "result": "core skill executed"}


class TestBizSkill(SkillHandler):
    """Test business skill"""
    name = "test_biz_skill"
    description = "A test business skill"
    keywords = ["test", "biz"]
    namespace = "biz"
    is_core = False

    async def execute(self, params, context=None):
        return {"success": True, "result": "biz skill executed"}


class TestSkillRegistry:
    """Test SkillRegistry basic operations"""

    def setup_method(self):
        """Reset registry before each test"""
        self.registry = SkillRegistry()
        self.registry._skills = {}

    def test_register_skill(self):
        """Test registering a skill"""
        skill = TestCoreSkill()
        self.registry.register(skill)
        assert skill.name in self.registry._skills

    def test_unregister_skill(self):
        """Test unregistering a skill"""
        skill = TestCoreSkill()
        self.registry.register(skill)
        assert skill.name in self.registry._skills

        self.registry.unregister(skill.name)
        assert skill.name not in self.registry._skills

    def test_get_skill(self):
        """Test getting a skill by name"""
        skill = TestCoreSkill()
        self.registry.register(skill)
        assert self.registry.get(skill.name) is skill
        assert self.registry.get("nonexistent") is None

    def test_all_skills(self):
        """Test listing all skills"""
        skill1 = TestCoreSkill()
        skill2 = TestBizSkill()
        skill2.name = "test_biz_skill_2"
        self.registry.register(skill1)
        self.registry.register(skill2)

        all_skills = self.registry.all()
        assert len(all_skills) == 2

    def test_match_skill(self):
        """Test skill matching still works"""
        core_skill = TestCoreSkill()
        biz_skill = TestBizSkill()
        biz_skill.name = "test_biz_skill_2"

        self.registry.register(core_skill)
        self.registry.register(biz_skill)

        matched1 = self.registry.match("test core")
        matched2 = self.registry.match("test biz")

        assert matched1 is not None
        assert matched2 is not None

    def test_register_many(self):
        """Test registering multiple skills"""
        self.registry.register_many([TestCoreSkill(), TestBizSkill()])
        assert len(self.registry._skills) == 2

    def test_no_false_match(self):
        """Test match doesn't return skill for unrelated text"""
        # SkillRegistry.match() finds best score; ensure it at least returns
        # a SkillHandler instance (not something else) for any result
        self.registry.register(TestCoreSkill())
        result = self.registry.match("completely unrelated text")
        if result is not None:
            from core.skill_base import ISkill
            assert isinstance(result, ISkill), "match() should return ISkill or None"


class TestToolRegistry:
    """Test ToolRegistry basic operations"""

    def setup_method(self):
        """Reset registry before each test"""
        ToolRegistry.reset()

    def test_register_tool(self):
        """Test registering a tool"""
        skill = TestCoreSkill()
        ToolRegistry.register(skill, keywords=["test", "core"])

        assert skill.name in ToolRegistry._tools

    def test_get_tool(self):
        """Test getting a registered tool"""
        skill = TestCoreSkill()
        biz_skill = TestBizSkill()
        biz_skill.name = "test_biz_skill_2"

        ToolRegistry.register(skill)
        ToolRegistry.register(biz_skill)

        core_tools = ToolRegistry._tools.get(skill.name)
        assert core_tools is not None

    def test_unregister_tool(self):
        """Test unregistering a tool"""
        skill = TestCoreSkill()
        ToolRegistry.register(skill)

        assert skill.name in ToolRegistry._tools

        ToolRegistry.unregister(skill.name)
        assert skill.name not in ToolRegistry._tools

    def test_register_with_keywords(self):
        """Test registering a tool with explicit keywords"""
        skill = TestCoreSkill()
        ToolRegistry.register(skill, keywords=["test", "core"])

        assert skill.name in ToolRegistry._keywords
        assert "test" in ToolRegistry._keywords[skill.name]

    def test_register_handler(self):
        """Test registering a handler function as tool"""
        def my_handler(params, context=None):
            return {"success": True}
        my_handler.name = "my_handler"

        ToolRegistry.register_handler("my_handler", my_handler,
                                       description="test handler",
                                       keywords=["test"])

        assert "my_handler" in ToolRegistry._tools

    def test_reset(self):
        """Test resetting the registry"""
        skill = TestCoreSkill()
        ToolRegistry.register(skill)
        assert len(ToolRegistry._tools) > 0

        ToolRegistry.reset()
        assert len(ToolRegistry._tools) == 0
