"""
E2E 能力测试: 验证工具系统优化的实际效果

覆盖：
1. html_parser — HTML→文本转换、搜索引擎结果解析
2. tool_result — 统一结果格式
3. 迁移工具 — read_file/edit_file/glob_search/grep_search
4. fetch_url — 直返可读文本
5. 搜索多引擎 — Bing+百度+DDG 解析
6. RecoveryManager — 降级链路
7. 完整工具链 — 搜索→分析→写文件
"""
import asyncio
import json
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock


# ═══════════════════════════════════════════════════════════════════
# 1. html_parser 单元验证
# ═══════════════════════════════════════════════════════════════════

class TestHtmlParser:
    """验证 html_to_text 和搜索引擎结果提取"""

    def test_html_to_text_strips_tags(self):
        from core.multi_agent_v2.tools.html_parser import html_to_text
        html = "<html><body><h1>标题</h1><p>正文内容</p></body></html>"
        result = html_to_text(html)
        assert "标题" in result
        assert "正文内容" in result
        assert "<h1>" not in result
        assert "<p>" not in result

    def test_html_to_text_removes_scripts(self):
        from core.multi_agent_v2.tools.html_parser import html_to_text
        html = "<html><body><script>var x=1;</script><p>可见内容</p></body></html>"
        result = html_to_text(html)
        assert "var x=1" not in result
        assert "可见内容" in result

    def test_html_to_text_max_length(self):
        from core.multi_agent_v2.tools.html_parser import html_to_text
        html = "<p>" + "很长" * 5000 + "</p>"
        result = html_to_text(html, max_length=100)
        assert len(result) <= 200

    def test_extract_bing_results(self):
        from core.multi_agent_v2.tools.html_parser import extract_search_results_bing
        html = """
        <html><body>
        <li class="b_algo"><h2><a href="https://example.com">示例网站</a></h2>
        <p>这是Bing搜索结果的描述文本</p></li>
        <li class="b_algo"><h2><a href="https://example2.com">第二个结果</a></h2>
        <p>第二个描述</p></li>
        </body></html>
        """
        results = extract_search_results_bing(html)
        assert len(results) >= 1
        assert any("示例网站" in r.get("title", "") for r in results)

    def test_extract_baidu_results(self):
        from core.multi_agent_v2.tools.html_parser import extract_search_results_baidu
        html = """
        <html><body>
        <div class="result c-container new-pmd">
            <h3 class="t"><a href="https://example.com">百度结果标题</a></h3>
            <span class="content-right_8Zs40">百度结果描述文本</span>
        </div>
        </div>
        </body></html>
        """
        results = extract_search_results_baidu(html)
        assert len(results) >= 1
        assert "百度结果标题" in results[0]["title"]

    def test_extract_ddg_results(self):
        from core.multi_agent_v2.tools.html_parser import extract_search_results_ddg
        html = """
        <html><body>
        <div class="result__body">
            <a class="result__a" href="https://example.com">DDG结果标题</a>
            <a class="result__snippet">DDG结果描述</a>
        </div>
        </div>
        </body></html>
        """
        results = extract_search_results_ddg(html)
        assert len(results) >= 1
        assert "DDG结果标题" in results[0]["title"]

    def test_merge_search_results_dedup(self):
        from core.multi_agent_v2.tools.html_parser import merge_search_results
        sources = [
            ("Bing", [{"title": "相同标题", "url": "https://a.com", "snippet": "描述A"}]),
            ("百度", [{"title": "相同标题", "url": "https://a.com", "snippet": "描述B"}]),
            ("DDG", [{"title": "不同标题", "url": "https://b.com", "snippet": "描述C"}]),
        ]
        merged = merge_search_results(sources)
        assert "相同标题" in merged
        assert "不同标题" in merged

    def test_merge_search_results_empty(self):
        from core.multi_agent_v2.tools.html_parser import merge_search_results
        merged = merge_search_results([])
        assert "未找到相关结果" in merged


# ═══════════════════════════════════════════════════════════════════
# 2. tool_result 统一格式验证
# ═══════════════════════════════════════════════════════════════════

