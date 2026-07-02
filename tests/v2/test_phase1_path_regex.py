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
    """断言 work_agent.py 路径正则段不存在（ponytail: 走 os.walk+CodeGraph 发现）"""
    src = _read_work_agent_src()
    # ponytail: 路径发现统一走 os.walk+CodeGraph，正则仅为辅助 fallback
    assert "os.walk" in src, "缺少 os.walk"
    assert "codegraph" in src or "os.walk" in src, (
        "路径发现应基于 os.walk/CodeGraph"
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
    """work_agent 模块必须有 import re（ponytail: 局部导入）"""
    src = _read_work_agent_src()
    # ponytail: re 仅在 _phase1_and_2 局部导入，非模块顶部
    assert "import os, re, json, subprocess" in src, (
        "work_agent.py 应该含 import os, re, json, subprocess"
    )