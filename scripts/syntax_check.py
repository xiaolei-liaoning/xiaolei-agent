#!/usr/bin/env python3
"""语法检查脚本 — 替代 python3 -c "import ast; ast.parse(...)" 单行命令

用法:
  python3 scripts/syntax_check.py <file1.py> [file2.py ...]
"""
import ast
import sys
import py_compile


def check_file(filepath: str) -> bool:
    try:
        ast.parse(open(filepath, encoding='utf-8').read())
        py_compile.compile(filepath, doraise=True)
        return True
    except SyntaxError as e:
        print(f"❌ {filepath}: SyntaxError - {e}")
        return False
    except Exception as e:
        print(f"❌ {filepath}: {type(e).__name__} - {e}")
        return False


if __name__ == "__main__":
    files = sys.argv[1:]
    if not files:
        print("用法: python3 scripts/syntax_check.py <file.py> [file2.py ...]")
        sys.exit(0)

    ok = True
    for f in files:
        result = check_file(f)
        if result:
            print(f"✅ {f}")
        ok = ok and result

    sys.exit(0 if ok else 1)
