"""V1ToolRegistry 单元测试"""

import pytest


class TestV1ToolRegistryBasics:
    def test_discover_all_builtins(self):
        from core.agent_v1_tools.v1_tool_registry import V1ToolRegistry
        import asyncio
        reg = V1ToolRegistry()
        tools = asyncio.run(reg.discover_all())
        names = [t.name for t in tools]
        assert "write_file" in names
        assert "read_file" in names
        assert "edit_file" in names
        assert "search_files" in names
        assert "execute_python" in names
        assert "execute_shell" in names
        assert "git" in names
        assert "fetch_url" in names
        assert "web_search" in names
        assert len(names) >= 9

    def test_no_v2_imports(self):
        import importlib
        import sys
        mod = importlib.import_module("core.agent_v1_tools.v1_tool_registry")
        mod_src = mod.__file__
        with open(mod_src) as f:
            src = f.read()
        assert "core.multi_agent_v2" not in src
        assert "core.mcp" not in src


class TestV1ToolRegistryGetHandler:
    def test_get_handler_builtin(self):
        from core.agent_v1_tools.v1_tool_registry import V1ToolRegistry
        import asyncio
        reg = V1ToolRegistry()
        asyncio.run(reg.discover_all())
        handler = reg.get_handler("write_file")
        assert handler is not None
        assert callable(handler)

    def test_get_handler_unknown(self):
        from core.agent_v1_tools.v1_tool_registry import V1ToolRegistry
        reg = V1ToolRegistry()
        assert reg.get_handler("nonexistent_tool") is None


class TestV1ToolRegistryValidateArgs:
    def test_validate_missing_required(self):
        from core.agent_v1_tools.v1_tool_registry import V1ToolRegistry
        import asyncio
        reg = V1ToolRegistry()
        asyncio.run(reg.discover_all())
        valid, msg = reg.validate_arguments("write_file", {})
        assert not valid
        assert "path" in msg

    def test_validate_valid_args(self):
        from core.agent_v1_tools.v1_tool_registry import V1ToolRegistry
        reg = V1ToolRegistry()
        import asyncio
        asyncio.run(reg.discover_all())
        valid, msg = reg.validate_arguments("write_file", {"path": "/tmp/test.txt", "content": "hello"})
        assert valid


class TestV1ToolRegistryGetToolsForTask:
    def test_filter_allowed(self):
        from core.agent_v1_tools.v1_tool_registry import V1ToolRegistry
        reg = V1ToolRegistry()
        import asyncio
        asyncio.run(reg.discover_all())
        tools = asyncio.run(reg.get_tools_for_task("", allowed=["read_file"]))
        names = [t.name for t in tools]
        assert "read_file" in names
        assert "write_file" not in names


class TestV1ToolResult:
    def test_ok(self):
        from core.agent_v1_tools.v1_tool_result import ok
        r = ok("hello")
        assert r == {"ok": True, "data": "hello"}

    def test_err(self):
        from core.agent_v1_tools.v1_tool_result import err
        r = err("something went wrong")
        assert r == {"ok": False, "error": "something went wrong"}

    def test_is_ok(self):
        from core.agent_v1_tools.v1_tool_result import is_ok
        assert is_ok({"ok": True, "data": "x"})
        assert not is_ok({"ok": False, "error": "x"})

    def test_from_handler(self):
        from core.agent_v1_tools.v1_tool_result import from_handler
        assert from_handler({"ok": True, "data": "hello"}) == "hello"
        assert from_handler(None) == ""
        assert from_handler("raw") == "raw"


class TestV1HtmlParser:
    def test_html_to_text(self):
        from core.agent_v1_tools.v1_html_parser import html_to_text
        assert "Hello" in html_to_text("<html><body><p>Hello</p></body></html>")
        assert html_to_text("") == ""

    def test_no_v2_imports(self):
        import importlib
        mod = importlib.import_module("core.agent_v1_tools.v1_html_parser")
        with open(mod.__file__) as f:
            src = f.read()
        assert "core.multi_agent_v2" not in src