class TestToolResult:
    """验证 tool_result 的 ok/err/from_handler 格式"""

    def test_ok_format(self):
        from core.multi_agent_v2.tools.tool_result import ok
        r = ok("成功消息")
        assert r["ok"] is True
        assert r["data"] == "成功消息"

    def test_err_format(self):
        from core.multi_agent_v2.tools.tool_result import err
        r = err("错误消息")
        assert r["ok"] is False
        assert r["error"] == "错误消息"

    def test_from_handler_new_format(self):
        from core.multi_agent_v2.tools.tool_result import from_handler, ok
        text = from_handler(ok("执行成功"))
        assert text == "执行成功"

    def test_from_handler_old_format(self):
        from core.multi_agent_v2.tools.tool_result import from_handler
        old = {"result": {"content": [{"text": "旧格式内容"}]}}
        text = from_handler(old)
        assert text == "旧格式内容"

    def test_from_handler_string(self):
        from core.multi_agent_v2.tools.tool_result import from_handler
        assert from_handler("纯字符串") == "纯字符串"

    def test_from_handler_none(self):
        from core.multi_agent_v2.tools.tool_result import from_handler
        assert from_handler(None) == ""

    def test_extract_error_from_err(self):
        from core.multi_agent_v2.tools.tool_result import extract_error, err
        e = extract_error(err("测试错误"))
        assert e == "测试错误"

    def test_extract_error_from_ok(self):
        from core.multi_agent_v2.tools.tool_result import extract_error, ok
        e = extract_error(ok("无错误"))
        assert e == ""

    def test_is_ok(self):
        from core.multi_agent_v2.tools.tool_result import is_ok, ok, err
        assert is_ok(ok("x")) is True
        assert is_ok(err("x")) is False
        assert is_ok({"old_format": True}) is True


# ═══════════════════════════════════════════════════════════════════
# 3. 迁移工具实际调用验证
# ═══════════════════════════════════════════════════════════════════

