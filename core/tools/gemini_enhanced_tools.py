"""
语言检测工具 — 检测代码语言、扩展名和默认文件名

只在 tool_registry.py 中被引用。
"""

import logging
from typing import Tuple

logger = logging.getLogger(__name__)


def _has_python_indicators(code: str) -> bool:
    """检查代码是否有 Python 特征（用于防止 HTML 字符串误检测）"""
    py_indicators = ["def ", "class ", "import ", "from ", "print(",
                     "if __name__", "elif ", "except:", "finally:",
                     "with open", "os.", "sys.", "json.", "asyncio",
                     "await ", "async def", "return "]
    score = sum(1 for ind in py_indicators if ind in code)
    return score >= 2


def detect_code_language(code: str) -> Tuple[str, str, str]:
    """
    检测代码语言

    Returns: (language, extension, default_filename)
    """
    code_stripped = code.strip()

    # HTML（但在 Python 特征明显时优先判定为 Python）
    if code_stripped.startswith("<!DOCTYPE") or code_stripped.startswith("<html"):
        if not _has_python_indicators(code):
            return ("html", ".html", "game")
    if "<html" in code_stripped or "</html>" in code_stripped:
        if not _has_python_indicators(code):
            return ("html", ".html", "game")

    # XML
    if code_stripped.startswith("<?xml") or code_stripped.startswith("<rss"):
        return ("xml", ".xml", "output")

    # JSON
    if code_stripped.startswith("{") and code_stripped.endswith("}"):
        try:
            import json as _json
            _json.loads(code_stripped)
            return ("json", ".json", "data")
        except Exception:
            pass

    # Shell
    if code_stripped.startswith("#!/bin/bash") or code_stripped.startswith("#!/bin/sh"):
        return ("shell", ".sh", "script")

    # 语言特征评分
    py_indicators = ["def ", "class ", "import ", "from ", "print(", "if __name__", "elif ", "except:", "finally:"]
    js_indicators = ["function ", "function(", "var ", "let ", "const ", "=>", "document.", "window.",
                     "addEventListener", "getElementById", "console.log", "innerHTML"]

    py_score = sum(1 for ind in py_indicators if ind in code_stripped)
    js_score = sum(1 for ind in js_indicators if ind in code_stripped)

    # Java (在 Python 之前)
    if "public class " in code_stripped or "public static void main" in code_stripped:
        return ("java", ".java", "Main")

    if py_score > js_score:
        return ("python", ".py", "script")

    # JavaScript
    if js_score >= 2:
        if "require(" in code_stripped or "module.exports" in code_stripped:
            return ("javascript", ".js", "script")
        return ("javascript", ".html", "game")

    # TypeScript
    if ": string" in code_stripped or ": number" in code_stripped or "interface " in code_stripped:
        return ("typescript", ".ts", "script")

    # CSS
    if "{" in code_stripped and any(k in code_stripped for k in ["color:", "margin:", "padding:", "font-size:"]):
        return ("css", ".css", "style")

    # Go
    if "package main" in code_stripped and "func main()" in code_stripped:
        return ("go", ".go", "main")

    # Rust
    if "fn main()" in code_stripped and any(k in code_stripped for k in ["let ", "mut "]):
        return ("rust", ".rs", "main")

    # C/C++
    if "#include <stdio.h>" in code_stripped or "int main(" in code_stripped:
        if "iostream" in code_stripped or "std::" in code_stripped or "class " in code_stripped:
            return ("cpp", ".cpp", "main")
        return ("c", ".c", "main")
    if "#include <iostream>" in code_stripped or "std::" in code_stripped:
        return ("cpp", ".cpp", "main")

    # PHP
    if code_stripped.startswith("<?php"):
        return ("php", ".php", "index")

    # SQL
    if any(kw in code_stripped.upper() for kw in ["SELECT ", "CREATE TABLE", "INSERT INTO", "ALTER TABLE"]):
        return ("sql", ".sql", "query")

    # Ruby
    if code_stripped.startswith("require ") or "puts " in code_stripped:
        return ("ruby", ".rb", "script")

    return ("python", ".py", "script")
