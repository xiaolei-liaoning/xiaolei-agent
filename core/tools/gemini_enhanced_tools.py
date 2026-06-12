"""
Gemini-CLI 工具算法 Python 移植版

移植自 gemini-cli/packages/core/src/tools/
核心算法: edit.ts (4层回退策略), shell.ts (注入检测), write-file.ts (LLM修正)

License: Apache-2.0 (Google LLC, 2025)
"""

import re
import os
import hashlib
import logging
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# 1. 编辑工具 — 4层回退策略 (移植自 edit.ts)
# ═══════════════════════════════════════════════════════════════════════

class EditStrategy(Enum):
    EXACT = "exact"
    FLEXIBLE = "flexible"
    REGEX = "regex"
    FUZZY = "fuzzy"
    FAILED = "failed"


@dataclass
class ReplacementResult:
    new_content: str
    occurrences: int
    final_old_string: str
    final_new_string: str
    strategy: EditStrategy
    match_ranges: Optional[List[Tuple[int, int]]] = None


def _detect_line_ending(content: str) -> str:
    """检测行尾符类型"""
    if "\r\n" in content:
        return "\r\n"
    return "\n"


def _restore_trailing_newline(original: str, modified: str) -> str:
    """恢复尾部换行符"""
    had_trailing = original.endswith("\n")
    if had_trailing and not modified.endswith("\n"):
        return modified + "\n"
    elif not had_trailing and modified.endswith("\n"):
        return modified.rstrip("\n")
    return modified


def _apply_indentation(lines: List[str], target_indent: str) -> List[str]:
    """应用目标缩进，保留相对缩进"""
    if not lines:
        return []
    ref_line = lines[0]
    ref_match = re.match(r"^([ \t]*)", ref_line)
    ref_indent = ref_match.group(1) if ref_match else ""

    result = []
    for line in lines:
        if line.strip() == "":
            result.append("")
        elif line.startswith(ref_indent):
            result.append(target_indent + line[len(ref_indent):])
        else:
            result.append(target_indent + line.lstrip())
    return result


def _safe_literal_replace(content: str, old: str, new: str) -> str:
    """安全的字面替换，处理 $ 序列"""
    import re as _re
    escaped = _re.escape(old)
    return _re.sub(escaped, lambda m: new, content, count=1)


def _escape_regex(s: str) -> str:
    """转义正则特殊字符"""
    return re.escape(s)


# --- Strategy 1: 精确匹配 ---
def _calculate_exact_replacement(
    content: str, old_string: str, new_string: str, allow_multiple: bool = False
) -> Optional[ReplacementResult]:
    normalized_search = old_string.replace("\r\n", "\n")
    normalized_replace = new_string.replace("\r\n", "\n")

    count = content.count(normalized_search)

    if count == 0:
        return None
    if not allow_multiple and count > 1:
        return ReplacementResult(
            new_content=content, occurrences=count,
            final_old_string=normalized_search, final_new_string=normalized_replace,
            strategy=EditStrategy.EXACT
        )

    new_content = _safe_literal_replace(content, normalized_search, normalized_replace)
    new_content = _restore_trailing_newline(content, new_content)
    return ReplacementResult(
        new_content=new_content, occurrences=count,
        final_old_string=normalized_search, final_new_string=normalized_replace,
        strategy=EditStrategy.EXACT
    )


# --- Strategy 2: 弹性匹配 (去空白) ---
def _calculate_flexible_replacement(
    content: str, old_string: str, new_string: str, allow_multiple: bool = False
) -> Optional[ReplacementResult]:
    normalized_search = old_string.replace("\r\n", "\n")
    normalized_replace = new_string.replace("\r\n", "\n")

    source_lines = content.split("\n")
    search_lines = [l.strip() for l in normalized_search.split("\n")]
    replace_lines = normalized_replace.split("\n")

    flexible_occurrences = 0
    i = 0
    while i <= len(source_lines) - len(search_lines):
        window = source_lines[i:i + len(search_lines)]
        window_stripped = [l.strip() for l in window]

        if window_stripped == search_lines:
            flexible_occurrences += 1
            first_line = window[0]
            indent_match = re.match(r"^([ \t]*)", first_line)
            indent = indent_match.group(1) if indent_match else ""

            new_block = _apply_indentation(replace_lines, indent)
            replacement_text = "\n".join(new_block)

            if (new_string and window[-1].endswith("\n") and
                    not replacement_text.endswith("\n")):
                replacement_text += "\n"

            source_lines[i:i + len(search_lines)] = [replacement_text]
            if not allow_multiple:
                break
        else:
            i += 1

    if flexible_occurrences > 0:
        new_content = "\n".join(source_lines)
        new_content = _restore_trailing_newline(content, new_content)
        return ReplacementResult(
            new_content=new_content, occurrences=flexible_occurrences,
            final_old_string=normalized_search, final_new_string=normalized_replace,
            strategy=EditStrategy.FLEXIBLE
        )
    return None


