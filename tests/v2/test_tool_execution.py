"""
Tool Handler 执行测试 — 覆盖 9 个 V2 内置工具

测试策略:
  - 文件操作: tmp_path 真实文件系统
  - 网络操作: patch _http_get + 解析器
  - 代码执行: patch SandboxExecutor
  - Git: patch asyncio.create_subprocess_exec
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════
# read_file
# ═══════════════════════════════════════════════════════════════

class TestReadFile:
    @pytest.mark.asyncio
    async def test_read_existing_file(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_read_file
        f = tmp_path / "test.txt"
        f.write_text("hello\nworld\n")
        result = await _handle_read_file({"path": str(f)})
        assert result["ok"] is True
        assert "hello" in result["data"]

    @pytest.mark.asyncio
    async def test_read_with_offset_limit(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_read_file
        f = tmp_path / "test.txt"
        f.write_text("\n".join(f"line{i}" for i in range(100)))
        result = await _handle_read_file({"path": str(f), "offset": 5, "limit": 3})
        assert result["ok"] is True
        assert "line4" in result["data"]

    @pytest.mark.asyncio
    async def test_read_directory(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_read_file
        (tmp_path / "a.txt").write_text("")
        (tmp_path / "b.txt").write_text("")
        result = await _handle_read_file({"path": str(tmp_path)})
        assert result["ok"] is True
        assert "a.txt" in result["data"]

    @pytest.mark.asyncio
    async def test_read_nonexistent(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_read_file
        result = await _handle_read_file({"path": str(tmp_path / "nope.txt")})
        assert result["ok"] is False
        assert "不存在" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_path(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_read_file
        result = await _handle_read_file({})
        assert result["ok"] is False


# ═══════════════════════════════════════════════════════════════
# write_file
# ═══════════════════════════════════════════════════════════════

class TestWriteFile:
    @pytest.mark.asyncio
    async def test_write_new_file(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_write_file
        target = tmp_path / "out.txt"
        result = await _handle_write_file({"path": str(target), "content": "hello world"})
        assert result["ok"] is True
        assert target.read_text() == "hello world"

    @pytest.mark.asyncio
    async def test_write_with_alias_param(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_write_file
        target = tmp_path / "out.txt"
        result = await _handle_write_file({"path": str(target), "code": "print(1)"})
        assert result["ok"] is True
        assert "print(1)" in target.read_text()

    @pytest.mark.asyncio
    async def test_missing_path(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_write_file
        result = await _handle_write_file({"content": "hello"})
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_missing_content(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_write_file
        result = await _handle_write_file({"path": str(tmp_path / "x.txt")})
        assert result["ok"] is False


# ═══════════════════════════════════════════════════════════════
# edit_file
# ═══════════════════════════════════════════════════════════════

class TestEditFile:
    @pytest.mark.asyncio
    async def test_exact_replace(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_edit_file
        f = tmp_path / "edit.txt"
        f.write_text("hello world\nfoo bar\n")
        result = await _handle_edit_file({
            "path": str(f), "old_string": "hello", "new_string": "hi"
        })
        assert result["ok"] is True
        assert f.read_text() == "hi world\nfoo bar\n"
        assert "diff" in result

    @pytest.mark.asyncio
    async def test_replace_all(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_edit_file
        f = tmp_path / "edit.txt"
        f.write_text("x y x z\n")
        result = await _handle_edit_file({
            "path": str(f), "old_string": "x", "new_string": "a", "replace_all": True
        })
        assert result["ok"] is True
        assert f.read_text() == "a y a z\n"

    @pytest.mark.asyncio
    async def test_multiple_matches_no_replace_all(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_edit_file
        f = tmp_path / "edit.txt"
        f.write_text("x x x\n")
        result = await _handle_edit_file({
            "path": str(f), "old_string": "x", "new_string": "a"
        })
        assert result["ok"] is False
        assert "多处匹配" in result["error"] or "replace_all" in result["error"]

    @pytest.mark.asyncio
    async def test_not_found(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_edit_file
        f = tmp_path / "edit.txt"
        f.write_text("hello\n")
        result = await _handle_edit_file({
            "path": str(f), "old_string": "zzz", "new_string": "aaa"
        })
        assert result["ok"] is False
        assert "未找到" in result["error"] or "old_string" in result["error"]

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_edit_file
        result = await _handle_edit_file({
            "path": str(tmp_path / "nope.txt"), "old_string": "x", "new_string": "y"
        })
        assert result["ok"] is False


# ═══════════════════════════════════════════════════════════════
# search_files
# ═══════════════════════════════════════════════════════════════

class TestSearchFiles:
    @pytest.mark.asyncio
    async def test_glob_search(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_search_files
        (tmp_path / "data.json").write_text("{}")
        (tmp_path / "info.json").write_text("{}")
        (tmp_path / "readme.md").write_text("# hi")
        result = await _handle_search_files({
            "pattern": "*.json", "path": str(tmp_path)
        })
        assert result["ok"] is True
        assert "data.json" in result["data"]
        assert "readme.md" not in result["data"]

    @pytest.mark.asyncio
    async def test_content_search(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_search_files
        (tmp_path / "a.py").write_text("def foo(): pass\n")
        (tmp_path / "b.py").write_text("bar = 1\n")
        result = await _handle_search_files({
            "content_pattern": "def ", "path": str(tmp_path), "include": "*.py"
        })
        assert result["ok"] is True
        assert "a.py" in result["data"]

    @pytest.mark.asyncio
    async def test_no_pattern_returns_error(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_search_files
        result = await _handle_search_files({"path": str(tmp_path)})
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_no_matches_glob(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_search_files
        result = await _handle_search_files({
            "pattern": "*.zzz", "path": str(tmp_path)
        })
        assert result["ok"] is True
        assert "未找到" in result["data"]

    @pytest.mark.asyncio
    async def test_content_search_no_matches(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_search_files
        (tmp_path / "a.py").write_text("hello\n")
        result = await _handle_search_files({
            "content_pattern": "zzzz_not_found", "path": str(tmp_path)
        })
        assert result["ok"] is True
        assert "未找到" in result["data"]

    @pytest.mark.asyncio
    async def test_grep_invalid_regex(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_search_files
        result = await _handle_search_files({
            "content_pattern": "[unclosed", "path": str(tmp_path)
        })
        assert result["ok"] is False
        assert "正则" in result["error"]


# ═══════════════════════════════════════════════════════════════
# execute_python
# ═══════════════════════════════════════════════════════════════

class TestExecutePython:
    @pytest.mark.asyncio
    async def test_sandbox_mode(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_execute_python
        mock_sr = MagicMock()
        mock_sr.status.value = "completed"
        mock_sr.stdout = "42\n"
        mock_sr.stderr = ""

        mock_executor = AsyncMock()
        mock_executor.execute_python.return_value = mock_sr

        with patch("core.tools.sandbox_executor.SandboxExecutor",
                   return_value=mock_executor):
            result = await _handle_execute_python({
                "code": "print(42)", "mode": "sandbox"
            })
        text = result["result"]["content"][0]["text"]
        assert "42" in text

    @pytest.mark.asyncio
    async def test_sandbox_error(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_execute_python
        mock_sr = MagicMock()
        mock_sr.status.value = "error"
        mock_sr.error_message = "NameError: name 'x' is not defined"
        mock_sr.stderr = ""

        mock_executor = AsyncMock()
        mock_executor.execute_python.return_value = mock_sr

        with patch("core.tools.sandbox_executor.SandboxExecutor",
                   return_value=mock_executor):
            result = await _handle_execute_python({
                "code": "print(x)", "mode": "sandbox"
            })
        text = result["result"]["content"][0]["text"]
        assert "NameError" in text

    @pytest.mark.asyncio
    async def test_local_mode_unconfirmed(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_execute_python
        result = await _handle_execute_python({
            "code": "print(1)", "mode": "local", "confirmed": False
        })
        text = result["result"]["content"][0]["text"]
        assert "确认" in text

    @pytest.mark.asyncio
    async def test_local_mode_confirmed(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_execute_python
        result = await _handle_execute_python({
            "code": "print(42)", "mode": "local", "confirmed": True
        })
        text = result["result"]["content"][0]["text"]
        assert "42" in text

    @pytest.mark.asyncio
    async def test_local_mode_exception(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_execute_python
        result = await _handle_execute_python({
            "code": "raise ValueError('bad')", "mode": "local", "confirmed": True
        })
        text = result["result"]["content"][0]["text"]
        assert "ValueError" in text
        assert "bad" in text

    @pytest.mark.asyncio
    async def test_non_python_code_redirect(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_execute_python
        result = await _handle_execute_python({
            "code": "<html><body>hello</body></html>", "mode": "sandbox"
        })
        assert result["ok"] is True
        assert "已自动将" in result["data"]
        assert ".html" in result["data"]


# ═══════════════════════════════════════════════════════════════
# execute_shell
# ═══════════════════════════════════════════════════════════════

class TestExecuteShell:
    @pytest.mark.asyncio
    async def test_local_mode(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_execute_shell
        mock_proc = AsyncMock()
        mock_proc.stdout = b"hello from shell\n"
        mock_proc.stderr = b""
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(
            return_value=(b"hello from shell\n", b"")
        )

        with patch("core.multi_agent_v2.tools.tool_registry.asyncio.create_subprocess_shell",
                   return_value=mock_proc):
            result = await _handle_execute_shell({
                "command": "echo hello", "mode": "local"
            })
        text = result["result"]["content"][0]["text"]
        assert "hello from shell" in text

    @pytest.mark.asyncio
    async def test_local_mode_error(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_execute_shell
        mock_proc = AsyncMock()
        mock_proc.returncode = 127
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"command not found")
        )

        with patch("core.multi_agent_v2.tools.tool_registry.asyncio.create_subprocess_shell",
                   return_value=mock_proc):
            result = await _handle_execute_shell({
                "command": "nonexistent_command_xyz", "mode": "local"
            })
        text = result["result"]["content"][0]["text"]
        assert "127" in text or "error" in text.lower()


# ═══════════════════════════════════════════════════════════════
# fetch_url
# ═══════════════════════════════════════════════════════════════

class TestFetchUrl:
    @pytest.mark.asyncio
    async def test_success(self):
        from core.multi_agent_v2.tools.tool_registry import _handle_fetch_url
        with (
            patch(
                "core.multi_agent_v2.tools.tool_registry._http_get",
                new=AsyncMock(return_value="<html><body>Hello World</body></html>"),
            ),
            patch(
                "core.multi_agent_v2.tools.html_parser.html_to_text",
                return_value="Hello World (this is readable text with more than 20 chars)",
            ),
        ):
            result = await _handle_fetch_url({"url": "https://example.com"})
        assert result["ok"] is True
        assert "Hello" in result["data"]

    @pytest.mark.asyncio
    async def test_json_response(self):
        from core.multi_agent_v2.tools.tool_registry import _handle_fetch_url
        with patch(
            "core.multi_agent_v2.tools.tool_registry._http_get",
            new=AsyncMock(return_value='[{"id":1,"name":"test"},{"id":2,"name":"test2"}]'),
        ):
            result = await _handle_fetch_url({"url": "https://api.example.com/data"})
        assert result["ok"] is True
        assert "test" in result["data"]

    @pytest.mark.asyncio
    async def test_timeout(self):
        from core.multi_agent_v2.tools.tool_registry import _handle_fetch_url
        with patch(
            "core.multi_agent_v2.tools.tool_registry._http_get",
            new=AsyncMock(side_effect=asyncio.TimeoutError()),
        ):
            result = await _handle_fetch_url({"url": "https://slow.example.com"})
        assert result["ok"] is False
        assert "超时" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_url(self):
        from core.multi_agent_v2.tools.tool_registry import _handle_fetch_url
        result = await _handle_fetch_url({})
        assert result["ok"] is False
        assert "url" in result["error"]


# ═══════════════════════════════════════════════════════════════
# web_search
# ═══════════════════════════════════════════════════════════════

class TestWebSearch:
    @pytest.mark.asyncio
    async def test_normal_search(self):
        from core.multi_agent_v2.tools.tool_registry import _handle_search

        mock_http_get = AsyncMock()
        mock_http_get.side_effect = [
            "<html>Bing results</html>",
            "<html>Baidu results</html>",
            "<html>DDG results</html>",
        ]

        with (
            patch(
                "core.multi_agent_v2.tools.tool_registry._http_get",
                new=mock_http_get,
            ),
            patch(
                "core.multi_agent_v2.tools.html_parser.extract_search_results_bing",
                return_value=[{"title": "B1", "url": "https://b1.com", "snippet": "s1"}],
            ),
            patch(
                "core.multi_agent_v2.tools.html_parser.extract_search_results_baidu",
                return_value=[{"title": "BD1", "url": "https://bd1.com", "snippet": "s2"}],
            ),
            patch(
                "core.multi_agent_v2.tools.html_parser.extract_search_results_ddg",
                return_value=[{"title": "DDG1", "url": "https://ddg1.com", "snippet": "s3"}],
            ),
            patch(
                "core.multi_agent_v2.tools.html_parser.merge_search_results",
                return_value="B1: s1\nBD1: s2\nDDG1: s3",
            ),
        ):
            result = await _handle_search({"query": "test query"})
        assert result["ok"] is True
        assert "B1" in result["data"]

    @pytest.mark.asyncio
    async def test_all_engines_fail(self):
        from core.multi_agent_v2.tools.tool_registry import _handle_search

        with patch(
            "core.multi_agent_v2.tools.tool_registry._http_get",
            new=AsyncMock(side_effect=TimeoutError("timeout")),
        ):
            result = await _handle_search({"query": "test query"})
        assert result["ok"] is False
        assert "不可用" in result["error"] or "超时" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_query(self):
        from core.multi_agent_v2.tools.tool_registry import _handle_search
        result = await _handle_search({})
        assert result["ok"] is False
        assert "query" in result["error"]


# ═══════════════════════════════════════════════════════════════
# git
# ═══════════════════════════════════════════════════════════════

class TestGit:
    @pytest.mark.asyncio
    async def test_git_status(self):
        from core.multi_agent_v2.tools.tool_registry import _handle_git
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"On branch main\nnothing to commit\n", b"")
        )

        with patch(
            "core.multi_agent_v2.tools.tool_registry.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            result = await _handle_git({"action": "status"})
        text = result["result"]["content"][0]["text"]
        assert "status" in text
        assert "main" in text

    @pytest.mark.asyncio
    async def test_git_log(self):
        from core.multi_agent_v2.tools.tool_registry import _handle_git
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"abc123 first commit\ndef456 second commit\n", b"")
        )

        with patch(
            "core.multi_agent_v2.tools.tool_registry.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            result = await _handle_git({"action": "log", "count": 5})
        text = result["result"]["content"][0]["text"]
        assert "abc123" in text
        assert "def456" in text

    @pytest.mark.asyncio
    async def test_git_unknown_action(self):
        from core.multi_agent_v2.tools.tool_registry import _handle_git
        result = await _handle_git({"action": "unknown_action"})
        text = result["result"]["content"][0]["text"]
        assert "未知" in text or "失败" in text


# ═══════════════════════════════════════════════════════════════
# ToolRegistry 集成 — validate_arguments + handler 联合测试
# ═══════════════════════════════════════════════════════════════

class TestRegistryIntegration:
    def _make_registry(self):
        from core.multi_agent_v2.tools.tool_registry import (
            ToolRegistry, _SANDBOX_TOOL_DEFS,
        )
        reg = ToolRegistry()
        for td in _SANDBOX_TOOL_DEFS:
            reg._tools[td.name] = td
        return reg

    @pytest.mark.asyncio
    async def test_validate_and_execute_read_file(self, tmp_path):
        reg = self._make_registry()
        f = tmp_path / "integrate.txt"
        f.write_text("integration test")

        valid, msg = reg.validate_arguments("read_file", {"path": str(f)})
        assert valid is True

        handler = reg.get_handler("read_file")
        result = await handler({"path": str(f)})
        assert result["ok"] is True
        assert "integration test" in result["data"]

    @pytest.mark.asyncio
    async def test_validate_and_execute_write_file(self, tmp_path):
        reg = self._make_registry()
        target = tmp_path / "integrate_out.txt"

        valid, msg = reg.validate_arguments(
            "write_file", {"path": str(target), "content": "hello from validate"}
        )
        assert valid is True

        handler = reg.get_handler("write_file")
        result = await handler({"path": str(target), "content": "hello from validate"})
        assert result["ok"] is True
        assert target.read_text() == "hello from validate"

    def test_validate_arguments_bad_type(self):
        reg = self._make_registry()
        valid, msg = reg.validate_arguments("read_file", {"path": 12345})
        assert valid is True, "validate_arguments auto-converts int→str"

    def test_validate_arguments_missing_required(self):
        reg = self._make_registry()
        valid, msg = reg.validate_arguments(
            "edit_file", {"new_string": "hello"}
        )
        assert valid is False

    def test_validate_arguments_unknown_tool(self):
        reg = self._make_registry()
        valid, msg = reg.validate_arguments("nonexistent_tool", {"foo": "bar"})
        assert valid is False
        assert "未知" in msg or "tool" in msg.lower()

    @pytest.mark.asyncio
    async def test_get_tools_for_task_returns_all_by_default(self):
        reg = self._make_registry()
        tools = await reg.get_tools_for_task("任意任务", max_tools=20)
        names = [t.name for t in tools]
        assert len(names) >= 9
        assert "web_search" in names
        assert "read_file" in names

    @pytest.mark.asyncio
    async def test_get_tools_for_task_honors_disallowed(self):
        reg = self._make_registry()
        reg._initialized = True
        tools = await reg.get_tools_for_task(
            "写一个Python脚本", max_tools=20, disallowed=["execute_shell", "git"]
        )
        names = [t.name for t in tools]
        assert "execute_shell" not in names
        assert "git" not in names
        assert "execute_python" in names


# ═══════════════════════════════════════════════════════════════
# ToolDefinition 元数据验证
# ═══════════════════════════════════════════════════════════════

class TestToolDefinitions:
    def test_all_tools_have_unique_names(self):
        from core.multi_agent_v2.tools.tool_registry import _SANDBOX_TOOL_DEFS
        names = [t.name for t in _SANDBOX_TOOL_DEFS]
        assert len(names) == len(set(names))

    def test_all_tools_have_descriptions(self):
        from core.multi_agent_v2.tools.tool_registry import _SANDBOX_TOOL_DEFS
        for td in _SANDBOX_TOOL_DEFS:
            assert len(td.description) > 10, f"{td.name} description too short"

    def test_all_tools_have_parameters_schema(self):
        from core.multi_agent_v2.tools.tool_registry import _SANDBOX_TOOL_DEFS
        for td in _SANDBOX_TOOL_DEFS:
            assert "properties" in td.parameters
            assert isinstance(td.parameters["properties"], dict)

    def test_all_tools_have_builtin_server(self):
        from core.multi_agent_v2.tools.tool_registry import _SANDBOX_TOOL_DEFS, SERVER_BUILTIN
        for td in _SANDBOX_TOOL_DEFS:
            assert td.server == SERVER_BUILTIN

    def test_all_handlers_in_handler_map(self):
        from core.multi_agent_v2.tools.tool_registry import (
            _SANDBOX_TOOL_DEFS, _HANDLER_MAP,
        )
        for td in _SANDBOX_TOOL_DEFS:
            assert td.name in _HANDLER_MAP
            assert callable(_HANDLER_MAP[td.name])

    def test_handler_map_no_extras(self):
        from core.multi_agent_v2.tools.tool_registry import (
            _SANDBOX_TOOL_DEFS, _HANDLER_MAP,
        )
        def_names = {td.name for td in _SANDBOX_TOOL_DEFS}
        map_names = set(_HANDLER_MAP.keys())
        assert map_names == def_names


# ═══════════════════════════════════════════════════════════════
# Tool result 格式兼容性
# ═══════════════════════════════════════════════════════════════

class TestToolResultFormat:
    def test_ok_format(self):
        from core.multi_agent_v2.tools.tool_result import ok, is_ok, from_handler, extract_error
        r = ok("success")
        assert r == {"ok": True, "data": "success"}
        assert is_ok(r) is True
        assert from_handler(r) == "success"
        assert extract_error(r) == ""

    def test_err_format(self):
        from core.multi_agent_v2.tools.tool_result import err, is_ok, from_handler, extract_error
        r = err("something failed")
        assert r == {"ok": False, "error": "something failed"}
        assert is_ok(r) is False
        assert "错误:" in from_handler(r)
        assert extract_error(r) == "something failed"

    def test_old_format_compatibility(self):
        from core.multi_agent_v2.tools.tool_result import is_ok, from_handler
        r = {"result": {"content": [{"text": "hello"}]}}
        assert is_ok(r) is True
        assert from_handler(r) == "hello"

    def test_old_format_error_text(self):
        from core.multi_agent_v2.tools.tool_result import is_ok
        r = {"result": {"content": [{"text": "失败: resource not found"}]}}
        assert is_ok(r) is False

    def test_none_handler(self):
        from core.multi_agent_v2.tools.tool_result import from_handler
        assert from_handler(None) == ""

    def test_string_handler(self):
        from core.multi_agent_v2.tools.tool_result import from_handler
        assert from_handler("plain string") == "plain string"
