"""
ContextBudgetManager — 上下文预算管理

在 ReAct 循环中主动检测上下文大小，当超出预算时压缩旧的
工具调用结果，保持 context 在可控范围内。

对标 Opencode compaction 系统：
  - Token 感知溢出检测（替代固定长度截断）
  - LLM 结构化摘要压缩（替代模板一句话）
  - tail_start 指针标记保留轮次
  - 上下文重排 [summary, tail, new]
  - 压缩后重放用户任务意图
  - 压缩结果持久化到 SQLite
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .middleware import RunContext

logger = logging.getLogger(__name__)

# ── LLM 摘要压缩提示词（对标 Opencode compaction agent prompt）──
_COMPACTION_SYSTEM_PROMPT = """You are a context summarization assistant for a coding agent.

Summarize the tool execution history below. Focus on:
1. Goal: what the user asked for
2. Progress: what tools were called, what was achieved/failed
3. Key findings: important data, errors, or decisions
4. Files: what files were created or modified
5. Next steps: what remains to be done

Output a concise structured summary. Use bullet points.
Do not mention the summarization process itself."""


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
    """上下文预算管理器（增强版 — 对标 Opencode compaction 系统）

    配置参数:
      max_context_chars:          最大上下文总字符数（默认 80000 ≈ 20K tokens）
      safety_margin:              为输出预留的安全空间（默认 20000 字符）
      min_prune_chars:            单次最少释放量，防止频繁微调（默认 15000 字符）
      protected_recent_turns:     最近 N 轮保留不做 LLM 压缩（默认 3）
      min_rounds_before_compact:  至少 N 轮后才触发压缩（默认 4）
      history_token_budget:       _conversation_history 的 token 预算（默认 6000）
      use_llm_compaction:         是否启用 LLM 压缩（默认 True，回退到模板）
    """

    def __init__(
        self,
        max_context_chars: int = 80000,
        safety_margin: int = 20000,
        min_prune_chars: int = 15000,
        protected_recent_turns: int = 3,
        min_rounds_before_compact: int = 4,
        history_token_budget: int = 6000,
        use_llm_compaction: bool = True,
        use_v1_compaction: bool = True,
    ):
        self.max_context_chars = max_context_chars
        self.safety_margin = safety_margin
        self.min_prune_chars = min_prune_chars
        self.protected_recent_turns = protected_recent_turns
        self.min_rounds_before_compact = min_rounds_before_compact
        self.history_token_budget = history_token_budget
        self.use_llm_compaction = use_llm_compaction
        self.use_v1_compaction = use_v1_compaction

        self._total_compactions = 0
        self._session_id: str = ""
        self._store: Any = None
        self._cached_total_chars = -1
        self._cached_ctx_task = ""
        self._cached_ctx_depth = -1
        self._v1_compactor: Any = None  # lazy init

    # ────────────────────────────────────────────────
    # Token 估算
    # ────────────────────────────────────────────────

    def _invalidate_cache(self):
        """标记缓存失效"""
        self._cached_total_chars = -1

    def _compute_total_chars(self, ctx: RunContext) -> int:
        """全量计算（不缓存）"""
        total = 0
        for r in ctx.tool_results:
            total += len(str(r.get("result", "")))
            total += len(r.get("tool_call", {}).get("name", ""))
        for msg in getattr(ctx, '_conversation_history', []):
            total += len(str(msg.get('content', '')))
        total += len(ctx.knowledge_context)
        if ctx.plan:
            for step in ctx.plan:
                total += len(step.description)
        total += len(ctx.final_answer)
        if ctx.last_error:
            total += len(ctx.last_error)
        return total

    def get_total_chars(self, ctx: RunContext) -> int:
        """估算当前上下文总字符数"""
        return self._compute_total_chars(ctx)

    def _estimate_conversation_tokens(self, ctx: RunContext) -> int:
        """估算 _conversation_history 的 token 数"""
        total = 0
        for msg in getattr(ctx, '_conversation_history', []):
            total += estimate_tokens(str(msg.get('content', '')))
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    total += estimate_tokens(str(tc.get("function", {}).get("name", "")))
                    total += estimate_tokens(str(tc.get("function", {}).get("arguments", "")))
        return total

    def is_overflow(self, ctx: RunContext) -> bool:
        """判断是否超出预算（含 conversation_history）"""
        return self._get_overflow_excess(ctx) > 0

    def _get_overflow_excess(self, ctx: RunContext, total_chars: Optional[int] = None) -> int:
        """计算超出预算的字符数，支持传入已计算的总字符"""
        threshold = self.max_context_chars - self.safety_margin
        current = total_chars if total_chars is not None else self.get_total_chars(ctx)
        return max(0, current - threshold)

    # ────────────────────────────────────────────────
    # 选择要压缩的条目
    # ────────────────────────────────────────────────

    def _select_entries_to_compact(self, ctx: RunContext,
                                   excess: Optional[int] = None) -> int:
        """选择哪些旧条目要压缩，返回要压缩的数量

        策略：保留最近 N 轮，其余全部压缩。如果总轮次太少，返回 0。
        """
        total = len(ctx.tool_results)
        if total <= self.protected_recent_turns + 1:
            return 0
        if total < self.min_rounds_before_compact:
            return 0

        protected = self.protected_recent_turns
        compactable = total - protected
        if compactable <= 0:
            return 0

        if excess is None:
            excess = self._get_overflow_excess(ctx)
        if excess <= 0:
            return 0

        prune_target = max(excess + self.safety_margin, self.min_prune_chars)
        chars_freed = 0

        for i in range(compactable):
            entry = ctx.tool_results[i]
            chars_freed += len(str(entry.get("result", "")))
            if chars_freed >= prune_target:
                return i + 1

        return compactable

    # ────────────────────────────────────────────────
    # 模板摘要（回退方案，不改动）
    # ────────────────────────────────────────────────

    def generate_compaction_summary(self, entries: List[Dict]) -> str:
        """增强模板摘要 — 提取文件路径 / 搜索查询 / 关键结果 / 错误"""
        if not entries:
            return ""

        tool_names: List[str] = []
        success_count = 0
        fail_count = 0
        files: List[str] = []
        queries: List[str] = []
        errors: List[str] = []
        results: List[str] = []

        for e in entries:
            tc = e.get("tool_call", {})
            name = tc.get("name", "")
            ok = e.get("success", False)
            args = tc.get("arguments", {})
            if name:
                tool_names.append(name)
            if ok:
                success_count += 1
            else:
                fail_count += 1

            if name in ("write_file", "edit_file"):
                p = args.get("path", "")
                if p:
                    files.append(p)
            elif name in ("web_search", "search"):
                q = args.get("query", "")
                if q and q not in queries:
                    queries.append(q[:60])
            elif name in ("fetch_url", "read_file"):
                u = args.get("url", "") or args.get("path", "")
                if u:
                    results.append(f"{name}: {u[:60]}")

            result_data = e.get("result", {})
            if isinstance(result_data, dict):
                if not ok:
                    err = str(result_data.get("error", "") or result_data.get("message", "") or "")
                    if err and err not in errors:
                        errors.append(err[:80])

        tools_unique = list(dict.fromkeys(tool_names))
        tools_summary = ", ".join(tools_unique[:6])
        if len(tools_unique) > 6:
            tools_summary += f" 等 {len(tools_unique)} 种工具"

        parts = [
            f"[上下文压缩] 之前 {len(entries)} 轮：{tools_summary}，"
            f"✅{success_count} ❌{fail_count}"
        ]
        if files:
            files_str = "; ".join(files[:3])
            parts.append(f"📄 {files_str}")
        if queries:
            parts.append(f"🔍 {'; '.join(queries[:2])}")
        if results:
            parts.append(f"📍 {'; '.join(results[:2])}")
        if errors:
            err_str = errors[0]
            parts.append(f"⚠️ {err_str}")
        return " | ".join(parts)

    # ────────────────────────────────────────────────
    # LLM 摘要压缩
    # ────────────────────────────────────────────────

    async def _llm_summarize(self, entries: List[Dict],
                             task_description: str) -> str:
        """调用 LLM 对压缩的条目生成结构化摘要

        对标 Opencode 的 compaction agent：
        - 专用 system prompt
        - 结构化输出（Goal/Progress/Key Findings/Next Steps）
        - 失败时回退到模板摘要
        """
        try:
            from core.engine.llm_backend import get_llm_router
            router = get_llm_router()
            if not router or not router.is_available():
                return self.generate_compaction_summary(entries)

            # 构造历史文本（限制每条目 300 字，防超长 prompt 导致 LLM 截断）
            history_lines = [f"## User Task\n{task_description[:500]}\n"]
            for i, e in enumerate(entries[-20:]):  # ponytail: 最多取最近 20 条
                tc = e.get("tool_call", {})
                name = tc.get("name", "?")
                ok = "SUCCESS" if e.get("success") else "FAILED"
                args = tc.get("arguments", {})
                result = e.get("result", {})
                history_lines.append(
                    f"### Call {i+1}: {name} ({ok})\n"
                    f"Args: {json.dumps(args, ensure_ascii=False, default=str)[:200]}\n"
                    f"Result: {json.dumps(result, ensure_ascii=False, default=str)[:300]}\n"
                )

            history_text = "\n".join(history_lines)

            messages = [
                {"role": "system", "content": _COMPACTION_SYSTEM_PROMPT},
                {"role": "user", "content": history_text},
            ]

            import asyncio
            response = await asyncio.wait_for(
                router.chat(messages, temperature=0.3, max_tokens=2048),
                timeout=60,
            )
            text = str(response) if response else ""
            if text and text != "None" and len(text) > 20:
                return text.strip()
        except asyncio.TimeoutError:
            logger.warning("LLM 压缩超时，使用模板摘要")
        except Exception as e:
            logger.warning(f"LLM 压缩失败: {e}，使用模板摘要")

        return self.generate_compaction_summary(entries)

    # ────────────────────────────────────────────────
    # 重建对话历史 + 重排
    # ────────────────────────────────────────────────

    def _rebuild_after_compaction(self, ctx: RunContext,
                                  compacted_count: int, summary: str) -> str:
        """压缩后重建上下文

        对标 Opencode 的 filterCompactedEffect + reorder：

        1. tool_results 重排为 [summary_note, tail..., new...]
        2. _conversation_history 重建：删除旧消息 + 插入摘要消息
        3. knowledge_context 追加摘要

        Returns:
            summary_note 的摘要文本
        """
        # 1. 替换 tool_results
        self._invalidate_cache()
        summary_note: Dict[str, Any] = {
            "compacted": True,
            "summary": summary,
            "count": compacted_count,
        }
        ctx.tool_results = [summary_note] + ctx.tool_results[compacted_count:]

        # 2. 重建 _conversation_history
        # 每个压缩的 entry 对应 ~2 条消息（1 tool msg + 1 assistant msg）
        if getattr(ctx, '_conversation_history', None):
            n_remove = min(compacted_count * 2, len(ctx._conversation_history) - 1)
            ctx._conversation_history = ctx._conversation_history[n_remove:]
            ctx._conversation_history.insert(0, {
                "role": "system",
                "content": f"[上下文摘要] 以下是对之前 {compacted_count} 轮工具调用结果的结构化摘要：\n{summary}",
            })

            # 截断到历史 token 预算（单次扫描决定保留范围）
            budget_tokens = self.history_token_budget * 2
            hist = ctx._conversation_history
            if len(hist) > 2:
                # 从尾部向前扫描，找到第一个使累积 ≤ budget 的位置
                accum = 0
                keep_from = len(hist) - 1
                for i in range(len(hist) - 1, 0, -1):
                    accum += estimate_tokens(str(hist[i].get('content', '')))
                    if accum > budget_tokens:
                        keep_from = i + 1
                        break
                if keep_from > 1:
                    ctx._conversation_history = hist[:1] + hist[keep_from:]
                    self._invalidate_cache()

        # 3. tool_results 总量封顶：保留摘要 + 最多 15 条尾部
        _MAX_TOOL_RESULTS = 16
        if len(ctx.tool_results) > _MAX_TOOL_RESULTS:
            ctx.tool_results = ctx.tool_results[:1] + ctx.tool_results[-(_MAX_TOOL_RESULTS - 1):]

        # 4. 追加到 knowledge_context
        if ctx.knowledge_context:
            ctx.knowledge_context = ctx.knowledge_context[-2000:] + "\n" + summary
        else:
            ctx.knowledge_context = summary

        return summary

    # ────────────────────────────────────────────────
    # 重放指令
    # ────────────────────────────────────────────────

    def _set_replay_instructions(self, ctx: RunContext, summary: str):
        """压缩后设置重放指令 + 同步 STM"""
        ctx.forced_instructions = (
            f"[上下文已压缩] 之前的 {len(ctx.tool_results)} 轮交互已被压缩为以下摘要，"
            f"请基于此继续完成任务：\n\n{summary}\n\n"
            f"不要再重复已经完成的工作，直接继续下一步。"
        )

        # 同步 STM：将 ContextBudget 的摘要也写入 STM，保持两层压缩一致
        try:
            from core.memory.short_term_memory import get_memory_manager
            stm = get_memory_manager()
            stm.add("cli_user", "assistant",
                    f"[上下文压缩摘要] {summary[:500]}")
        except Exception:
            pass

    # ────────────────────────────────────────────────
    # 持久化
    # ────────────────────────────────────────────────

    def _persist_compaction(self, ctx: RunContext,
                            compacted_count: int, summary: str):
        """将压缩记录持久化到 SQLite"""
        if not self._session_id or not self._store:
            return
        try:
            tail_start = len(ctx.tool_results)
            self._store.save_compaction(
                self._session_id, ctx.react_depth,
                summary, tail_start,
            )
        except Exception as e:
            logger.debug(f"持久化压缩记录失败: {e}")

    def init_session(self, session_id: str, store: Any):
        """初始化会话绑定（由 run_react 调用）"""
        self._session_id = session_id
        self._store = store

    # ────────────────────────────────────────────────
    # 主入口
    # ────────────────────────────────────────────────

    async def async_check_and_compact(self, ctx: RunContext) -> bool:
        """检查并执行 LLM 压缩（异步主入口）

        对标 Opencode 的 compaction.process()：

        1. V1 8-layer: L0-L4 + SessionMem + CircuitBreaker (新增)
        2. 检查溢出
        3. 选择旧条目
        4. LLM 摘要
        5. 重建上下文（重排 + 历史重建）
        6. 设置重放指令
        7. 持久化

        Returns:
            True 表示执行了压缩
        """
        total_chars = self.get_total_chars(ctx)
        excess = self._get_overflow_excess(ctx, total_chars=total_chars)
        if excess <= 0:
            return False

        # ── V1 8-layer compression on _conversation_history ──
        if self.use_v1_compaction and getattr(ctx, '_conversation_history', None):
            try:
                if self._v1_compactor is None:
                    from core.memory.context_compactor import ContextCompactor
                    self._v1_compactor = ContextCompactor(
                        model_limit=int(self.history_token_budget * 0.85),
                        compact_threshold=0.85,
                    )
                old_tokens = estimate_tokens(str(ctx._conversation_history))
                v1_msgs = self._v1_compactor.compact(ctx._conversation_history)
                new_tokens = estimate_tokens(str(v1_msgs))
                if new_tokens < old_tokens:
                    ctx._conversation_history = v1_msgs
                    self._invalidate_cache()
                    saved = old_tokens - new_tokens
                    logger.info(f"V1 8-layer压缩: {old_tokens}→{new_tokens} tokens, saved {saved}")
                    _budget_stats.record(0, saved)
                    self._total_compactions += 1
                    # Re-check overflow — V1 might have freed enough
                    total_chars = self.get_total_chars(ctx)
                    excess = self._get_overflow_excess(ctx, total_chars=total_chars)
                    if excess <= 0:
                        return True
            except Exception as e:
                logger.debug(f"V1 8-layer压缩跳过: {e}")

        if not ctx.tool_results:
            return False

        compacted_count = self._select_entries_to_compact(ctx, excess=excess)
        if compacted_count <= 0:
            return False

        # 选择要压缩的条目
        entries_to_compact = ctx.tool_results[:compacted_count]

        # LLM 或模板摘要
        if self.use_llm_compaction:
            summary = await self._llm_summarize(entries_to_compact, ctx.task_description)
        else:
            summary = self.generate_compaction_summary(entries_to_compact)

        # 重建上下文（重排 + 历史重建）
        self._rebuild_after_compaction(ctx, compacted_count, summary)

        # 设置重放指令
        self._set_replay_instructions(ctx, summary)

        # 持久化
        self._persist_compaction(ctx, compacted_count, summary)

        self._total_compactions += 1
        _budget_stats.record(compacted_count,
                             sum(len(str(e.get("result", ""))) for e in entries_to_compact))

        logger.info(
            f"LLM 上下文压缩: {compacted_count} 条被压缩, "
            f"剩余 {len(ctx.tool_results)} 条, "
            f"压缩方式: {'LLM' if self.use_llm_compaction else '模板'}"
        )
        return True

    # ────────────────────────────────────────────────
    # 同步兼容接口（保留原有 check_and_compact）
    # ────────────────────────────────────────────────

    def apply_compaction(self, ctx: RunContext) -> int:
        """同步压缩（保留向后兼容，使用模板）"""
        total = len(ctx.tool_results)
        if total <= self.protected_recent_turns + 1:
            return 0

        protected = self.protected_recent_turns
        compactable = total - protected
        if compactable <= 0:
            return 0

        excess = self._get_overflow_excess(ctx)
        if excess <= 0:
            return 0

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
        self._rebuild_after_compaction(ctx, compact_count, summary)
        self._persist_compaction(ctx, compact_count, summary)

        _budget_stats.record(compact_count, chars_freed)
        logger.info(f"模板压缩: {compact_count} 条被压缩, 释放 {chars_freed} 字符")
        return compact_count

    def check_and_compact(self, ctx: RunContext) -> bool:
        """同步压缩入口（向后兼容）"""
        if not ctx.tool_results:
            return False
        if not self.is_overflow(ctx):
            return False
        return self.apply_compaction(ctx) > 0
