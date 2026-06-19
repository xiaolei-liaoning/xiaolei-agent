"""
测试上下文压缩系统：ConversationStore + ContextBudgetManager
"""
import json
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.multi_agent_v2.agents.context_budget import ContextBudgetManager, estimate_tokens
from core.multi_agent_v2.agents.middleware import RunContext


# ── Mock 数据 ──────────────────────────────────────────────

def make_entry(name: str, success: bool, args: dict, result: dict, n: int = 0):
    return {
        "tool_call": {"name": name, "arguments": args},
        "success": success,
        "result": result,
        "quality": "ok" if success else "bad",
        "_data_status": "",
    }


SAMPLE_ENTRIES = [
    make_entry("web_search", True, {"query": "天气北京"}, {"result": "北京今天晴 25°C", "url": "http://weather.com"}),
    make_entry("fetch_url", True, {"url": "http://example.com"}, {"content": "<html>Example</html>", "url": "http://example.com"}),
    make_entry("write_file", True, {"path": "/tmp/test.txt", "content": "hello"}, {"path": "/tmp/test.txt", "size": 5}),
    make_entry("read_file", False, {"path": "/tmp/nonexist.txt"}, {"error": "file not found"}),
    make_entry("execute_shell", True, {"command": "echo hi"}, {"stdout": "hi", "returncode": 0}),
    make_entry("write_file", True, {"path": "/tmp/report.md", "content": "# Report"}, {"path": "/tmp/report.md", "size": 10}),
]


# ── Test: estimate_tokens ──────────────────────────────────

class TestEstimateTokens:
    def test_empty(self):
        assert estimate_tokens("") == 0

    def test_english(self):
        assert estimate_tokens("hello world") > 0

    def test_chinese(self):
        assert estimate_tokens("你好世界") > 0


# ── Test: generate_compaction_summary（增强模板）────────────

class TestTemplateSummary:
    def test_empty_entries(self):
        mgr = ContextBudgetManager()
        assert mgr.generate_compaction_summary([]) == ""

    def test_basic_summary(self):
        mgr = ContextBudgetManager()
        summary = mgr.generate_compaction_summary(SAMPLE_ENTRIES[:3])
        assert "web_search" in summary
        assert "fetch_url" in summary
        assert "write_file" in summary
        assert "✅" in summary or "❌" in summary

    def test_file_extraction(self):
        mgr = ContextBudgetManager()
        summary = mgr.generate_compaction_summary(SAMPLE_ENTRIES)
        assert "test.txt" in summary or "/tmp" in summary

    def test_query_extraction(self):
        mgr = ContextBudgetManager()
        summary = mgr.generate_compaction_summary(SAMPLE_ENTRIES[:1])
        assert "天气" in summary or "weather" in summary.lower()

    def test_error_extraction(self):
        mgr = ContextBudgetManager()
        summary = mgr.generate_compaction_summary(SAMPLE_ENTRIES[3:4])
        assert "file not found" in summary


# ── Test: Overflow Detection ──────────────────────────────

class TestOverflow:
    def test_no_overflow_empty(self):
        ctx = RunContext("test")
        mgr = ContextBudgetManager(max_context_chars=1000, safety_margin=0)
        assert not mgr.is_overflow(ctx)

    def test_overflow_detected(self):
        ctx = RunContext("test")
        ctx.tool_results = list(SAMPLE_ENTRIES)
        # with very small budget, should overflow
        mgr = ContextBudgetManager(max_context_chars=10, safety_margin=0)
        assert mgr.is_overflow(ctx)

    def test_no_overflow_large_budget(self):
        ctx = RunContext("test")
        ctx.tool_results = list(SAMPLE_ENTRIES[:1])
        mgr = ContextBudgetManager(max_context_chars=999999)
        assert not mgr.is_overflow(ctx)

    def test_overflow_includes_conversation_history(self):
        ctx = RunContext("test")
        ctx._conversation_history = [
            {"role": "tool", "content": "x" * 5000, "tool_call_id": "c1", "name": "web_search"},
            {"role": "assistant", "content": "y" * 1000},
        ]
        mgr = ContextBudgetManager(max_context_chars=500, safety_margin=0)
        assert mgr.is_overflow(ctx)


# ── Test: select_entries_to_compact ───────────────────────

class TestSelectEntries:
    def test_too_few_entries(self):
        ctx = RunContext("test")
        ctx.tool_results = SAMPLE_ENTRIES[:2]
        mgr = ContextBudgetManager(min_rounds_before_compact=4)
        assert mgr._select_entries_to_compact(ctx) == 0

    def test_select_oldest_entries(self):
        ctx = RunContext("test")
        ctx.tool_results = list(SAMPLE_ENTRIES)  # 6 entries
        mgr = ContextBudgetManager(
            max_context_chars=10, safety_margin=0,
            protected_recent_turns=2, min_rounds_before_compact=2,
        )
        n = mgr._select_entries_to_compact(ctx)
        # protected=2, compactable=4, overflow → should select some
        assert n > 0
        assert n <= 4

    def test_no_overflow_no_compact(self):
        ctx = RunContext("test")
        ctx.tool_results = list(SAMPLE_ENTRIES)
        mgr = ContextBudgetManager(
            max_context_chars=999999,
            protected_recent_turns=2, min_rounds_before_compact=2,
        )
        assert mgr._select_entries_to_compact(ctx) == 0


# ── Test: rebuild_after_compaction ────────────────────────

