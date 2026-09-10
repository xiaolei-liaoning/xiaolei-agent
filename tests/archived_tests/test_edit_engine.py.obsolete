"""
edit_engine 单元测试 — 9 种级联替换策略
"""

import pytest
pytest.importorskip("core.multi_agent_v2.tools.edit_engine",
                     reason="edit_engine 已归档，需要时从 archived/ 恢复")

from core.multi_agent_v2.tools.edit_engine import (
    block_anchor_replacer,
    context_aware_replacer,
    escape_normalized_replacer,
    generate_diff,
    indentation_flexible_replacer,
    is_disproportionate_match,
    levenshtein,
    line_trimmed_replacer,
    multi_occurrence_replacer,
    replace,
    simple_replacer,
    trim_diff,
    trimmed_boundary_replacer,
    whitespace_normalized_replacer,
)


# ── 1. SimpleReplacer ──────────────────────────────────────
class TestSimpleReplacer:
    def test_exact_match(self):
        content = "hello world\nfoo bar"
        assert list(simple_replacer(content, "hello world")) == ["hello world"]

    def test_no_match(self):
        assert list(simple_replacer("abc", "xyz")) == []

    def test_empty_find(self):
        assert list(simple_replacer("abc", "")) == []

    def test_trailing_newline(self):
        content = "line1\nline2\n"
        assert list(simple_replacer(content, "line1\nline2\n")) == ["line1\nline2\n"]


# ── 2. Levenshtein 工具 ──────────────────────────────────
class TestLevenshtein:
    def test_equal(self):
        assert levenshtein("abc", "abc") == 0

    def test_one_empty(self):
        assert levenshtein("", "abc") == 3
        assert levenshtein("abc", "") == 3

    def test_insert_delete(self):
        assert levenshtein("kitten", "sitting") == 3

    def test_both_empty(self):
        assert levenshtein("", "") == 0


# ── 3. LineTrimmedReplacer ────────────────────────────────
class TestLineTrimmedReplacer:
    def test_extra_whitespace(self):
        content = "  hello  \n  world  "
        find = "hello\nworld"
        candidates = list(line_trimmed_replacer(content, find))
        assert len(candidates) >= 1
        assert candidates[0] == "  hello  \n  world  "

    def test_tab_diff(self):
        content = "\thello\n\tworld"
        find = "  hello\n  world"
        assert list(line_trimmed_replacer(content, find))

    def test_no_match(self):
        content = "hello\nworld"
        assert not list(line_trimmed_replacer(content, "hello\nfoo"))

    def test_single_line(self):
        content = "  hello  "
        assert list(line_trimmed_replacer(content, "hello"))


# ── 4. BlockAnchorReplacer ────────────────────────────────
class TestBlockAnchorReplacer:
    def test_anchors_plus_fuzzy_middle(self):
        content = "first\nhello world\nlast"
        find = "first\nhello wrold\nlast"  # 故意写错一个字母
        candidates = list(block_anchor_replacer(content, find))
        assert candidates

    def test_missing_anchor_fails(self):
        content = "first\nmiddle\nlast"
        find = "nomatch\nmiddle\nlast"
        assert not list(block_anchor_replacer(content, find))

    def test_less_than_three_lines_skipped(self):
        content = "a\nb"
        find = "a\nb"
        assert not list(block_anchor_replacer(content, find))


# ── 5. WhitespaceNormalizedReplacer ──────────────────────
class TestWhitespaceNormalizedReplacer:
    def test_multiple_spaces(self):
        content = "hello    world"
        find = "hello world"
        assert list(whitespace_normalized_replacer(content, find))

    def test_multiline_with_mixed_ws(self):
        # 每行内有多余空格/边界空格，归一化后应能匹配
        content = "  if   x   ==   1:\n      pass  \n"
        find = "if x == 1:\n    pass"
        result = list(whitespace_normalized_replacer(content, find))
        assert result, "逐行 normalize_ws 后应能匹配多余空格的整段"


# ── 6. IndentationFlexibleReplacer ───────────────────────
class TestIndentationFlexibleReplacer:
    def test_different_indent(self):
        content = "        def foo():\n            return 1"
        find = "    def foo():\n        return 1"
        candidates = list(indentation_flexible_replacer(content, find))
        assert candidates

    def test_no_indent_same(self):
        content = "    def foo():\n        pass"
        find = "    def foo():\n        pass"
        assert list(indentation_flexible_replacer(content, find))


# ── 7. EscapeNormalizedReplacer ──────────────────────────
class TestEscapeNormalizedReplacer:
    def test_newline_escape(self):
        content = "line1\nline2"
        find = "line1\\nline2"
        assert list(escape_normalized_replacer(content, find))

    def test_no_escape_does_not_yield(self):
        content = "hello"
        find = "hello"
        assert not list(escape_normalized_replacer(content, find))


