"""
省略占位符检测模块
移植自 gemini-cli: omissionPlaceholderDetector.ts

检测 LLM 输出中的省略占位符，如：
- rest of methods ...
- rest of code ...
- unchanged code ...
- // rest of methods ...
"""

from typing import List


OMITTED_PREFIXES = {
    'rest of',
    'rest of method',
    'rest of methods',
    'rest of code',
    'unchanged code',
    'unchanged method',
    'unchanged methods',
}


def _is_all_dots(s: str) -> bool:
    """检查字符串是否全部由点号组成"""
    if not s:
        return False
    return all(c == '.' for c in s)


def _normalize_whitespace(text: str) -> str:
    """标准化空白字符"""
    segments = []
    current = ''
    
    for char in text:
        if char in (' ', '\t', '\n', '\r'):
            if current:
                segments.append(current)
                current = ''
            continue
        current += char
    
    if current:
        segments.append(current)
    
    return ' '.join(segments)


def _normalize_placeholder(line: str) -> str | None:
    """标准化单行占位符"""
    text = line.strip()
    if not text:
        return None
    
    # 移除注释前缀
    if text.startswith('//'):
        text = text[2:].strip()
    
    # 移除括号包裹
    if text.startswith('(') and text.endswith(')'):
        text = text[1:-1].strip()
    
    # 查找省略号
    ellipsis_pos = text.find('...')
    if ellipsis_pos < 0:
        return None
    
    prefix_raw = text[:ellipsis_pos].strip().lower()
    suffix_raw = text[ellipsis_pos + 3:].strip()
    
    # 标准化前缀并检查
    prefix = _normalize_whitespace(prefix_raw)
    if prefix not in OMITTED_PREFIXES:
        return None
    
    # 后缀必须是空的或全部是点号
    if suffix_raw and not _is_all_dots(suffix_raw):
        return None
    
    return f"{prefix} ..."


def detect_omission_placeholders(text: str) -> List[str]:
    """
    检测文本中的省略占位符
    
    检测模式：
    - (rest of methods ...)
    - rest of code ...
    - unchanged code ...
    - // rest of methods ...
    
    Args:
        text: 待检测的文本
        
    Returns:
        找到的占位符列表（已标准化）
        
    Examples:
        >>> detect_omission_placeholders("rest of methods ...")
        ['rest of methods ...']
        
        >>> detect_omission_placeholders("// rest of code ...")
        ['rest of code ...']
        
        >>> detect_omission_placeholders("完整的代码")
        []
    """
    # 统一换行符
    text = text.replace('\r\n', '\n')
    lines = text.split('\n')
    
    matches = []
    for line in lines:
        normalized = _normalize_placeholder(line)
        if normalized:
            matches.append(normalized)
    
    return matches


if __name__ == "__main__":
    # 测试代码
    test_cases = [
        "rest of methods ...",
        "(rest of code ...)",
        "// unchanged code ...",
        "完整的代码内容",
        "rest of methods ... rest of code ...",
        "请添加 rest of methods ... 的内容",
    ]
    
    for test in test_cases:
        result = detect_omission_placeholders(test)
        print(f"输入: {test!r}")
        print(f"结果: {result}")
        print()
