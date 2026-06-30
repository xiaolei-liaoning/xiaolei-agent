"""
Phase 1 路径正则中文支持测试 — V2-C8
直接通过源码扫描验证 work_agent.py 中路径正则含有中文范围
"""
import os

import pytest


def _read_work_agent_src() -> str:
    import core.multi_agent_v2.agents.base.work_agent as wa
    with open(wa.__file__) as f:
        return f.read()


def test_phase1_regex_contains_chinese_range():
    """断言 work_agent.py 路径正则段含 [\u4e00-\u9fff] 中文范围"""
    src = _read_work_agent_src()
    # 定位路径提取那一段
    assert "# 1. 提取路径" in src, "找不到路径提取段"
    idx = src.index("# 1. 提取路径")
    snippet = src[idx:idx + 500]
    # 含中文范围
    assert "\\u4e00" in snippet or "[一-" in snippet, (
        f"路径正则应含中文范围 \\u4e00-\\u9fff，实际片段：{snippet[:200]!r}"
    )


def test_phase1_chinese_path_matches_with_fixed_regex():
    """用修复后的正则验证含中文路径能完整匹配"""
    import tempfile
    with tempfile.TemporaryDirectory(suffix="_副本") as tmpdir:
        desc = f"{tmpdir} 分析这个项目"
        # 用修复后的正则
        for pat in [r'(~[^\s，,]+/[\w\u4e00-\u9fff./-]+)',
                    r'(/[\w\u4e00-\u9fff./-]+)',
                    r'(\.\.[\w\u4e00-\u9fff./-]+)']:
            import re
            m = re.search(pat, desc)
            if m:
                c = os.path.expanduser(m.group(1))
                if os.path.isdir(c):
                    assert c == tmpdir
                    return
    pytest.fail("含中文路径未匹配")


def test_phase1_english_path_matches_with_fixed_regex():
    """英文路径不回归"""
    import re, tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        desc = f"{tmpdir} task"
        for pat in [r'(~[^\s，,]+/[\w\u4e00-\u9fff./-]+)',
                    r'(/[\w\u4e00-\u9fff./-]+)',
                    r'(\.\.[\w\u4e00-\u9fff./-]+)']:
            m = re.search(pat, desc)
            if m:
                c = os.path.expanduser(m.group(1))
                if os.path.isdir(c):
                    assert c == tmpdir
                    return
    pytest.fail("英文路径未匹配")


def test_workagent_import_re_not_missing():
    """work_agent 模块顶部必须有 import re"""
    src = _read_work_agent_src()
    # 模块顶部 import 区段（前面 30 行）
    head = src[:1500]
    assert "import re" in head, "work_agent.py 顶部应该含 import re"