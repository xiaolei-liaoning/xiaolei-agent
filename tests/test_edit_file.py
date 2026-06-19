#!/usr/bin/env python3
"""
测试 edit_file 工具的模糊匹配能力
"""

import asyncio
import tempfile
from pathlib import Path

from core.multi_agent_v2.tools.tool_registry import _handle_edit_file


async def main():
    # 创建测试文件（故意与 old_text 有缩进差异）
    test_content = """def hello():
    print('hello world')
    return True

def goodbye():
    print('goodbye')
    return False
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(test_content)
    temp_path = Path(f.name)

    try:
        # 测试场景1：缩进不一致的多行代码
        print("=== 测试1：缩进不一致的多行代码 ===")
        args = {
            "path": str(temp_path),
            "old_string": "print('hello world')\nreturn True",  # 期望 4-space
            "new_string": "print('hello there')\nreturn False",
            "replace_all": False,
        }
        result = await _handle_edit_file(args)
        print(f"结果: {result['ok']}")
        if result["ok"]:
            print(f"提示: {result['data']}")
            print(f"Diff:\n{result['diff']}")
        else:
            print(f"错误: {result['error']}")

        # 测试场景2：故意写错一个字母（中间行，3行以上）
        print("\n=== 测试2：3行以上，中间行有 typo ===")
        args = {
            "path": str(temp_path),
            "old_string": "def hello():\nprint('hello there')\nretun False",  # typo: retun
            "new_string": "def hello():\n    print('hello again')\n    return True",
            "replace_all": False,
        }
        result = await _handle_edit_file(args)
        print(f"结果: {result['ok']}")
        if result["ok"]:
            print(f"提示: {result['data']}")
            print(f"Diff:\n{result['diff']}")
            # 读取修改后的内容
            with open(temp_path, "r", encoding="utf-8") as f:
                new_content = f.read()
            print(f"\n修改后内容:\n{new_content}")
        else:
            print(f"错误: {result['error']}")

        # 测试场景3：空白不一致
        print("\n=== 测试3：空白不一致 ===")
        args = {
            "path": str(temp_path),
            "old_string": "def   hello() :",  # 多余空格
            "new_string": "def hello():",
            "replace_all": False,
        }
        result = await _handle_edit_file(args)
        print(f"结果: {result['ok']}")
        if result["ok"]:
            print(f"提示: {result['data']}")
            print(f"Diff:\n{result['diff']}")
        else:
            print(f"错误: {result['error']}")

    finally:
        temp_path.unlink()


if __name__ == "__main__":
    asyncio.run(main())