# --- Strategy 3: 正则匹配 ---
def _calculate_regex_replacement(
    content: str, old_string: str, new_string: str, allow_multiple: bool = False
) -> Optional[ReplacementResult]:
    normalized_search = old_string.replace("\r\n", "\n")
    normalized_replace = new_string.replace("\r\n", "\n")

    delimiters = ['(', ')', ':', '[', ']', '{', '}', '>', '<', '=']
    processed = normalized_search
    for d in delimiters:
        processed = processed.replace(d, f" {d} ")

    tokens = [t for t in processed.split() if t]
    if not tokens:
        return None

    escaped_tokens = [_escape_regex(t) for t in tokens]
    pattern = r"\s*".join(escaped_tokens)
    final_pattern = rf"^([ \t]*){pattern}"

    global_regex = re.compile(final_pattern, re.MULTILINE)
    matches = global_regex.findall(content)
    if not matches:
        return None

    occurrences = len(matches)
    new_lines = normalized_replace.split("\n")

    if allow_multiple:
        def replacer(m):
            indent = m.group(1) or ""
            return "\n".join(_apply_indentation(new_lines, indent))
        new_content = global_regex.sub(replacer, content)
    else:
        def replacer(m):
            indent = m.group(1) or ""
            return "\n".join(_apply_indentation(new_lines, indent))
        new_content = global_regex.sub(replacer, content, count=1)

    new_content = _restore_trailing_newline(content, new_content)
    return ReplacementResult(
        new_content=new_content, occurrences=occurrences,
        final_old_string=normalized_search, final_new_string=normalized_replace,
        strategy=EditStrategy.REGEX
    )


# --- Strategy 4: 模糊匹配 (Levenshtein) ---
def _levenshtein_distance(s1: str, s2: str) -> int:
    """计算 Levenshtein 编辑距离"""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr_row.append(min(
                prev_row[j + 1] + 1,
                curr_row[j] + 1,
                prev_row[j] + cost
            ))
        prev_row = curr_row
    return prev_row[-1]


def _strip_whitespace(s: str) -> str:
    return re.sub(r"\s", "", s)


def _calculate_fuzzy_replacement(
    content: str, old_string: str, new_string: str,
    allow_multiple: bool = False,
    threshold: float = 0.1,
    whitespace_penalty: float = 0.1
) -> Optional[ReplacementResult]:
    """模糊匹配 — Levenshtein 距离 + 空白惩罚"""
    if len(old_string) < 10:
        return None

    normalized_code = content.replace("\r\n", "\n")
    normalized_search = old_string.replace("\r\n", "\n")
    normalized_replace = new_string.replace("\r\n", "\n")

    source_lines = normalized_code.split("\n")
    search_lines = [l.rstrip() for l in normalized_search.split("\n")]

    if not search_lines:
        return None

    N = len(search_lines)
    candidates = []
    search_block = "\n".join(search_lines)

    # 复杂度限制
    if len(source_lines) * (len(old_string) ** 2) > 400_000_000:
        return None

    for i in range(len(source_lines) - N + 1):
        window_lines = source_lines[i:i + N]
        window_text = "\n".join(l.rstrip() for l in window_lines)

        # 长度启发式
        length_diff = abs(len(window_text) - len(search_block))
        if length_diff / len(search_block) > threshold / whitespace_penalty:
            continue

        d_raw = _levenshtein_distance(window_text, search_block)
        d_norm = _levenshtein_distance(
            _strip_whitespace(window_text),
            _strip_whitespace(search_block)
        )
        weighted_dist = d_norm + (d_raw - d_norm) * whitespace_penalty
        score = weighted_dist / len(search_block)

        if score <= threshold:
            candidates.append((i, score))

    if not candidates:
        return None

    # 按分数排序，选非重叠最佳匹配
    candidates.sort(key=lambda x: (x[1], x[0]))
    selected = []
    for idx, score in candidates:
        if not any(abs(idx - m[0]) < N for m in selected):
            selected.append((idx, score))

    if not selected:
        return None

    # 从下往上替换 (保持索引有效)
    selected.sort(key=lambda x: x[0], reverse=True)
    new_lines = normalized_replace.split("\n")

    match_ranges = []
    for idx, score in selected:
        first_line = source_lines[idx]
        indent_match = re.match(r"^([ \t]*)", first_line)
        indent = indent_match.group(1) if indent_match else ""

        indented = _apply_indentation(new_lines, indent)
        replacement_text = "\n".join(indented)
        if source_lines[idx + N - 1].endswith("\n"):
            replacement_text += "\n"

        source_lines[idx:idx + N] = [replacement_text]
        match_ranges.append((idx + 1, idx + N))

    match_ranges.sort(key=lambda x: x[0])
    new_content = "\n".join(source_lines)
    new_content = _restore_trailing_newline(content, new_content)

    return ReplacementResult(
        new_content=new_content, occurrences=len(selected),
        final_old_string=normalized_search, final_new_string=normalized_replace,
        strategy=EditStrategy.FUZZY, match_ranges=match_ranges
    )


