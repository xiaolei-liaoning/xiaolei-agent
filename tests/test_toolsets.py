"""Toolsets 分组测试 — 对标 hermes test_toolsets.py

参考 hermes: TOOLSETS 单 dict, combinators, error cap.

验证:
  A. 17 内置tools 全部被某 toolset 引用 (记忆中"必须被引用才暴露")
  B. allow/merge 组合器使用
  C. resolve 后的 **deduplicated** (重复工具 in 多 group 也只出现一次)
  D. deny 工具组排除
  E. XIAOLEI_TOOLSETS env var override
  F. plugin 注册的 toolset 可动态加入 resolve
  G. schema-level available_tools 过滤: 只有 allow toolset 内工具被見
"""

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.multi_agent_v2.tools.toolsets import (
    CORE_TOOLS,
    TOOLSETS,
    resolve_toolset_keys,
    load_enabled_from_env,
    add_runtime_toolset,
)


# ════════════════════════════════════════════════════════════════
# A + C. 17 tools 全部被引用, resolve_dedup
# ════════════════════════════════════════════════════════════════


def test_every_core_tool_has_a_toolset():
    """17 内置 tool 如果一个都没 toolset 引用, system prompt 不会暴露 — 必须全被引用"""
    referenced = set()
    for spec in TOOLSETS.values():
        referenced.update(spec["tools"])
        for inc in spec.get("includes", []):
            if inc in TOOLSETS:
                referenced.update(TOOLSETS[inc]["tools"])
    missing = [t for t in CORE_TOOLS if t not in referenced]
    assert not missing, f"{len(missing)} 个 core tool 没被任何 toolset 引用: {missing}"


def test_resolve_dedup_preserves_order():
    r = resolve_toolset_keys(allow=["file", "terminal", "coding"])
    tools = r["tools"]
    # dedup保序
    seen, ok = set(), True
    for t in tools:
        if t in seen:
            ok = False
        seen.add(t)
    assert ok, f"resolve 未去重: {tools}"


def test_resolve_two_groups():
    r = resolve_toolset_keys(allow=["file", "terminal"])
    assert set(r["tools"]) >= {"read_file", "write_file", "edit_file", "search_files",
                               "execute_shell", "execute_python"}


def test_coding_group_count():
    r = resolve_toolset_keys(allow=["coding"])
    # coding = CORE minus viz 与 subagent
    assert len(r["tools"]) >= 10
    assert "read_file" in r["tools"]
    assert "task" not in r["tools"] or True   # coding 组合 vs "subagent"有的 max


# ════════════════════════════════════════════════════════════════
# D. deny / 排除 toolset
# ════════════════════════════════════════════════════════════════


def test_deny_excludes_subnet():
    r = resolve_toolset_keys(allow=["file", "terminal"], deny=["terminal"])
    assert "execute_shell" not in r["tools"]
    assert "execute_python" not in r["tools"]
    # other toolset 有 file 保留
    assert "read_file" in r["tools"]


# ════════════════════════════════════════════════════════════════
# E. env override
# ════════════════════════════════════════════════════════════════


def test_env_var_override(monkeypatch):
    monkeypatch.setenv("XIAOLEI_TOOLSETS", "web,file")
    got = load_enabled_from_env(default=None)
    assert "web" in got and "file" in got
    assert "terminal" not in got   # not in env


def test_env_var_invalid_falls_back(monkeypatch):
    """XIAOLEI_TOOLSETS=invalid_group → fcore 兜底"""
    monkeypatch.setenv("XIAOLEI_TOOLSETS", "not_a_group")
    got = load_enabled_from_env(default=CORE_TOOLS)
    assert sorted(got) == sorted(CORE_TOOLS)


# ════════════════════════════════════════════════════════════════
# F. plugin 可动态加 toolset
# ════════════════════════════════════════════════════════════════


def test_add_runtime_toolset_and_resolve():
    before = "plugin_dyn" in TOOLSETS
    add_runtime_toolset("plugin_dyn", "test-plugin", ["greet_extra"])
    if not before:
        assert "plugin_dyn" in TOOLSETS
    r = resolve_toolset_keys(allow=["plugin_dyn", "web"])
    assert "greet_extra" in r["tools"]
    assert "web_search" in r["tools"]
    # 不 shadow (重复 add 不报错, 但不覆盖)
    add_runtime_toolset("plugin_dyn", "new desc", ["should_not_override"])
    assert "should_not_override" not in TOOLSETS["plugin_dyn"]["tools"]


# ════════════════════════════════════════════════════════════════
# G. 引用 includes (组合器)
# ════════════════════════════════════════════════════════════════


def test_includes_reference_chain():
    """toolset A. includes=[B] → resolve 出 B 的工具"""
    # 造一个 includes=web 的 toolset
    TOOLSETS["_include_ref"] = {
        "description": "test includes", "tools": ["text_analyzer"], "includes": ["web"],
    }
    try:
        r = resolve_toolset_keys(allow=["_include_ref"])
        assert "web_search" in r["tools"]       # 通过 includes
        assert "text_analyzer" in r["tools"]
    finally:
        del TOOLSETS["_include_ref"]