class TestMigratedTools:
    """验证从 register_new_tools 迁移到 _SANDBOX_TOOL_DEFS 的工具"""

    @pytest.mark.asyncio
    async def test_read_file(self):
        from core.multi_agent_v2.tools.tool_registry import _handle_read_file
        from core.multi_agent_v2.tools.tool_result import from_handler
        r = await _handle_read_file({"path": "/etc/hostname"})
        text = from_handler(r)
        assert len(text) > 0

    @pytest.mark.asyncio
    async def test_read_file_not_found(self):
        from core.multi_agent_v2.tools.tool_registry import _handle_read_file
        from core.multi_agent_v2.tools.tool_result import is_ok
        r = await _handle_read_file({"path": "/tmp/nonexistent_12345.txt"})
        assert is_ok(r) is False

    @pytest.mark.asyncio
    async def test_read_file_no_path(self):
        from core.multi_agent_v2.tools.tool_registry import _handle_read_file
        from core.multi_agent_v2.tools.tool_result import is_ok
        r = await _handle_read_file({})
        assert is_ok(r) is False

    @pytest.mark.asyncio
    async def test_read_file_directory(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_read_file
        from core.multi_agent_v2.tools.tool_result import from_handler
        (tmp_path / "dir_a").mkdir()
        (tmp_path / "file_b.txt").write_text("x")
        r = await _handle_read_file({"path": str(tmp_path)})
        text = from_handler(r)
        assert "dir_a" in text
        assert "file_b.txt" in text

    @pytest.mark.asyncio
    async def test_edit_file(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_edit_file
        from core.multi_agent_v2.tools.tool_result import from_handler, is_ok
        f = tmp_path / "edit_test.txt"
        f.write_text("Hello World", encoding="utf-8")
        r = await _handle_edit_file({
            "path": str(f),
            "old_string": "World",
            "new_string": "Python"
        })
        assert is_ok(r) is True
        text = from_handler(r)
        assert "成功" in text
        assert f.read_text(encoding="utf-8") == "Hello Python"

    @pytest.mark.asyncio
    async def test_edit_file_not_found(self):
        from core.multi_agent_v2.tools.tool_registry import _handle_edit_file
        from core.multi_agent_v2.tools.tool_result import is_ok
        r = await _handle_edit_file({
            "path": "/tmp/nonexistent_edit.txt",
            "old_string": "a",
            "new_string": "b"
        })
        assert is_ok(r) is False

    @pytest.mark.asyncio
    async def test_edit_file_replace_all(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_edit_file
        from core.multi_agent_v2.tools.tool_result import from_handler
        f = tmp_path / "multi.txt"
        f.write_text("aaa bbb aaa ccc aaa", encoding="utf-8")
        r = await _handle_edit_file({
            "path": str(f),
            "old_string": "aaa",
            "new_string": "xxx",
            "replace_all": True
        })
        text = from_handler(r)
        assert "成功" in text
        assert f.read_text(encoding="utf-8") == "xxx bbb xxx ccc xxx"

    @pytest.mark.asyncio
    async def test_glob_search(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_glob_search
        from core.multi_agent_v2.tools.tool_result import from_handler
        (tmp_path / "a.py").write_text("x")
        (tmp_path / "b.py").write_text("y")
        (tmp_path / "c.txt").write_text("z")
        r = await _handle_glob_search({"pattern": "*.py", "path": str(tmp_path)})
        text = from_handler(r)
        assert "a.py" in text
        assert "b.py" in text
        assert "c.txt" not in text

    @pytest.mark.asyncio
    async def test_grep_search(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_grep_search
        from core.multi_agent_v2.tools.tool_result import from_handler
        f = tmp_path / "grep_test.py"
        f.write_text("def foo():\n    pass\ndef bar():\n    pass\n", encoding="utf-8")
        r = await _handle_grep_search({
            "pattern": "def \\w+",
            "path": str(f),
        })
        text = from_handler(r)
        assert "foo" in text
        assert "bar" in text

    @pytest.mark.asyncio
    async def test_grep_search_no_match(self, tmp_path):
        from core.multi_agent_v2.tools.tool_registry import _handle_grep_search
        from core.multi_agent_v2.tools.tool_result import from_handler
        f = tmp_path / "no_match.txt"
        f.write_text("hello world", encoding="utf-8")
        r = await _handle_grep_search({"pattern": " xyzABC ", "path": str(f)})
        text = from_handler(r)
        assert "未找到" in text


# ═══════════════════════════════════════════════════════════════════
# 4. fetch_url 直返可读文本
# ═══════════════════════════════════════════════════════════════════

class TestFetchUrlDirectReturn:
    """验证 fetch_url 不再写 /tmp 文件，直接返回可读文本"""

    @pytest.mark.asyncio
    async def test_fetch_url_returns_text(self):
        from core.multi_agent_v2.tools.tool_registry import _handle_fetch_url
        from core.multi_agent_v2.tools.tool_result import from_handler
        r = await _handle_fetch_url({"url": "https://httpbin.org/get"})
        text = from_handler(r)
        assert "保存到" not in text
        assert "agent_fetch_" not in text
        assert len(text) > 10

    @pytest.mark.asyncio
    async def test_fetch_url_no_tmp_file(self):
        from core.multi_agent_v2.tools.tool_registry import _handle_fetch_url
        before = set(Path("/tmp").glob("agent_fetch_*"))
        await _handle_fetch_url({"url": "https://httpbin.org/get"})
        after = set(Path("/tmp").glob("agent_fetch_*"))
        new_files = after - before
        assert len(new_files) == 0

    @pytest.mark.asyncio
    async def test_fetch_url_empty_url(self):
        from core.multi_agent_v2.tools.tool_registry import _handle_fetch_url
        from core.multi_agent_v2.tools.tool_result import is_ok
        r = await _handle_fetch_url({"url": ""})
        assert is_ok(r) is False

    @pytest.mark.asyncio
    async def test_fetch_url_invalid_url(self):
        from core.multi_agent_v2.tools.tool_registry import _handle_fetch_url
        from core.multi_agent_v2.tools.tool_result import is_ok
        r = await _handle_fetch_url({"url": "https://this-domain-does-not-exist-12345.com"})
        assert is_ok(r) is False


# ═══════════════════════════════════════════════════════════════════
# 5. 搜索引擎多引擎解析验证
# ═══════════════════════════════════════════════════════════════════

class TestMultiEngineSearch:
    """验证搜索解析器能正确处理各引擎的 HTML"""

    def test_bing_parser_extracts_links(self):
        from core.multi_agent_v2.tools.html_parser import extract_search_results_bing
        html = """
        <ol>
        <li class="b_algo"><h2><a href="https://a.com">Result A</a></h2><p>Desc A</p></li>
        <li class="b_algo"><h2><a href="https://b.com">Result B</a></h2><p>Desc B</p></li>
        </ol>
        """
        results = extract_search_results_bing(html)
        assert len(results) == 2
        assert results[0]["title"] == "Result A"
        assert results[0]["url"] == "https://a.com"

    def test_baidu_parser_extracts_links(self):
        from core.multi_agent_v2.tools.html_parser import extract_search_results_baidu
        html = """
        <div class="result c-container new-pmd">
            <h3 class="t"><a href="https://a.com">百度标题A</a></h3>
            <span class="content-right_8Zs40">描述A</span>
        </div>
        </div>
        <div class="result c-container new-pmd">
            <h3 class="t"><a href="https://b.com">百度标题B</a></h3>
            <span class="content-right_8Zs40">描述B</span>
        </div>
        </div>
        """
        results = extract_search_results_baidu(html)
        assert len(results) >= 1

    def test_ddg_parser_extracts_links(self):
        from core.multi_agent_v2.tools.html_parser import extract_search_results_ddg
        html = """
        <div class="result__body">
            <a class="result__a" href="https://a.com">DDG Title A</a>
            <a class="result__snippet">DDG Snippet A</a>
        </div>
        </div>
        <div class="result__body">
            <a class="result__a" href="https://b.com">DDG Title B</a>
            <a class="result__snippet">DDG Snippet B</a>
        </div>
        </div>
        """
        results = extract_search_results_ddg(html)
        assert len(results) >= 1

    def test_merge_preserves_source(self):
        from core.multi_agent_v2.tools.html_parser import merge_search_results
        sources = [
            ("Bing", [{"title": "T1", "url": "https://1.com", "snippet": "S1"}]),
            ("百度", [{"title": "T2", "url": "https://2.com", "snippet": "S2"}]),
        ]
        merged = merge_search_results(sources)
        assert "T1" in merged
        assert "T2" in merged


# ═══════════════════════════════════════════════════════════════════
# 6. RecoveryManager 降级链路
# ═══════════════════════════════════════════════════════════════════

class TestRecoveryManagerFallback:
    """验证 RecoveryManager 的降级配置和链路"""

    def test_fallback_config_has_tools(self):
        from core.multi_agent_v2.tools.recovery import DEFAULT_FALLBACK_CONFIG
        fb = DEFAULT_FALLBACK_CONFIG.fallback_tools
        assert "web_search" in fb
        assert fb["web_search"] == "fetch_url"
        assert "fetch_url" in fb
        assert "rag_search" in fb

    def test_get_fallback_tool(self):
        from core.multi_agent_v2.tools.recovery import RecoveryManager, FallbackConfig
        mgr = RecoveryManager(fallback_config=FallbackConfig(
            enabled=True,
            fallback_tools={"tool_a": "tool_b", "tool_c": "tool_d"}
        ))
        assert mgr.get_fallback_tool("tool_a") == "tool_b"
        assert mgr.get_fallback_tool("tool_c") == "tool_d"
        assert mgr.get_fallback_tool("unknown") is None

    def test_fallback_disabled(self):
        from core.multi_agent_v2.tools.recovery import RecoveryManager, FallbackConfig
        mgr = RecoveryManager(fallback_config=FallbackConfig(enabled=False))
        assert mgr.get_fallback_tool("web_search") is None

    def test_recovery_plan_fallback(self):
        from core.multi_agent_v2.tools.recovery import RecoveryManager, FallbackConfig
        mgr = RecoveryManager(fallback_config=FallbackConfig(
            enabled=True,
            fallback_tools={"web_search": "fetch_url"}
        ))
        plan = mgr.create_recovery_plan(
            "web_search", Exception("timeout"), attempt=5
        )
        assert plan.strategy == "fallback"
        assert plan.fallback_tool == "fetch_url"

    def test_recovery_plan_abort_when_no_fallback(self):
        from core.multi_agent_v2.tools.recovery import RecoveryManager, FallbackConfig
        mgr = RecoveryManager(fallback_config=FallbackConfig(
            enabled=True, fallback_tools={}
        ))
        plan = mgr.create_recovery_plan(
            "unknown_tool", Exception("fail"), attempt=5
        )
        assert plan.strategy == "abort"

    @pytest.mark.asyncio
    async def test_parallel_degradation_uses_fallback(self):
        """验证 execute_tool_calls_parallel 在连续失败后使用 RecoveryManager 降级"""
        from core.multi_agent_v2.agents.react_core import RunContext
        from core.multi_agent_v2.agents.tool_executor import execute_tool_calls_parallel

        ctx = RunContext(task_description="降级测试", max_iterations=10)
        ctx.consecutive_failures["web_search"] = 3

        call_names = []

        async def mock_execute(tc, _ctx):
            name = tc.get("function", {}).get("name", "")
            call_names.append(name)
            return {"success": True, "result": {"text": f"{name} executed"}}

        tc = {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "web_search",
                "arguments": json.dumps({"query": "test"})
            }
        }

        results = await execute_tool_calls_parallel([tc], ctx, execute_fn=mock_execute)
        assert len(results) == 1
        assert call_names[0] == "fetch_url"
        assert results[0].get("quality") == "degraded"
        assert results[0].get("degraded_from") == "web_search"


# ═══════════════════════════════════════════════════════════════════
# 7. 完整工具链: 搜索→分析→写文件
# ═══════════════════════════════════════════════════════════════════

class TestFullToolChain:
    """端到端验证：工具链完整性"""

    @pytest.mark.asyncio
    async def test_search_then_write_report(self, tmp_path):
        """模拟: 搜索 → 分析 → 写报告"""
        from core.multi_agent_v2.tools.tool_registry import (
            _handle_search,
            _handle_execute_python,
            _handle_write_file,
        )
        from core.multi_agent_v2.tools.tool_result import from_handler

        with patch("core.multi_agent_v2.tools.tool_registry._http_get", new_callable=AsyncMock) as mock_http:
            mock_http.return_value = "<html><body><p>搜索结果内容</p></body></html>"
            search_result = await _handle_search({"query": "测试搜索"})

        search_text = from_handler(search_result)
        assert len(search_text) > 0

        analysis = await _handle_execute_python({
            "code": f"data = '''{search_text[:200]}'''\nresult = f'分析完成: {{len(data)}}字符'"
        })
        analysis_text = from_handler(analysis)
        assert "分析完成" in analysis_text or "执行成功" in analysis_text

        report_path = str(tmp_path / "report.md")
        write_result = await _handle_write_file({
            "path": report_path,
            "content": f"# 搜索报告\n\n搜索结果: {search_text[:100]}\n\n分析: 完成"
        })
        write_text = from_handler(write_result)
        assert "写入" in write_text

        report_content = Path(report_path).read_text(encoding="utf-8")
        assert "搜索报告" in report_content
        assert "搜索结果" in report_content

    @pytest.mark.asyncio
    async def test_read_edit_glob_grep_chain(self, tmp_path):
        """模拟: glob查找 → read读取 → edit编辑 → grep验证"""
        from core.multi_agent_v2.tools.tool_registry import (
            _handle_glob_search,
            _handle_read_file,
            _handle_edit_file,
            _handle_grep_search,
        )
        from core.multi_agent_v2.tools.tool_result import from_handler

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text(
            "def hello():\n    print('old')\n", encoding="utf-8"
        )
        (tmp_path / "src" / "utils.py").write_text(
            "def helper():\n    pass\n", encoding="utf-8"
        )

        glob_result = await _handle_glob_search({
            "pattern": "*.py",
            "path": str(tmp_path / "src")
        })
        glob_text = from_handler(glob_result)
        assert "main.py" in glob_text

        read_result = await _handle_read_file({
            "path": str(tmp_path / "src" / "main.py")
        })
        read_text = from_handler(read_result)
        assert "hello" in read_text

        edit_result = await _handle_edit_file({
            "path": str(tmp_path / "src" / "main.py"),
            "old_string": "old",
            "new_string": "new"
        })
        edit_text = from_handler(edit_result)
        assert "成功" in edit_text

        grep_result = await _handle_grep_search({
            "pattern": "new",
            "path": str(tmp_path / "src" / "main.py")
        })
        grep_text = from_handler(grep_result)
        assert "new" in grep_text

    def test_all_sandbox_tools_registered(self):
        """验证所有关键工具都在 _SANDBOX_TOOL_DEFS 中"""
        from core.multi_agent_v2.tools.tool_registry import _SANDBOX_TOOL_DEFS
        names = {td.name for td in _SANDBOX_TOOL_DEFS}
        required = {
            "write_file", "execute_python", "execute_shell", "git",
            "fetch_url", "web_search",
            "read_file", "edit_file",
        }
        missing = required - names
        assert not missing, f"缺少工具: {missing}"

    def test_handler_map_complete(self):
        """验证 _HANDLER_MAP 覆盖所有关键工具"""
        from core.multi_agent_v2.tools.tool_registry import _HANDLER_MAP
        required = {
            "write_file", "execute_python", "execute_shell", "git",
            "fetch_url", "web_search",
            "read_file", "edit_file",
        }
        missing = required - set(_HANDLER_MAP.keys())
        assert not missing, f"缺少 handler: {missing}"