def calculate_replacement(
    content: str, old_string: str, new_string: str,
    allow_multiple: bool = False, enable_fuzzy: bool = True
) -> ReplacementResult:
    """
    4层回退策略计算编辑替换
    
    移植自 gemini-cli edit.ts 的 calculateReplacement()
    精确 → 弹性(去空白) → 正则(分词) → 模糊(Levenshtein)
    """
    if not old_string:
        return ReplacementResult(
            new_content=content, occurrences=0,
            final_old_string=old_string, final_new_string=new_string,
            strategy=EditStrategy.EXACT
        )

    # Strategy 1: 精确匹配
    result = _calculate_exact_replacement(content, old_string, new_string, allow_multiple)
    if result:
        logger.debug(f"Edit strategy: exact ({result.occurrences} occurrences)")
        return result

    # Strategy 2: 弹性匹配 (去空白后比较)
    result = _calculate_flexible_replacement(content, old_string, new_string, allow_multiple)
    if result:
        logger.debug(f"Edit strategy: flexible ({result.occurrences} occurrences)")
        return result

    # Strategy 3: 正则匹配 (分词后用 \s* 连接)
    result = _calculate_regex_replacement(content, old_string, new_string, allow_multiple)
    if result:
        logger.debug(f"Edit strategy: regex ({result.occurrences} occurrences)")
        return result

    # Strategy 4: 模糊匹配 (Levenshtein)
    if enable_fuzzy:
        result = _calculate_fuzzy_replacement(content, old_string, new_string, allow_multiple)
        if result:
            logger.debug(f"Edit strategy: fuzzy ({result.occurrences} occurrences)")
            return result

    return ReplacementResult(
        new_content=content, occurrences=0,
        final_old_string=old_string, final_new_string=new_string,
        strategy=EditStrategy.FAILED
    )


