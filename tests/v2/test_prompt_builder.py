"""PromptBuilder 单元测试"""
import tempfile
import pytest
from pathlib import Path
from core.multi_agent_v2.prompts.builder import (
    PromptBuilder, CircularDependencyError, PromptNotFoundError
)


@pytest.fixture
def builder():
    tmp = Path(tempfile.mkdtemp())
    for d in ["system", "tools", "agents", "blocks"]:
        (tmp / d).mkdir(exist_ok=True)
    (tmp / "system" / "base.txt").write_text("Base prompt content.")
    (tmp / "system" / "code_gen.txt").write_text("Code generation rules.")
    (tmp / "agents" / "explore.txt").write_text("You are an explorer.")
    (tmp / "agents" / "build.txt").write_text("You are a builder.")
    (tmp / "agents" / "work_rules.txt").write_text("Work rules content.")
    (tmp / "blocks" / "status.txt").write_text("Status: {value}")
    (tmp / "tools" / "task.txt").write_text(
        "@requires: agents/explore, agents/build\n"
        "Task description.\n"
        "{{agents/explore}}\n"
        "{{agents/build}}"
    )
    (tmp / "tools" / "circular_a.txt").write_text("@requires: tools/circular_b\nA content.")
    (tmp / "tools" / "circular_b.txt").write_text("@requires: tools/circular_a\nB content.")
    return PromptBuilder(str(tmp))


class TestPromptBuilder:
    def test_load_simple(self, builder):
        assert builder.load("system/base") == "Base prompt content."

    def test_load_cached(self, builder):
        builder.load("system/base")
        assert "system/base" in builder._cache

    def test_load_not_found(self, builder):
        with pytest.raises(PromptNotFoundError):
            builder.load("system/nonexistent")

    def test_load_with_deps(self, builder):
        content = builder.load("tools/task")
        assert "Task description." in content
        assert "You are an explorer." in content
        assert "You are a builder." in content
        assert "{{agents/" not in content

    def test_circular_dependency(self, builder):
        with pytest.raises(CircularDependencyError) as exc:
            builder.load("tools/circular_a")
        assert "circular_a" in str(exc.value)

    def test_assemble_system(self, builder):
        content = builder.assemble_system(["base", "code_gen"])
        assert "Base prompt content." in content
        assert "Code generation rules." in content

    def test_get_tool_desc(self, builder):
        content = builder.get_tool_desc("task")
        assert "Task description." in content
        assert "You are an explorer." in content

    def test_get_agent_prompt(self, builder):
        content = builder.get_agent_prompt("explore")
        assert "You are an explorer." in content
        assert "Work rules content." in content

    def test_get_block_with_vars(self, builder):
        assert builder.get_block("status", value="running") == "Status: running"

    def test_clear_cache(self, builder):
        builder.load("system/base")
        builder.clear_cache()
        assert "system/base" not in builder._cache
