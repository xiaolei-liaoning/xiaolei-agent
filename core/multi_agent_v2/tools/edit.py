"""
智能文件编辑器 — 9 种模糊匹配策略

对标 opencode 的 EditTool 多替换策略
"""

import difflib
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class EditStrategy(Enum):
    """编辑策略"""
    EXACT_MATCH = "exact_match"           # 1. 精确匹配
    FUZZY_MATCH = "fuzzy_match"           # 2. 模糊匹配
    LINE_NUMBER = "line_number"           # 3. 行号定位
    CONTEXT_LINES = "context_lines"       # 4. 上下文行匹配
    INDENTATION_MATCH = "indentation_match"  # 5. 缩进匹配
    STRUCTURE_MATCH = "structure_match"   # 6. AST 结构匹配
    REGEX_REPLACE = "regex_replace"       # 7. 正则替换
    MULTI_REPLACE = "multi_replace"       # 8. 多处批量替换
    SMART_DIFF = "smart_diff"            # 9. 智能差异合并


@dataclass
class EditResult:
    """编辑结果"""
    success: bool
    strategy: EditStrategy
    changes: List[str] = field(default_factory=list)
    diff: str = ""
    error: str = ""
    matches_found: int = 0


class SmartEditor:
    """智能文件编辑器"""

    def __init__(self, file_path: str = None):
        self.file_path = file_path
        self.original_content = None

    def load(self, file_path: str = None) -> None:
        """加载文件内容"""
        path = file_path or self.file_path
        if not path:
            raise ValueError("未指定文件路径")

        try:
            with open(path, "r", encoding="utf-8") as f:
                self.original_content = f.read()
            self.file_path = path
        except Exception as e:
            logger.error(f"加载文件失败: {e}")
            raise

    async def edit(
        self,
        old_text: str,
        new_text: str,
        strategy: str = "auto",
        line_number: int = None,
        context_lines: int = 3,
        fuzzy_threshold: float = 0.6,
    ) -> EditResult:
        """
        智能编辑

        Args:
            old_text: 要替换的文本
            new_text: 替换后的文本
            strategy: 编辑策略（auto 使用自动选择）
            line_number: 行号定位（仅 line_number 策略）
            context_lines: 上下文行数（仅 context_lines 策略）
            fuzzy_threshold: 模糊匹配阈值（仅 fuzzy_match 策略）

        Returns:
            EditResult: 编辑结果
        """
        if self.original_content is None:
            raise ValueError("请先调用 load() 加载文件内容")

        if strategy == "auto":
            strategy_enum = self._find_best_strategy(old_text)
        else:
            try:
                strategy_enum = EditStrategy(strategy)
            except ValueError:
                return EditResult(
                    success=False,
                    strategy=EditStrategy.EXACT_MATCH,
                    error=f"未知策略: {strategy}",
                )

        return await self._execute_edit(
            old_text, new_text, strategy_enum,
            line_number, context_lines, fuzzy_threshold
        )

    def _find_best_strategy(self, old_text: str) -> EditStrategy:
        """自动选择最佳策略"""
        content = self.original_content

        # 1. 尝试精确匹配
        if old_text in content:
            return EditStrategy.EXACT_MATCH

        # 2. 尝试模糊匹配
        lines = content.split("\n")
        for i, line in enumerate(lines):
            ratio = difflib.SequenceMatcher(None, line.strip(), old_text.strip()).ratio()
            if ratio > 0.8:
                return EditStrategy.FUZZY_MATCH

        # 3. 尝试正则匹配
        try:
            re.compile(old_text)
            if re.search(old_text, content):
                return EditStrategy.REGEX_REPLACE
        except re.error:
            pass

        # 4. 尝试上下文匹配
        old_lines = old_text.split("\n")
        if len(old_lines) > 1:
            return EditStrategy.CONTEXT_LINES

        # 5. 默认使用智能差异
        return EditStrategy.SMART_DIFF

    async def _execute_edit(
        self,
        old_text: str,
        new_text: str,
        strategy: EditStrategy,
        line_number: int = None,
        context_lines: int = 3,
        fuzzy_threshold: float = 0.6,
    ) -> EditResult:
        """执行编辑"""
        content = self.original_content

        if strategy == EditStrategy.EXACT_MATCH:
            return self._exact_match(content, old_text, new_text)
        elif strategy == EditStrategy.FUZZY_MATCH:
            return self._fuzzy_match(content, old_text, new_text, fuzzy_threshold)
        elif strategy == EditStrategy.LINE_NUMBER:
            return self._line_number_match(content, old_text, new_text, line_number)
        elif strategy == EditStrategy.CONTEXT_LINES:
            return self._context_lines_match(content, old_text, new_text, context_lines)
        elif strategy == EditStrategy.INDENTATION_MATCH:
            return self._indentation_match(content, old_text, new_text)
        elif strategy == EditStrategy.STRUCTURE_MATCH:
            return self._structure_match(content, old_text, new_text)
        elif strategy == EditStrategy.REGEX_REPLACE:
            return self._regex_replace(content, old_text, new_text)
        elif strategy == EditStrategy.MULTI_REPLACE:
            return self._multi_replace(content, old_text, new_text)
        elif strategy == EditStrategy.SMART_DIFF:
            return self._smart_diff(content, old_text, new_text)
        else:
            return EditResult(
                success=False,
                strategy=strategy,
                error=f"未实现策略: {strategy}",
            )

    def _exact_match(self, content: str, old_text: str, new_text: str) -> EditResult:
        """1. 精确匹配"""
        if old_text not in content:
            return EditResult(
                success=False,
                strategy=EditStrategy.EXACT_MATCH,
                error="未找到精确匹配的文本",
            )

        new_content = content.replace(old_text, new_text, 1)
        diff = self._generate_diff(content, new_content)
        self.original_content = new_content

        return EditResult(
            success=True,
            strategy=EditStrategy.EXACT_MATCH,
            diff=diff,
            matches_found=1,
        )

    def _fuzzy_match(
        self, content: str, old_text: str, new_text: str, threshold: float
    ) -> EditResult:
        """2. 模糊匹配"""
        lines = content.split("\n")
        best_match = None
        best_ratio = 0
        best_index = -1

        for i, line in enumerate(lines):
            ratio = difflib.SequenceMatcher(None, line.strip(), old_text.strip()).ratio()
            if ratio > best_ratio and ratio >= threshold:
                best_ratio = ratio
                best_match = line
                best_index = i

        if best_match is None:
            return EditResult(
                success=False,
                strategy=EditStrategy.FUZZY_MATCH,
                error=f"未找到相似度 >= {threshold} 的匹配",
            )

        lines[best_index] = new_text
        new_content = "\n".join(lines)
        diff = self._generate_diff(content, new_content)
        self.original_content = new_content

        return EditResult(
            success=True,
            strategy=EditStrategy.FUZZY_MATCH,
            diff=diff,
            matches_found=1,
        )

    def _line_number_match(
        self, content: str, old_text: str, new_text: str, line_number: int
    ) -> EditResult:
        """3. 行号定位"""
        if line_number is None:
            return EditResult(
                success=False,
                strategy=EditStrategy.LINE_NUMBER,
                error="未指定行号",
            )

        lines = content.split("\n")
        if line_number < 1 or line_number > len(lines):
            return EditResult(
                success=False,
                strategy=EditStrategy.LINE_NUMBER,
                error=f"行号 {line_number} 超出范围 (1-{len(lines)})",
            )

        # 找到该行附近的匹配
        target_line = lines[line_number - 1]
        ratio = difflib.SequenceMatcher(None, target_line.strip(), old_text.strip()).ratio()

        if ratio < 0.5:
            return EditResult(
                success=False,
                strategy=EditStrategy.LINE_NUMBER,
                error=f"第 {line_number} 行与目标文本不匹配",
            )

        lines[line_number - 1] = new_text
        new_content = "\n".join(lines)
        diff = self._generate_diff(content, new_content)
        self.original_content = new_content

        return EditResult(
            success=True,
            strategy=EditStrategy.LINE_NUMBER,
            diff=diff,
            matches_found=1,
        )

    def _context_lines_match(
        self, content: str, old_text: str, new_text: str, context_lines: int
    ) -> EditResult:
        """4. 上下文行匹配"""
        old_lines = old_text.split("\n")
        content_lines = content.split("\n")

        # 在内容中搜索连续的相似行
        for i in range(len(content_lines) - len(old_lines) + 1):
            match_count = 0
            for j, old_line in enumerate(old_lines):
                ratio = difflib.SequenceMatcher(
                    None, content_lines[i + j].strip(), old_line.strip()
                ).ratio()
                if ratio > 0.7:
                    match_count += 1

            if match_count >= len(old_lines) * 0.8:
                # 找到匹配，替换
                new_lines = new_text.split("\n")
                content_lines[i:i + len(old_lines)] = new_lines
                new_content = "\n".join(content_lines)
                diff = self._generate_diff(content, new_content)
                self.original_content = new_content

                return EditResult(
                    success=True,
                    strategy=EditStrategy.CONTEXT_LINES,
                    diff=diff,
                    matches_found=1,
                )

        return EditResult(
            success=False,
            strategy=EditStrategy.CONTEXT_LINES,
            error="未找到上下文匹配",
        )

    def _indentation_match(self, content: str, old_text: str, new_text: str) -> EditResult:
        """5. 缩进匹配"""
        lines = content.split("\n")
        old_lines = old_text.split("\n")

        for i in range(len(lines) - len(old_lines) + 1):
            # 检查缩进是否匹配
            match = True
            for j, old_line in enumerate(old_lines):
                if old_line.strip():  # 跳过空行
                    old_indent = len(old_line) - len(old_line.lstrip())
                    current_indent = len(lines[i + j]) - len(lines[i + j].lstrip())
                    if old_indent != current_indent:
                        match = False
                        break

            if match:
                # 保持原缩进
                new_lines = new_text.split("\n")
                result_lines = []
                for k, new_line in enumerate(new_lines):
                    if new_line.strip() and i + k < len(lines):
                        old_indent = len(lines[i + k]) - len(lines[i + k].lstrip())
                        result_lines.append(" " * old_indent + new_line.strip())
                    else:
                        result_lines.append(new_line)

                content_lines[i:i + len(old_lines)] = result_lines
                new_content = "\n".join(content_lines)
                diff = self._generate_diff(content, new_content)
                self.original_content = new_content

                return EditResult(
                    success=True,
                    strategy=EditStrategy.INDENTATION_MATCH,
                    diff=diff,
                    matches_found=1,
                )

        return EditResult(
            success=False,
            strategy=EditStrategy.INDENTATION_MATCH,
            error="未找到缩进匹配",
        )

    def _structure_match(self, content: str, old_text: str, new_text: str) -> EditResult:
        """6. AST 结构匹配（简单实现：基于缩进和语法）"""
        # 简化实现：使用缩进匹配
        return self._indentation_match(content, old_text, new_text)

    def _regex_replace(self, content: str, old_text: str, new_text: str) -> EditResult:
        """7. 正则替换"""
        try:
            pattern = re.compile(old_text)
        except re.error as e:
            return EditResult(
                success=False,
                strategy=EditStrategy.REGEX_REPLACE,
                error=f"正则表达式无效: {e}",
            )

        matches = pattern.findall(content)
        if not matches:
            return EditResult(
                success=False,
                strategy=EditStrategy.REGEX_REPLACE,
                error="未找到正则匹配",
            )

        new_content = pattern.sub(new_text, content, count=1)
        diff = self._generate_diff(content, new_content)
        self.original_content = new_content

        return EditResult(
            success=True,
            strategy=EditStrategy.REGEX_REPLACE,
            diff=diff,
            matches_found=len(matches),
        )

    def _multi_replace(self, content: str, old_text: str, new_text: str) -> EditResult:
        """8. 多处批量替换"""
        if old_text not in content:
            return EditResult(
                success=False,
                strategy=EditStrategy.MULTI_REPLACE,
                error="未找到匹配的文本",
            )

        count = content.count(old_text)
        new_content = content.replace(old_text, new_text)
        diff = self._generate_diff(content, new_content)
        self.original_content = new_content

        return EditResult(
            success=True,
            strategy=EditStrategy.MULTI_REPLACE,
            diff=diff,
            matches_found=count,
        )

    def _smart_diff(self, content: str, old_text: str, new_text: str) -> EditResult:
        """9. 智能差异合并"""
        # 使用 difflib 查找最佳匹配
        old_lines = old_text.split("\n")
        content_lines = content.split("\n")

        # 查找最相似的连续行
        best_start = -1
        best_score = 0

        for i in range(len(content_lines) - len(old_lines) + 1):
            score = 0
            for j, old_line in enumerate(old_lines):
                ratio = difflib.SequenceMatcher(
                    None, content_lines[i + j].strip(), old_line.strip()
                ).ratio()
                score += ratio

            avg_score = score / len(old_lines) if old_lines else 0
            if avg_score > best_score:
                best_score = avg_score
                best_start = i

        if best_score < 0.5:
            return EditResult(
                success=False,
                strategy=EditStrategy.SMART_DIFF,
                error="未找到足够相似的匹配",
            )

        # 替换
        new_lines = new_text.split("\n")
        content_lines[best_start:best_start + len(old_lines)] = new_lines
        new_content = "\n".join(content_lines)
        diff = self._generate_diff(content, new_content)
        self.original_content = new_content

        return EditResult(
            success=True,
            strategy=EditStrategy.SMART_DIFF,
            diff=diff,
            matches_found=1,
        )

    def _generate_diff(self, old: str, new: str) -> str:
        """生成差异"""
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        diff = list(difflib.unified_diff(old_lines, new_lines, lineterm=""))
        return "".join(diff)

    def save(self, file_path: str = None) -> None:
        """保存修改"""
        path = file_path or self.file_path
        if not path:
            raise ValueError("未指定文件路径")

        if self.original_content is None:
            raise ValueError("无内容可保存")

        with open(path, "w", encoding="utf-8") as f:
            f.write(self.original_content)
        logger.info(f"文件已保存: {path}")

    def get_content(self) -> str:
        """获取当前内容"""
        return self.original_content or ""


def get_smart_editor(file_path: str = None) -> SmartEditor:
    """获取智能编辑器实例"""
    editor = SmartEditor(file_path)
    if file_path:
        try:
            editor.load(file_path)
        except Exception:
            pass
    return editor
