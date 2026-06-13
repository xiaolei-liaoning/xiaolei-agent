"""代码质量校验器 - 检测常见代码问题并提供改进建议"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class CodeIssue:
    """代码问题"""
    line: int
    column: int
    severity: str  # error, warning, info
    message: str
    suggestion: str


@dataclass
class QualityReport:
    """质量报告"""
    file_path: str
    issues: List[CodeIssue]
    score: int  # 0-100
    suggestions: List[str]


class CodeQualityChecker:
    """代码质量校验器"""
    
    def check_html(self, content: str) -> QualityReport:
        """检查 HTML 文件质量"""
        issues = []
        suggestions = []
        score = 100
        
        lines = content.split('\n')
        
        # 检查括号匹配
        bracket_issues = self._check_brackets(content)
        issues.extend(bracket_issues)
        score -= len(bracket_issues) * 10
        
        # 检查 JavaScript 语法
        js_issues = self._check_javascript(content)
        issues.extend(js_issues)
        score -= len(js_issues) * 15
        
        # 检查常见逻辑错误
        logic_issues = self._check_logic(content)
        issues.extend(logic_issues)
        score -= len(logic_issues) * 5
        
        # 生成建议
        if any(i.severity == 'error' for i in issues):
            suggestions.append("存在语法错误，请修复后再写入")
        
        if len(content) < 500:
            suggestions.append("文件内容较短，可能是不完整的代码")
        
        if '<script' in content.lower() and '</script>' not in content.lower():
            suggestions.append("JavaScript 代码被截断")
        
        return QualityReport(
            file_path="",
            issues=issues,
            score=max(0, score),
            suggestions=suggestions
        )
    
    def check_javascript(self, content: str) -> QualityReport:
        """检查 JavaScript 文件质量"""
        issues = []
        suggestions = []
        score = 100
        
        # 检查括号匹配
        bracket_issues = self._check_js_brackets(content)
        issues.extend(bracket_issues)
        score -= len(bracket_issues) * 15
        
        # 检查常见错误
        error_patterns = [
            (r'function\s+\w+\s*\([^)]*\)\s*{[^}]*$', "函数定义可能被截断"),
            (r'if\s*\([^)]*\)\s*{[^}]*$', "if 语句可能被截断"),
            (r'for\s*\([^)]*\)\s*{[^}]*$', "for 循环可能被截断"),
        ]
        
        for pattern, message in error_patterns:
            if re.search(pattern, content, re.MULTILINE):
                issues.append(CodeIssue(
                    line=0, column=0, severity='warning',
                    message=message, suggestion="请检查代码完整性"
                ))
                score -= 10
        
        return QualityReport(
            file_path="",
            issues=issues,
            score=max(0, score),
            suggestions=suggestions
        )
    
    def _check_brackets(self, content: str) -> List[CodeIssue]:
        """检查 HTML 中的括号匹配"""
        issues = []
        stack = []
        line_num = 1
        col_num = 1
        
        # 检查花括号（JavaScript 中的）
        in_script = False
        for i, char in enumerate(content):
            if char == '\n':
                line_num += 1
                col_num = 1
                continue
            col_num += 1
            
            # 追踪 <script> 标签
            if content[i:i+7].lower() == '<script':
                in_script = True
            elif content[i:i+8].lower() == '</script>':
                in_script = False
            
            if in_script:
                if char == '{':
                    stack.append(('{', line_num, col_num))
                elif char == '}':
                    if stack and stack[-1][0] == '{':
                        stack.pop()
                    else:
                        issues.append(CodeIssue(
                            line=line_num, column=col_num,
                            severity='error',
                            message="多余的右花括号 '}'",
                            suggestion="检查 JavaScript 代码的花括号匹配"
                        ))
        
        # 检查未闭合的花括号
        for item in stack:
            issues.append(CodeIssue(
                line=item[1], column=item[2],
                severity='error',
                message="未闭合的左花括号 '{'",
                suggestion="检查 JavaScript 代码是否被截断"
            ))
        
        return issues
    
    def _check_javascript(self, content: str) -> List[CodeIssue]:
        """检查 JavaScript 语法"""
        issues = []
        
        # 检查常见的 JavaScript 错误
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # 检查未闭合的字符串
            if stripped.count("'") % 2 != 0:
                issues.append(CodeIssue(
                    line=i, column=0,
                    severity='warning',
                    message="可能有未闭合的字符串",
                    suggestion="检查引号匹配"
                ))
            
            if stripped.count('"') % 2 != 0:
                issues.append(CodeIssue(
                    line=i, column=0,
                    severity='warning',
                    message="可能有未闭合的双引号",
                    suggestion="检查引号匹配"
                ))
        
        return issues
    
    def _check_logic(self, content: str) -> List[CodeIssue]:
        """检查常见逻辑错误"""
        issues = []
        
        # 检查八数码游戏特有的逻辑问题
        if 'puzzle' in content.lower() or '游戏' in content or 'board' in content.lower() or 'cell' in content.lower():
            # 检查移动逻辑
            if 'Math.abs' in content:
                # 检查是否只检查了左右相邻（=== 1）
                if re.search(r'Math\.abs\([^)]*-\s*emptyIndex\)\s*===?\s*1', content):
                    issues.append(CodeIssue(
                        line=0, column=0,
                        severity='warning',
                        message="移动逻辑可能只检查了左右相邻（===1）",
                        suggestion="八数码游戏需要检查上下左右四个方向的相邻（行差+列差=1）"
                    ))
                # 检查是否正确检查了四个方向
                elif re.search(r'Math\.abs\([^)]*-\s*emptyIndex\)\s*[=!<>]=?\s*[0-3]', content):
                    # 看起来是正确的检查方式
                    pass
                else:
                    # 其他 Math.abs 使用方式，可能有问题
                    issues.append(CodeIssue(
                        line=0, column=0,
                        severity='info',
                        message="检测到使用 Math.abs 进行移动判断",
                        suggestion="请确保检查了上下左右四个方向的相邻"
                    ))
        
        return issues
    
    def _check_js_brackets(self, content: str) -> List[CodeIssue]:
        """检查 JavaScript 括号匹配"""
        issues = []
        stack = []
        line_num = 1
        col_num = 1
        
        for i, char in enumerate(content):
            if char == '\n':
                line_num += 1
                col_num = 1
                continue
            col_num += 1
            
            if char in '({[':
                stack.append((char, line_num, col_num))
            elif char in ')}]':
                if stack:
                    expected = {'(': ')', '{': '}', '[': ']'}[stack[-1][0]]
                    if char == expected:
                        stack.pop()
                    else:
                        issues.append(CodeIssue(
                            line=line_num, column=col_num,
                            severity='error',
                            message=f"括号不匹配: 期望 '{expected}' 但得到 '{char}'",
                            suggestion="检查代码的括号匹配"
                        ))
                else:
                    issues.append(CodeIssue(
                        line=line_num, column=col_num,
                        severity='error',
                        message=f"多余的右括号 '{char}'",
                        suggestion="检查代码结构"
                    ))
        
        for item in stack:
            issues.append(CodeIssue(
                line=item[1], column=item[2],
                severity='error',
                message=f"未闭合的左括号 '{item[0]}'",
                suggestion="检查代码是否被截断"
            ))
        
        return issues


def validate_code_quality(file_path: str, content: str) -> Tuple[bool, QualityReport]:
    """验证代码质量
    
    Returns:
        (is_valid, report): 是否有效和质量报告
    """
    checker = CodeQualityChecker()
    
    if file_path.endswith(('.html', '.htm')):
        report = checker.check_html(content)
    elif file_path.endswith('.js'):
        report = checker.check_javascript(content)
    else:
        # 其他文件类型，跳过详细检查
        report = QualityReport(
            file_path=file_path,
            issues=[],
            score=100,
            suggestions=[]
        )
    
    report.file_path = file_path
    
    # 如果有严重错误，返回无效
    has_errors = any(i.severity == 'error' for i in report.issues)
    
    return not has_errors, report