class TestRebuild:
    def test_tool_results_reordered(self):
        ctx = RunContext("test")
        ctx.tool_results = [{"tool_call": {"name": f"tool_{i}"}} for i in range(6)]
        mgr = ContextBudgetManager()
        mgr._rebuild_after_compaction(ctx, compacted_count=4, summary="test summary")
        # First entry should be summary note
        assert ctx.tool_results[0].get("compacted") is True
        assert ctx.tool_results[0].get("summary") == "test summary"
        # Remaining entries should be the tail (entries 4,5 → now indices 1,2)
        assert len(ctx.tool_results) == 3  # 1 summary + 2 tail

    def test_tool_results_max_cap(self):
        """_rebuild 后 tool_results 总量应封顶"""
        ctx = RunContext("test")
        many = [{"tool_call": {"name": "t"}, "result": {}, "success": True} for _ in range(30)]
        ctx.tool_results = many
        ctx._conversation_history = [{"role": "assistant", "content": "hello"}] * 5
        mgr = ContextBudgetManager()
        mgr._rebuild_after_compaction(ctx, compacted_count=25, summary="cap test")
        # After compacting 25 and keeping summary + 5 tail, but cap is 16
        # tail had 5 entries, now [summary, tail...] = 6 total → within cap
        assert len(ctx.tool_results) <= 16

    def test_conversation_history_rebuilt(self):
        ctx = RunContext("test")
        ctx.tool_results = [{"tool_call": {"name": "t"}, "result": {}, "success": True} for _ in range(6)]
        ctx._conversation_history = [
            {"role": "tool", "content": f"msg_{i}", "tool_call_id": f"c{i}", "name": "t"}
            for i in range(12)
        ]
        mgr = ContextBudgetManager(history_token_budget=9999)
        mgr._rebuild_after_compaction(ctx, compacted_count=4, summary="rebuilt test")
        # First entry should be the summary system message
        assert ctx._conversation_history[0]["role"] == "system"
        assert "rebuilt test" in ctx._conversation_history[0]["content"]
        # Remaining should be the tail messages (less than original)
        assert len(ctx._conversation_history) < 12
        assert len(ctx._conversation_history) >= 1


# ── Test: replay instructions ─────────────────────────────

class TestReplay:
    def test_forced_instructions_set(self):
        ctx = RunContext("test")
        ctx.tool_results = list(SAMPLE_ENTRIES[:3])
        mgr = ContextBudgetManager()
        mgr._set_replay_instructions(ctx, "summary: done some work")
        assert ctx.forced_instructions != ""
        assert "summary" in ctx.forced_instructions.lower() or "上下文" in ctx.forced_instructions


# ── Test: ConversationStore ───────────────────────────────

class TestConversationStore:
    @pytest.fixture
    def store(self):
        from core.multi_agent_v2.agents.conversation_store import ConversationStore
        # Use in-memory SQLite for testing
        import tempfile, os
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        path = f.name
        f.close()
        store = ConversationStore(path)
        yield store
        os.unlink(path)

    def test_save_and_get_session(self, store):
        store.save_session("test1", "do something", {"source": "test"})
        session = store.load_session("test1")
        assert session is not None
        assert "do something" in str(session["task_description"])

    def test_save_tool_result(self, store):
        store.save_session("test2", "task")
        entry = make_entry("web_search", True, {"query": "test"}, {"result": "data"})
        store.save_tool_result("test2", 1, entry)
        # verify no error
        assert True

    def test_save_compaction(self, store):
        store.save_session("test3", "task")
        store.save_compaction("test3", 5, "summary text", 2)
        latest = store.get_latest_compaction("test3")
        assert latest is not None
        assert latest["summary"] == "summary text"
        assert latest["tail_start_round"] == 2

    def test_get_summaries(self, store):
        store.save_session("test4", "task")
        store.save_compaction("test4", 3, "s1", 1)
        store.save_compaction("test4", 6, "s2", 2)
        summaries = store.get_compaction_summaries("test4")
        assert len(summaries) == 2
        assert summaries == ["s1", "s2"]


# ── Test: check_and_compact (with LLM mocked) ─────────────

class TestAsyncCompact:
    @pytest.mark.asyncio
    async def test_async_compact_no_overflow(self):
        ctx = RunContext("test")
        ctx.tool_results = []
        mgr = ContextBudgetManager()
        result = await mgr.async_check_and_compact(ctx)
        assert result is False  # no overflow

    @pytest.mark.asyncio
    async def test_async_compact_overflow_large(self):
        """超大量上下文应触发压缩"""
        ctx = RunContext("test " * 1000)
        ctx.tool_results = [
            make_entry("web_search", True, {"query": f"q{i}"}, {"result": "x" * 5000})
            for i in range(10)
        ]
        mgr = ContextBudgetManager(
            max_context_chars=1000, safety_margin=0,
            protected_recent_turns=2, min_rounds_before_compact=2,
            use_llm_compaction=False,  # use template for speed
        )
        result = await mgr.async_check_and_compact(ctx)
        assert result is True
        # Should have been reordered
        assert any(r.get("compacted") for r in ctx.tool_results)
        assert ctx.forced_instructions != ""  # replay set

    @pytest.mark.asyncio
    async def test_async_compact_llm_fallback(self):
        """LLM 压缩失败时自动回退到模板"""
        ctx = RunContext("test")
        ctx.tool_results = [
            make_entry("web_search", True, {"query": "t"}, {"result": "d" * 5000})
            for _ in range(8)
        ]
        mgr = ContextBudgetManager(
            max_context_chars=100, safety_margin=0,
            protected_recent_turns=1, min_rounds_before_compact=2,
            use_llm_compaction=True,
        )
        with patch.object(mgr, '_llm_summarize') as mock_llm:
            mock_llm.return_value = ""
            result = await mgr.async_check_and_compact(ctx)
            assert result is True  # should still compact with template fallback
