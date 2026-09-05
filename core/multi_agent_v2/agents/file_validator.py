"""文件验证模块"""

import re
from typing import Any, Dict, List, Optional, Tuple


def validate_file_content(
    path: str,
    content: str,
    raw: str = "",
    ctx: Optional[Any] = None,
    agent: Optional[Any] = None,
) -> List[str]:
    """验证文件内容，返回警告列表，含截断循环检测和语法检查"""
    from types import SimpleNamespace

    if ctx is None:
        ctx = SimpleNamespace()
    if not hasattr(ctx, "_write_retries"):
        ctx._write_retries = {}
    if not hasattr(ctx, "forced_instructions"):
        ctx.forced_instructions = None
    if not hasattr(ctx, "warnings"):
        ctx.warnings = []

    warnings = []
    if not content.strip():
        warnings.append("文件内容为空")

    # ── 截断循环检测 ──
    if raw and len(raw) > 0:
        key = f"truncation:{path}"
        retry_count = ctx._write_retries.get(key, 0) + 1
        ctx._write_retries[key] = retry_count

        is_truncated = _is_truncated(content)
        if is_truncated and retry_count < 3:
            ctx.forced_instructions = (
                f"文件内容被截断，需要续写完整内容。"
                f"已续写 {retry_count} 次，请确保输出完整的 {path} 文件。"
            )
        elif is_truncated and retry_count >= 3:
            ctx.forced_instructions = None

    # ── 语法检测 ──
    syntax_ok, syntax_msg = _check_syntax(path, content)
    if not syntax_ok:
        warnings.append(syntax_msg)

    ctx.warnings.extend(warnings)
    return warnings


def _check_syntax(path: str, content: str) -> tuple:
    """检测文件语法错误"""
    ext = path.rsplit('.', 1)[-1].lower() if '.' in path else ''
    if not content or len(content) < 20:
        return True, ""

    try:
        if ext == 'py':
            import ast
            ast.parse(content)
            return True, ""
        elif ext in ('js', 'ts', 'jsx', 'tsx'):
            return True, ""  # js syntax check needs node; skip
        elif ext in ('html', 'htm'):
            _open = len(re.findall(r'<\w+[^>]*>', content))
            _close = len(re.findall(r'</\w+>', content))
            _self = len(re.findall(r'<(?:br|hr|img|input|meta|link|doctype|!doctype)\b[^>]*>', content, re.I))
            if _open > _close + _self + 5:
                return False, f"HTML: 开标签({_open})远多于闭标签({_close}+{_self})，可能截断"
            return True, ""
    except SyntaxError as e:
        return False, f"Python 语法错误: {e}"
    except Exception:
        pass

    return True, ""


def _is_truncated(content: str) -> bool:
    """检测内容是否被截断"""
    if not content or len(content) < 5:
        return False
    # 常见截断特征：HTML/XML 标签未闭合
    open_tags = re.findall(r'<(\w+)[^>]*>', content)
    close_tags = re.findall(r'</(\w+)>', content)
    stack = []
    for tag in open_tags:
        if tag.lower() not in ('br', 'hr', 'img', 'input', 'meta', 'link', 'doctype', '!doctype'):
            stack.append(tag.lower())
    for tag in close_tags:
        if stack and stack[-1] == tag.lower():
            stack.pop()
    if stack:
        return True
    # 以不完整标签结尾
    if re.search(r'<[^>]*$', content[-200:]):
        return True
    return False


def check_file_safety(path: str, content: str) -> Tuple[bool, str]:
    """检查文件安全性"""
    forbidden_patterns = [
        r"rm\s+-rf\s+/",
        r"format\s+[a-z]:",
    ]
    for pattern in forbidden_patterns:
        if re.search(pattern, content):
            return False, f"包含危险命令: {pattern}"
    return True, ""


def suggest_file_path(task_description: str, preferred_ext: str = "") -> str:
    """根据任务描述建议文件路径"""
    return f"/tmp/output{preferred_ext}"
