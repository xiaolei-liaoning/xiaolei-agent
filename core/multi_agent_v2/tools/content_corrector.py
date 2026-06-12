"""
内容修正模块
移植自 gemini-cli: editCorrector.ts

修正 LLM 输出中的转义问题和格式问题
"""

import re
import logging
from typing import Optional
from functools import lru_cache

logger = logging.getLogger(__name__)


# 缓存修正结果
_correction_cache: dict[str, str] = {}
MAX_CACHE_SIZE = 50


def unescape_string_for_llm_bug(input_string: str) -> str:
    """
    修正 LLM 过度转义的问题
    
    例如：
    - "\\\\n" → "\\n" (正确的换行符)
    - '\\"Hello\\"' → '"Hello"' (正确的引号)
    
    Args:
        input_string: 可能有问题的字符串
        
    Returns:
        修正后的字符串
    """
    def replace_match(match: re.Match) -> str:
        captured_char = match.group(1)
        
        escape_map = {
            'n': '\n',
            't': '\t',
            'r': '\r',
            "'": "'",
            '"': '"',
            '`': '`',
            '\\': '\\',
            '\n': '\n',
        }
        
        return escape_map.get(captured_char, match.group(0))
    
    # 匹配多余的反斜杠
    pattern = r'\\+(n|t|r|\'|"|`|\\|\n)'
    return re.sub(pattern, replace_match, input_string)


def ensure_correct_content(
    content: str,
    aggressive_unescape: bool = True,
) -> str:
    """
    确保文件内容正确（修正 LLM 转义问题）
    
    Args:
        content: 原始内容
        aggressive_unescape: 是否积极修正转义
        
    Returns:
        修正后的内容
        
    Examples:
        >>> ensure_correct_content('print("\\\\nhello")')
        'print("\\nhello")'
    """
    # 检查缓存
    if content in _correction_cache:
        return _correction_cache[content]
    
    # 尝试修正转义
    unescaped = unescape_string_for_llm_bug(content)
    
    if unescaped == content:
        # 没有变化，缓存原始内容
        _correction_cache[content] = content
        return content
    
    if aggressive_unescape:
        _correction_cache[content] = unescaped
        logger.debug(f"内容已修正: {len(content)} → {len(unescaped)} 字符")
        return unescaped
    
    _correction_cache[content] = content
    return content


def detect_encoding_issues(content: str) -> list[str]:
    """
    检测内容中的编码问题
    
    Args:
        content: 待检测的内容
        
    Returns:
        问题描述列表
    """
    issues = []
    
    # 检测过度转义
    if '\\\\n' in content:
        issues.append("检测到过度转义的换行符: \\\\n → 应该是 \\n")
    
    if '\\\\t' in content:
        issues.append("检测到过度转义的制表符: \\\\t → 应该是 \\t")
    
    # 检测引号问题
    if '\\"' in content:
        issues.append('检测到转义的双引号: \\" -> 可能应该是 "')
    
    if "\\'" in content:
        issues.append("检测到转义的单引号: \\' -> 可能应该是 '")
    
    return issues


def fix_common_issues(content: str) -> str:
    """
    修复常见的 LLM 输出问题
    
    Args:
        content: 原始内容
        
    Returns:
        修复后的内容
    """
    # 1. 修正过度转义
    content = unescape_string_for_llm_bug(content)
    
    # 2. 修复常见的 HTML 问题
    # 修复没有闭合的标签
    if '<script>' in content and '</script>' not in content:
        # 尝试在 </html> 之前添加 </script>
        content = content.replace('</html>', '</script>\n</html>')
    
    # 3. 修复常见的 JavaScript 问题
    # 修复缺少的分号（简单检测）
    
    return content


if __name__ == "__main__":
    # 测试代码
    test_cases = [
        'print("\\\\nhello")',
        'console.log("\\\\"Hello\\\\\\")',
        '<!DOCTYPE html><html><head></head><body><script>console.log("test")</body></html>',
    ]
    
    for test in test_cases:
        result = ensure_correct_content(test)
        issues = detect_encoding_issues(test)
        print(f"输入: {test!r}")
        print(f"输出: {result!r}")
        print(f"问题: {issues}")
        print()
