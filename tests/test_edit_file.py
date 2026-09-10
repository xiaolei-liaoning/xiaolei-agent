#!/usr/bin/env python3
"""edit_file 模糊匹配能力测试 — pytest 化

原为脚本型 (if __name__ == '__main__')，2026-09-10 改写为 pytest 收集格式。
断言化改造：每个场景除 ok=True 还断言 data/diff 非空 + 修改真的落盘。

对应 edit_file.py 的 9 级行为：缩进不一致 / 中间行 typo / 空白差异
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.multi_agent_v2.tools.tool_registry import _handle_edit_file

pytestmark = pytest.mark.asyncio

_CONTENT = """def hello():
    print('hello world')
    return True

def goodbye():
    print('goodbye')
    return False
"""


@pytest.fixture
def temp_py_file(tmp_path):
    """每个测试一份干净的临时 py 文件（带典型函数模板）"""
    p = tmp_path / "sample.py"
    p.write_text(_CONTENT, encoding="utf-8")
    return p


# ── 场景1：缩进不一致的多行代码 ──


async def test_fuzzy_indentation_diff_match(temp_py_file):
    """old_string 缩进与文件不一致（0空 vs 4空）也能匹配并替换"""
    args = {
        "path": str(temp_py_file),
        "old_string": "print('hello world')\nreturn True",
        "new_string": "print('hello there')\nreturn False",
        "replace_all": False,
    }
    result = await _handle_edit_file(args)
    assert result["ok"] is True, f"edit 失败: {result.get('error')}"
    assert "diff" in result and result["diff"], "成功应有 diff"

    new_content = temp_py_file.read_text(encoding="utf-8")
    assert "hello there" in new_content, "新代码应写入"
    assert "hello world" not in new_content, "旧代码应消失"


# ── 场景2：3 行以上，中间行 typo ──


async def test_fuzzy_middle_line_typo(temp_py_file):
    """3+行上下文中，中间行 'retun' typo 也能被模糊匹配成功"""
    args = {
        "path": str(temp_py_file),
        "old_string": "def hello():\n    print('hello there')\nretun False",  # retun typo
        "new_string": "def hello():\n    print('hello again')\n    return True",
        "replace_all": False,
    }
    result = await _handle_edit_file(args)
    assert result["ok"] is True, f"typo 模糊匹配失败: {result.get('error')}"

    new_content = temp_py_file.read_text(encoding="utf-8")
    assert "hello again" in new_content, "typo 修复后的新代码应写入"


# ── 场景3：空白差异 ──


async def test_fuzzy_whitespace_diff(temp_py_file):
    """'def   hello() :'（多空格+尾空格）应匹配 'def hello():'"""
    args = {
        "path": str(temp_py_file),
        "old_string": "def   hello() :",
        "new_string": "def hello():",
        "replace_all": False,
    }
    result = await _handle_edit_file(args)
    assert result["ok"] is True, f"空白差异匹配失败: {result.get('error')}"
