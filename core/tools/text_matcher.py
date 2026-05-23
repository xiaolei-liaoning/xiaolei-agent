"""语义文本匹配引擎 — 支持精确/模糊/LLM辅助匹配

用于 edit_file 工具，当精确匹配失败时提供多策略回退：
1. exact → 当前 str.replace 行为
2. whitespace_insensitive → 标准化空白后重试
3. fuzzy → difflib.SequenceMatcher ratio >= 0.8
4. llm_assisted → 模糊匹配歧义时调 LLM 裁决
"""

import difflib
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)


class MatchStrategy(Enum):
    """匹配策略"""
    EXACT = "exact"
    WHITESPACE_INSENSITIVE = "whitespace_insensitive"
    FUZZY = "fuzzy"
    LLM_ASSISTED = "llm_assisted"


@dataclass
class MatchResult:
    """匹配结果"""
    start_pos: int = -1
    end_pos: int = -1
    confidence: float = 0.0
    strategy_used: MatchStrategy = MatchStrategy.EXACT
    matched_text: str = ""
    context_before: str = ""
    context_after: str = ""
    message: str = ""


class TextMatcher:
    """多策略文本匹配引擎"""

    def __init__(self, fuzzy_threshold: float = 0.8):
        self.fuzzy_threshold = fuzzy_threshold

    async def find_match(
        self,
        content: str,
        old_string: str,
        strategy: MatchStrategy = MatchStrategy.EXACT,
    ) -> List[MatchResult]:
        """在 content 中查找 old_string，返回所有匹配结果

        Args:
            content: 文件内容
            old_string: 要查找的文本
            strategy: 匹配策略（逐级回退）

        Returns:
            匹配结果列表（可能为空）
        """
        if strategy == MatchStrategy.EXACT:
            return self._find_exact(content, old_string)
        elif strategy == MatchStrategy.WHITESPACE_INSENSITIVE:
            return self._find_whitespace_insensitive(content, old_string)
        elif strategy == MatchStrategy.FUZZY:
            return self._find_fuzzy(content, old_string)
        elif strategy == MatchStrategy.LLM_ASSISTED:
            return await self._find_llm(content, old_string)
        return []

    async def find_best_match(
        self,
        content: str,
        old_string: str,
        auto_escalate: bool = True,
    ) -> MatchResult:
        """自动逐级回退查找最佳匹配

        Args:
            content: 文件内容
            old_string: 要查找的文本
            auto_escalate: 是否自动升级策略

        Returns:
            最佳匹配，或在未找到时返回带建议的 MatchResult
        """
        # 1. 精确匹配
        exact = await self.find_match(content, old_string, MatchStrategy.EXACT)
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1 and not auto_escalate:
            return MatchResult(
                message=f"找到 {len(exact)} 处精确匹配，请提供更多上下文使其唯一，或使用 replace_all=true"
            )

        if not auto_escalate:
            return MatchResult(message="未找到匹配文本")

        # 2. 空白不敏感匹配
        ws = await self.find_match(content, old_string, MatchStrategy.WHITESPACE_INSENSITIVE)
        if len(ws) == 1:
            ws[0].message = "通过忽略空白差异匹配成功"
            return ws[0]

        # 3. 模糊匹配
        fuzzy = await self.find_match(content, old_string, MatchStrategy.FUZZY)
        if len(fuzzy) == 1:
            match = fuzzy[0]
            match.message = f"通过模糊匹配成功（相似度 {match.confidence:.0%}）"
            return match
        if len(fuzzy) > 1:
            # 多个模糊匹配 → LLM 辅助
            llm = await self._resolve_ambiguous(content, old_string, fuzzy)
            if llm:
                return llm
            # LLM 失败：返回最佳候选
            best = max(fuzzy, key=lambda m: m.confidence)
            candidates = "\n".join(
                f"  [{i}] 行 {self._pos_to_line(content, m.start_pos)}: {m.matched_text[:60]}... (相似度 {m.confidence:.0%})"
                for i, m in enumerate(fuzzy[:5])
            )
            return MatchResult(
                message=f"找到 {len(fuzzy)} 处相似匹配，请提供更多上下文：\n{candidates}"
            )

        # 4. 全部失败：给出最接近的匹配建议
        return self._suggest_closest(content, old_string)

    def _find_exact(self, content: str, old_string: str) -> List[MatchResult]:
        """精确匹配"""
        if not old_string:
            return []

        results = []
        start = 0
        while True:
            pos = content.find(old_string, start)
            if pos == -1:
                break
            results.append(MatchResult(
                start_pos=pos,
                end_pos=pos + len(old_string),
                confidence=1.0,
                strategy_used=MatchStrategy.EXACT,
                matched_text=old_string,
                context_before=self._get_context(content, pos, before=True),
                context_after=self._get_context(content, pos + len(old_string)),
            ))
            start = pos + 1

        return results

    def _find_whitespace_insensitive(self, content: str, old_string: str) -> List[MatchResult]:
        """空白不敏感匹配：标准化所有空白后匹配"""
        def normalize(s: str) -> str:
            return re.sub(r'\s+', ' ', s).strip()

        norm_content = normalize(content)
        norm_old = normalize(old_string)

        if norm_old not in norm_content:
            return []

        # 找到位置后映射回原文
        pattern = re.escape(norm_old)
        for match in re.finditer(pattern, norm_content):
            # 估算在原文中的位置
            orig_start = self._estimate_orig_pos(content, norm_content, match.start())
            orig_end = self._estimate_orig_pos(content, norm_content, match.end())
            orig_text = content[orig_start:orig_end]

            if orig_text.strip():
                return [MatchResult(
                    start_pos=orig_start,
                    end_pos=orig_end,
                    confidence=0.95,
                    strategy_used=MatchStrategy.WHITESPACE_INSENSITIVE,
                    matched_text=orig_text,
                    context_before=self._get_context(content, orig_start, before=True),
                    context_after=self._get_context(content, orig_end),
                )]

        return []

    def _find_fuzzy(self, content: str, old_string: str) -> List[MatchResult]:
        """模糊匹配：按行滑动窗口匹配"""
        old_lines = old_string.splitlines(keepends=True)
        old_len = len(old_string)
        if old_len == 0:
            return []

        # 按行滑动窗口
        content_lines = content.splitlines(keepends=True)
        results = []

        # 预计算行偏移量（避免 O(n²) 重复 join）
        line_offsets = []
        offset = 0
        for line in content_lines:
            line_offsets.append(offset)
            offset += len(line)

        for i in range(len(content_lines)):
            # 构建窗口：从 i 行开始，取与 old_lines 相同行数
            window = content_lines[i:i + len(old_lines)]
            window_text = "".join(window)

            # 计算相似度
            ratio = difflib.SequenceMatcher(None, old_string, window_text).ratio()

            if ratio >= self.fuzzy_threshold:
                start_pos = line_offsets[i]
                end_pos = start_pos + len(window_text)
                results.append(MatchResult(
                    start_pos=start_pos,
                    end_pos=end_pos,
                    confidence=ratio,
                    strategy_used=MatchStrategy.FUZZY,
                    matched_text=window_text[:200],
                    context_before=self._get_context(content, start_pos, before=True),
                    context_after=self._get_context(content, end_pos),
                ))

        # 去重（同一区域可能有多个相似窗口）
        return self._deduplicate(results)

    async def _find_llm(self, content: str, old_string: str) -> List[MatchResult]:
        """LLM 辅助匹配 — 尝试调用 LLM 定位目标文本"""
        try:
            from core.engine.llm_backend import GLMBackend
            llm = GLMBackend()
            prompt = (
                f"在以下文件内容中，找到与目标文本最匹配的位置。\n\n"
                f"目标文本:\n```\n{old_string[:500]}\n```\n\n"
                f"文件内容:\n```\n{content[:3000]}\n```\n\n"
                f"请返回匹配文本在内容中的精确起始位置（字符偏移量），格式：\n"
                f"位置: <数字>\n匹配文本: <精确的匹配文本>\n置信度: <0-1>"
            )
            response = await llm.chat([{"role": "user", "content": prompt}])
            if not response:
                return []

            # 解析 LLM 返回
            pos_match = re.search(r'位置:\s*(\d+)', str(response))
            text_match = re.search(r'匹配文本:\s*(.+?)(?:\n|$)', str(response))
            conf_match = re.search(r'置信度:\s*([\d.]+)', str(response))

            if pos_match and text_match:
                pos = int(pos_match.group(1))
                matched = text_match.group(1).strip()
                conf = float(conf_match.group(1)) if conf_match else 0.7
                if 0 <= pos < len(content) and matched in content:
                    return [MatchResult(
                        start_pos=pos,
                        end_pos=pos + len(matched),
                        confidence=conf,
                        strategy_used=MatchStrategy.LLM_ASSISTED,
                        matched_text=matched,
                        context_before=self._get_context(content, pos, before=True),
                        context_after=self._get_context(content, pos + len(matched)),
                    )]
        except ImportError as e:
            logger.debug(f"LLM 后端不可用（缺失模块: {e.name}），跳过 LLM 匹配")
        except Exception as e:
            logger.debug(f"LLM 匹配失败: {e}")

        return []

    async def _resolve_ambiguous(self, content: str, old_string: str, fuzzy_matches: List[MatchResult]) -> Optional[MatchResult]:
        """LLM 裁决模糊匹配"""
        try:
            from core.engine.llm_backend import GLMBackend
            llm = GLMBackend()
            candidates_text = "\n".join(
                f"[{i}] 位置 {m.start_pos}: {m.matched_text[:100]}..."
                for i, m in enumerate(fuzzy_matches[:5])
            )
            prompt = (
                f"目标文本:\n```\n{old_string[:500]}\n```\n\n"
                f"有多个相似匹配，请选择最匹配的一个：\n{candidates_text}\n\n"
                f"请返回最佳匹配的序号。格式：序号: <数字>"
            )
            response = await llm.chat([{"role": "user", "content": prompt}])
            if response:
                idx_match = re.search(r'序号:\s*(\d+)', str(response))
                if idx_match:
                    idx = int(idx_match.group(1))
                    if 0 <= idx < len(fuzzy_matches):
                        return fuzzy_matches[idx]
        except Exception:
            pass
        return None

    def _suggest_closest(self, content: str, old_string: str) -> MatchResult:
        """给出最接近的匹配建议"""
        # 按行匹配，找相似度最高的行
        content_lines = content.splitlines()
        best_ratio = 0
        best_line = ""
        best_line_no = 0

        for i, line in enumerate(content_lines):
            ratio = difflib.SequenceMatcher(None, old_string.strip(), line.strip()).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_line = line.strip()[:100]
                best_line_no = i + 1

        if best_ratio > 0.3:
            return MatchResult(
                message=(
                    f"未找到匹配文本。最接近的匹配是第 {best_line_no} 行的 "
                    f"'{best_line}'（相似度 {best_ratio:.0%}）。"
                    f"请检查缩进和空格，或使用更独特的上下文片段。"
                )
            )

        return MatchResult(
            message="未找到匹配文本，且未发现相似内容。请检查目标文本是否正确，或使用 write_file 重新写入整个文件。"
        )

    @staticmethod
    def _get_context(content: str, pos: int, before: bool = False, lines: int = 2) -> str:
        """获取位置附近的上下文"""
        if pos < 0 or pos > len(content):
            return ""
        if before:
            start = max(0, content.rfind("\n", 0, pos))
            for _ in range(lines - 1):
                prev = content.rfind("\n", 0, start)
                if prev == -1:
                    break
                start = prev
            return content[start:pos].strip()
        else:
            end = content.find("\n", pos)
            if end == -1:
                end = len(content)
            for _ in range(lines - 1):
                nxt = content.find("\n", end + 1)
                if nxt == -1:
                    break
                end = nxt
            return content[pos:end].strip()

    @staticmethod
    def _pos_to_line(content: str, pos: int) -> int:
        """将字符偏移量转为行号"""
        return content[:pos].count("\n") + 1

    @staticmethod
    def _estimate_orig_pos(content: str, norm_content: str, norm_pos: int) -> int:
        """估算标准化内容中的位置对应原文的位置"""
        # 通过记录字符映射来估算
        orig_idx = 0
        norm_idx = 0
        while norm_idx < norm_pos and orig_idx < len(content):
            if content[orig_idx].isspace() and norm_content[norm_idx] != content[orig_idx]:
                # 原文空白被压缩
                orig_idx += 1
                continue
            norm_idx += 1
            orig_idx += 1
        return orig_idx

    @staticmethod
    def _deduplicate(results: List[MatchResult]) -> List[MatchResult]:
        """去除位置重叠的匹配结果"""
        if not results:
            return []
        sorted_results = sorted(results, key=lambda r: (-r.confidence, r.start_pos))
        deduped = []
        seen_ranges = set()
        for r in sorted_results:
            key = (r.start_pos // 10, r.end_pos // 10)  # 粗粒度去重
            if key not in seen_ranges:
                seen_ranges.add(key)
                deduped.append(r)
        return deduped


class DiffVisualizer:
    """变更可视化工具"""

    @staticmethod
    def compute_diff(old_content: str, new_content: str) -> str:
        """计算 unified diff"""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = difflib.unified_diff(
            old_lines, new_lines,
            fromfile="original", tofile="modified",
            lineterm="",
        )
        return "".join(diff)

    @staticmethod
    def format_change_summary(old_content: str, new_content: str) -> str:
        """格式化变更摘要"""
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()

        added = len(new_lines) - len(old_lines)
        changed_lines = 0
        for i in range(min(len(old_lines), len(new_lines))):
            if old_lines[i] != new_lines[i]:
                changed_lines += 1

        parts = []
        if added > 0:
            parts.append(f"+{added} 行")
        elif added < 0:
            parts.append(f"{added} 行")
        if changed_lines:
            parts.append(f"修改 {changed_lines} 行")

        summary = "，".join(parts) if parts else "无变更"
        return f"变更摘要: {summary}（共 {len(new_lines)} 行）"