# ── 8. TrimmedBoundaryReplacer ───────────────────────────
class TestTrimmedBoundaryReplacer:
    def test_boundary_whitespace(self):
        content = "  hello world  "
        find = "hello world"
        assert list(trimmed_boundary_replacer(content, find))

    def test_multiline_boundary(self):
        content = "  hello\n  world  "
        find = "hello\nworld"
        assert list(trimmed_boundary_replacer(content, find))


# ── 9. ContextAwareReplacer ──────────────────────────────
class TestContextAwareReplacer:
    def test_most_middles_match(self):
        # 5 行中间，3 行精确 → ≥ 50%
        content = "start\naaa\nbbb\nccc\nddd\nend"
        find = "start\naaa\nbbb\nxxx\nyyy\nend"
        candidates = list(context_aware_replacer(content, find))
        assert candidates

    def test_few_middles_fail(self):
        content = "start\naaa\nbbb\nccc\nend"
        find = "start\nzzz\nyyy\nxxx\nend"  # 0 个精确匹配
        assert not list(context_aware_replacer(content, find))


# ── 10. MultiOccurrenceReplacer ──────────────────────────
class TestMultiOccurrenceReplacer:
    def test_multiple_hits(self):
        content = "abc abc abc"
        candidates = list(multi_occurrence_replacer(content, "abc"))
        assert len(candidates) == 3


# ── 11. replace() 主入口 ─────────────────────────────────
class TestReplaceMain:
    def test_exact_single_replace(self):
        result = replace("hello world", "world", "there", replace_all=False)
        assert result == "hello there"

    def test_replace_all(self):
        result = replace("abc abc abc", "abc", "xyz", replace_all=True)
        assert result == "xyz xyz xyz"

    def test_multiple_matches_raises_without_replace_all(self):
        with pytest.raises(ValueError, match="找到 .* 处匹配"):
            replace("abc abc abc", "abc", "xyz", replace_all=False)

    def test_not_found_raises(self):
        with pytest.raises(ValueError, match="未在文件中找到"):
            replace("hello world", "nomatch", "xxx")

    def test_empty_old_raises(self):
        with pytest.raises(ValueError, match="不能为空"):
            replace("abc", "", "x")

    def test_old_equals_new_raises(self):
        with pytest.raises(ValueError, match="无需替换"):
            replace("abc", "abc", "abc")

    def test_fuzzy_line_trimmed_succeeds(self):
        content = "    foo bar\n    baz qux\n"
        find = "foo bar\nbaz qux"  # 没有前导空格
        result = replace(content, find, "replaced\nstuff", replace_all=False)
        assert "replaced" in result and "stuff" in result
        assert "foo bar" not in result

    def test_whitespace_normalized_succeeds(self):
        content = "if    x    ==    1:"
        find = "if x == 1:"
        result = replace(content, find, "if x == 2:")
        assert result == "if x == 2:"


# ── 12. is_disproportionate_match ───────────────────────
class TestDisproportionate:
    def test_rejects_large_diff(self):
        assert (
            is_disproportionate_match("a" * 1000, "small target text to find") is True
        )

    def test_accepts_same_size(self):
        assert is_disproportionate_match("hello world", "hello wrold") is False

    def test_single_line_accepts(self):
        assert is_disproportionate_match("a short line", "a short line") is False


# ── 13. Diff 生成 ────────────────────────────────────────
class TestDiff:
    def test_basic_generate_diff(self):
        diff = generate_diff("a\nb\nc\n", "a\nx\nc\n", "f.txt")
        assert diff
        assert "-b" in diff
        assert "+x" in diff
        assert "f.txt" in diff

    def test_no_change_empty(self):
        assert generate_diff("a\n", "a\n", "f.txt") == ""

    def test_trim_diff_keeps_changes(self):
        diff = generate_diff("a\nb\nc\n", "a\nx\nc\n", "f.txt")
        trimmed = trim_diff(diff)
        assert "-b" in trimmed and "+x" in trimmed

    def test_trim_diff_on_empty(self):
        assert trim_diff("") == ""


# ── 14. 端到端：多策略级联 ─────────────────────────────
class TestEndToEndCascade:
    def test_simple_does_not_need_cascade(self):
        assert replace("abc\ndef\n", "abc", "xyz") == "xyz\ndef\n"

    def test_indent_different_falls_through_to_indent_replacer(self):
        content = "def foo():\n" "    if True:\n" "        print('hi')\n"
        find = "if True:\n    print('hi')"  # 4-space 期望
        new_text = "if False:\n    print('nope')"
        result = replace(content, find, new_text)
        assert "if False:" in result
        assert "print('nope')" in result
        assert "print('hi')" not in result

    def test_block_anchor_handles_typo_in_middle(self):
        content = "START\nthe quick brown fox\nEND\n"
        find = "START\nthe quick brown fx\nEND"  # 中间行有 typo
        result = replace(content, find, "START\nREPLACED\nEND")
        assert "REPLACED" in result
        assert "quick brown fox" not in result