def smart_edit_file(
    file_path: str, old_string: str, new_string: str,
    allow_multiple: bool = False
) -> Dict:
    """
    智能文件编辑 — 4层回退策略
    
    Returns: {"success": bool, "strategy": str, "message": str}
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        if not old_string:
            # 新建文件
            os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_string)
            return {"success": True, "strategy": "new_file", "message": f"Created {file_path}"}
        return {"success": False, "strategy": "failed", "message": f"File not found: {file_path}"}
    except Exception as e:
        return {"success": False, "strategy": "failed", "message": f"Read error: {e}"}

    result = calculate_replacement(content, old_string, new_string, allow_multiple)

    if result.strategy == EditStrategy.FAILED:
        return {
            "success": False, "strategy": "failed",
            "message": f"Could not find old_string in {file_path}. "
                       f"Use read_file to verify content, whitespace, and indentation."
        }

    try:
        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(result.new_content)
        msg = f"Successfully edited {file_path} ({result.occurrences} replacements, strategy: {result.strategy.value})"
        if result.match_ranges:
            ranges = ", ".join(f"{s}-{e}" for s, e in result.match_ranges)
            msg += f" [lines: {ranges}]"
        return {"success": True, "strategy": result.strategy.value, "message": msg}
    except Exception as e:
        return {"success": False, "strategy": "failed", "message": f"Write error: {e}"}


# ═══════════════════════════════════════════════════════════════════════
# 2. Shell 注入检测 (移植自 shell.ts)
# ═══════════════════════════════════════════════════════════════════════

# 命令替换模式
_CMD_SUBSTITUTION_PATTERNS = [
    r"\$\(",        # $()
    r"`",           # backticks
    r"<\(",         # <()
    r">\(",         # >()
    r"\$\{",        # ${} (间接注入)
]


def detect_command_injection(command: str) -> Optional[str]:
    """
    检测命令注入 — 移植自 shell.ts detectCommandSubstitution()
    
    Returns: None (安全) 或 检测到的注入模式描述
    """
    for pattern in _CMD_SUBSTITUTION_PATTERNS:
        if re.search(pattern, command):
            return f"Command substitution detected: pattern '{pattern}' found"
    return None


# ═══════════════════════════════════════════════════════════════════════
# 3. 输出截断 + 文件保存 (移植自 tool-executor.ts)
# ═══════════════════════════════════════════════════════════════════════

MAX_OUTPUT_CHARS = 50_000  # 50KB 截断阈值


def truncate_output(output: str, max_chars: int = MAX_OUTPUT_CHARS) -> Tuple[str, Optional[str]]:
    """
    截断大输出，保存完整版到临时文件
    
    Returns: (截断后的输出, 完整输出文件路径 or None)
    """
    if len(output) <= max_chars:
        return output, None

    # 保存完整输出
    import tempfile
    fd, filepath = tempfile.mkstemp(suffix=".txt", prefix="tool_output_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(output)
    except Exception:
        pass

    truncated = (
        output[:max_chars] +
        f"\n\n... [truncated, full output ({len(output)} chars) saved to {filepath}]"
    )
    return truncated, filepath


# ═══════════════════════════════════════════════════════════════════════
# 4. 语言检测 (移植自 tool_registry.py _detect_code_language)
# ═══════════════════════════════════════════════════════════════════════

def detect_code_language(code: str) -> Tuple[str, str, str]:
    """
    检测代码语言
    
    Returns: (language, extension, default_filename)
    """
    code_stripped = code.strip()

    # HTML
    if code_stripped.startswith("<!DOCTYPE") or code_stripped.startswith("<html"):
        return ("html", ".html", "game")
    if "<html" in code_stripped or "</html>" in code_stripped:
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


# ═══════════════════════════════════════════════════════════════════════
# 5. SHA256 文件哈希 (移植自 edit.ts hashContent)
# ═══════════════════════════════════════════════════════════════════════

def hash_content(content: str) -> str:
    """计算内容的 SHA256 哈希"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def detect_file_changed(file_path: str, original_hash: str) -> bool:
    """检测文件是否被外部修改"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            current = f.read()
        return hash_content(current) != original_hash
    except Exception:
        return True


# ═══════════════════════════════════════════════════════════════════════
# 6. 省略符检测 (移植自 omissionPlaceholderDetector.ts)
# ═══════════════════════════════════════════════════════════════════════

OMISSION_PATTERNS = [
    r"rest of .*",
    r"\.\.\..*",
    r"remaining .*",
    r"other .* methods",
    r"other .* functions",
    r"other .* code",
    r"etc\..*",
    r"and so on",
    r"and more",
]


def detect_omission_placeholders(text: str) -> List[str]:
    """检测省略符占位符"""
    found = []
    for pattern in OMISSION_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        found.extend(matches)
    return found


# ═══════════════════════════════════════════════════════════════════════
# 7. 路径安全检查 (移植自 shell.ts validatePathAccess)
# ═══════════════════════════════════════════════════════════════════════

SENSITIVE_DIRS = {
    os.path.expanduser("~"),
    os.path.dirname(os.path.expanduser("~")),
    "/",
    "/etc",
    "/usr",
    "/var",
    "/bin",
    "/sbin",
    "/lib",
    "/root",
    "/home",
    "/Users",
}


def validate_path_access(file_path: str, workspace_root: str = None) -> Optional[str]:
    """
    验证路径安全性 — 防止路径穿越
    
    Returns: None (安全) 或 错误信息
    """
    abs_path = os.path.abspath(file_path)
    real_path = os.path.realpath(abs_path)

    # 路径穿越检测
    if workspace_root:
        workspace_root = os.path.realpath(os.path.abspath(workspace_root))
        if not real_path.startswith(workspace_root):
            return f"Path traversal detected: {file_path} is outside workspace {workspace_root}"

    # 敏感目录检测
    if real_path in SENSITIVE_DIRS:
        return f"Access to sensitive directory denied: {real_path}"

    return None
