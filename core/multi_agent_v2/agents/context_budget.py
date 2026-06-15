"""
ContextBudgetManager — 上下文预算管理

在 ReAct 循环中主动检测上下文大小，当超出预算时压缩旧的
工具调用结果，保持 context 在可控范围内。

核心策略：
  - 主动检查：每次 LLM 调用前检查
  - 分层保护：最近 N 轮永远不压缩
  - 比例保留：60% 头部重要 + 25% 尾部最近 + 15% 弹性
  - 零 LLM 开销：压缩摘要用模板生成，不调 LLM
"""

import logging
from typing import Any, Dict, List, Optional

from .middleware import RunContext

logger = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    """粗略 token 估算（中英文混合）"""
    if not text:
        return 0
    return int(len(text) / 3.5)


class BudgetStats:
    """压缩统计"""
    def __init__(self):
        self.total_compactions = 0
        self.total_compacted_entries = 0
        self.total_saved_chars = 0

    def record(self, entries_count: int, saved_chars: int):
        self.total_compactions += 1
        self.total_compacted_entries += entries_count
        self.total_saved_chars += saved_chars

    def summary(self) -> str:
        if self.total_compactions == 0:
            return "未发生压缩"
        return (
            f"压缩{self.total_compactions}次, "
            f"共压缩{self.total_compacted_entries}条, "
            f"节省约{self.total_saved_chars}字符"
        )


# 全局单例
_budget_stats = BudgetStats()


def get_budget_stats() -> BudgetStats:
    return _budget_stats


class ContextBudgetManager:
    """上下文预算管理器

    配置参数:
      max_context_chars:   最大上下文总字符数（默认 80000 ≈ 20K tokens）
      safety_margin:       为输出预留的安全空间（默认 20000 字符）
      min_prune_chars:     单次最少释放量，防止频繁微调（默认 15000 字符）
      protected_recent_turns: 最近 N 轮工具结果不压缩（默认 3）
    """

    def __init__(
        self,
        max_context_chars: int = 80000,
        safety_margin: int = 20000,
        min_prune_chars: int = 15000,
        protected_recent_turns: int = 3,
    ):
        self.max_context_chars = max_context_chars
        self.safety_margin = safety_margin
        self.min_prune_chars = min_prune_chars
        self.protected_recent_turns = protected_recent_turns

    def get_total_chars(self, ctx: RunContext) -> int:
        """估算当前上下文总字符数（tool_results + knowledge_context + plan 等）"""
        total = 0
        for r in ctx.tool_results:
            total += len(str(r.get("result", "")))
            total += len(r.get("tool_call", {}).get("name", ""))
        total += len(ctx.knowledge_context)
        if ctx.plan:
            for step in ctx.plan:
                total += len(step.description)
        total += len(ctx.final_answer)
        if ctx.last_error:
            total += len(ctx.last_error)
        return total

    def is_overflow(self, ctx: RunContext) -> bool:
        """判断是否超出预算"""
        threshold = self.max_context_chars - self.safety_margin
        current = self.get_total_chars(ctx)
        return current > threshold

    def _calc_overflow_excess(self, ctx: RunContext) -> int:
        """计算超出多少字符"""
        threshold = self.max_context_chars - self.safety_margin
        current = self.get_total_chars(ctx)
        return max(0, current - threshold)

    def generate_compaction_summary(self, entries: List[Dict]) -> str:
        """对一批要压缩的工具结果生成摘要"""
        if not entries:
            return ""

        tool_names: List[str] = []
        success_count = 0
        fail_count = 0
        achievements: List[str] = []

        for e in entries:
            tc = e.get("tool_call", {})
            name = tc.get("name", "")
            ok = e.get("success", False)
            if name:
                tool_names.append(name)
            if ok:
                success_count += 1
            else:
                fail_count += 1

            result = e.get("result", {})
            if ok and isinstance(result, dict):
                for key in ("path", "filepath", "url", "query", "command"):
                    val = result.get(key, "")
                    if val and isinstance(val, str) and len(val) > 3:
                        achievements.append(f"{name}: {val[:80]}")
                        break

        tools_unique = list(dict.fromkeys(tool_names))
        tools_summary = ", ".join(tools_unique[:6])
        if len(tools_unique) > 6:
            tools_summary += f" 等 {len(tools_unique)} 种工具"

        ach_summary = "; ".join(achievements[:4])
        if achievements:
            ach_part = f"，完成了 {ach_summary}"
        else:
            ach_part = ""

        return (
            f"[上下文压缩] 之前的 {len(entries)} 轮对话中，"
            f"执行了 {tools_summary}，"
            f"成功 {success_count} 次 / 失败 {fail_count} 次{ach_part}。"
        )

    def apply_compaction(self, ctx: RunContext) -> int:
        """对 ctx.tool_results 执行压缩

        策略：
          1. 保护最近 N 轮（tail）
          2. 从最旧的 entry 开始，标记一批进行压缩
          3. 60% 头部 + 25% 尾部 + 15% 弹性

        Returns:
            被压缩的条目数（0 表示未压缩）
        """
        total = len(ctx.tool_results)
        if total <= self.protected_recent_turns + 1:
            return 0

        protected = self.protected_recent_turns
        compactable = total - protected
        if compactable <= 0:
            return 0

        excess = self._calc_overflow_excess(ctx)
        prune_target = max(excess + self.safety_margin, self.min_prune_chars)

        entries_to_compact: List[Dict] = []
        chars_freed = 0
        compact_count = 0

        for i in range(compactable):
            entry = ctx.tool_results[i]
            entry_chars = len(str(entry.get("result", "")))
            entries_to_compact.append(entry)
            chars_freed += entry_chars
            compact_count += 1
            if chars_freed >= prune_target:
                break

        if not entries_to_compact:
            return 0

        summary = self.generate_compaction_summary(entries_to_compact)
        summary_note: Dict[str, Any] = {
            "compacted": True,
            "summary": summary,
            "count": len(entries_to_compact),
        }

        # 替换压缩的条目为一个 compaction note
        ctx.tool_results = [summary_note] + ctx.tool_results[compact_count:]

        # 将摘要追加到 knowledge_context，让 system prompt 携带
        if ctx.knowledge_context:
            ctx.knowledge_context = ctx.knowledge_context[-2000:] + "\n" + summary
        else:
            ctx.knowledge_context = summary

        _budget_stats.record(compact_count, chars_freed)
        logger.info(
            f"上下文压缩: {compact_count} 条被压缩, "
            f"释放 {chars_freed} 字符, "
            f"剩余 {len(ctx.tool_results)} 条"
        )
        return compact_count

    def check_and_compact(self, ctx: RunContext) -> bool:
        """检查并执行压缩（主入口）

        Returns:
            True 表示执行了压缩
        """
        if not ctx.tool_results:
            return False
        if not self.is_overflow(ctx):
            return False
        count = self.apply_compaction(ctx)
        return count > 0
