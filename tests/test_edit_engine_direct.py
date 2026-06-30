#!/usr/bin/env python3
"""
直接测试 edit_engine.replace 函数

注意：edit_engine 已归档，当前合并为 core/multi_agent_v2/tools/edit.py。
此测试整体 skip 直到重新设计对 SmartEditor 的新测试。
"""
import pytest
pytest.skip("edit_engine 已归档为 tools/edit.py 的 SmartEditor", allow_module_level=True)

from core.multi_agent_v2.tools.edit_engine import (
    block_anchor_replacer,
    replace,
    whitespace_normalized_replacer,
)


# 测试 block_anchor_replacer
def test_block_anchor():
    print("=== 测试 block_anchor_replacer ===")
    content = "def hello():\n    print('hello there')\n    return False"
    find = "def hello():\nprint('hello there')\nretun False"  # typo: retun

    # 拆分参数
    find_lines = find.split("\n")
    print(f"find_lines: {find_lines}")
    print(f"len(find_lines): {len(find_lines)}")

    candidates = list(block_anchor_replacer(content, find))
    print(f"匹配到: {candidates}")
    if candidates:
        print(f"替换后: {content.replace(candidates[0], 'REPLACED')}")


# 测试 whitespace_normalized_replacer
def test_whitespace_normalized():
    print("\n=== 测试 whitespace_normalized_replacer ===")
    content = "def hello():"
    find = "def   hello() :"
    candidates = list(whitespace_normalized_replacer(content, find))
    print(f"匹配到: {candidates}")
    if candidates:
        print(f"替换后: {content.replace(candidates[0], 'def hello():')}")


# 测试 replace 主函数
def test_replace():
    print("\n=== 测试 replace 主函数 ===")
    content = "def hello():\n    print('hello world')\n    return True"

    # 测试缩进不一致
    try:
        result = replace(
            content,
            "print('hello world')\nreturn True",
            "print('hello there')\nreturn False",
        )
        print(f"缩进不一致测试成功: {result}")
    except Exception as e:
        print(f"缩进不一致测试失败: {e}")

    # 测试空白不一致
    try:
        result = replace(content, "def   hello() :", "def hello():")
        print(f"空白不一致测试成功: {result}")
    except Exception as e:
        print(f"空白不一致测试失败: {e}")


if __name__ == "__main__":
    test_block_anchor()
    test_whitespace_normalized()
    test_replace()
