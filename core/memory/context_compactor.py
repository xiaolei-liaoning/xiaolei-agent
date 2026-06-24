"""7-layer context compaction engine — mirrors Claude Code's compact architecture.

Layer order (matching Claude Code source):
  L0  ToolResultBudget       — per-message char limit, spill oversized to disk
  L1a API-Level Context Mgmt  — clear_tool_uses_20250919 + clear_thinking_20251015
  L1b CollapseReadSearch      — UI-only display metadata tracker (messages pass through)
  L1c Time-Based MC           — gap >60min → keep recent 5 results
  L2  CachedMicrocompact      — generate cache breakpoint metadata (no message modification)
  L2b SnipCompact             — independent snip of old tool results (first-half + last-quarter)
  L3  LLM Compaction          — compactConversation() with PTL retry + pre/post hooks
  L4  Post-Compact Rebuild    — buildPostCompactMessages with all attachment types
  +   Reactive Compact        — 413 fallback
  +   Session Memory Compact  — experimental LLM-free heuristic fallback
  +   Circuit Breaker         — stop after MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3

Ponytail: 7 layers, not 5. Verified against compact.ts (1705 lines).
"""

import logging
import time
from typing import Any

from core.memory.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class ContextCompactor:
    """7-layer context compaction orchestrator.

    Designed as a single pipeline:
      1. Check circuit breaker + threshold
      2. Run L0→L2b (non-LLM layers)
      3. If enough space saved → return
      4. Run L3 (LLM compaction with PTL retry)
      5. Run L4 (post-compact rebuild with attachments)
      6. Update circuit breaker state
    """

    def __init__(
        self,
        model_limit: int = 8000,
        compact_threshold: float = 0.7,
        time_based_mc_enabled: bool = False,
        time_gap_threshold_minutes: float = 60,
    ):
        self.model_limit = model_limit
        self.compact_threshold = compact_threshold

        # Lazy-import layers to avoid circular imports at module level
        self._l0 = None
        self._l1a = None
        self._l1b = None
        self._l1c = None
        self._l2 = None
        self._l2b = None
        self._l3 = None
        self._l4 = None
        self._react = None
        self._session_mem = None
        self._circuit_breaker = CircuitBreaker()

        self._time_based_mc_enabled = time_based_mc_enabled
        self._time_gap_threshold_minutes = time_gap_threshold_minutes
        self._last_assistant_timestamp: float | None = None
        self._total_compactions = 0
        self._total_tokens_saved = 0

    @property
    def l0(self):
        if self._l0 is None:
            from core.memory.l0_tool_result_budget import L0ToolResultBudget
            self._l0 = L0ToolResultBudget()
        return self._l0

    @property
    def l1a(self):
        if self._l1a is None:
            from core.memory.l1a_api_context_mgmt import L1aApiContextMgmt
            self._l1a = L1aApiContextMgmt()
        return self._l1a

    @property
    def l1b(self):
        if self._l1b is None:
            from core.memory.l1b_collapse_read_search import CollapseReadSearchManager
            self._l1b = CollapseReadSearchManager()
        return self._l1b

    @property
    def l1c(self):
        if self._l1c is None:
            from core.memory.l1c_time_based_mc import L1cTimeBasedMicrocompact
            self._l1c = L1cTimeBasedMicrocompact(
                enabled=self._time_based_mc_enabled,
                gap_threshold_minutes=self._time_gap_threshold_minutes,
            )
        return self._l1c

    @property
    def l2(self):
        if self._l2 is None:
            from core.memory.l2_cached_microcompact import L2CachedMicrocompact
            self._l2 = L2CachedMicrocompact()
        return self._l2

    @property
    def l2b(self):
        if self._l2b is None:
            from core.memory.l2b_snip_compact import L2bSnipCompact
            self._l2b = L2bSnipCompact()
        return self._l2b

    @property
    def l3(self):
        if self._l3 is None:
            from core.memory.l3_llm_compaction import L3LLMCompaction
            self._l3 = L3LLMCompaction(model_limit=self.model_limit)
        return self._l3

    @property
    def l4(self):
        if self._l4 is None:
            from core.memory.l4_post_compact_rebuild import L4PostCompactRebuild
            self._l4 = L4PostCompactRebuild()
        return self._l4

    @property
    def react(self):
        if self._react is None:
            from core.memory.react_compact import ReactCompact
            self._react = ReactCompact()
        return self._react

    @property
    def session_mem(self):
        if self._session_mem is None:
            from core.memory.session_memory_compaction import SessionMemoryCompaction
            self._session_mem = SessionMemoryCompaction()
        return self._session_mem

    # ------------------------------------------------------------------
    # Main orchestration
    # ------------------------------------------------------------------

    def compact(
        self,
        messages: list[dict],
        force: bool = False,
        recent_files: list[dict] | None = None,
        skills: list[dict] | None = None,
        active_agents: list[dict] | None = None,
        plan_content: str | None = None,
        plan_file_path: str | None = None,
        is_plan_mode: bool = False,
        tools: list[dict] | None = None,
        mcp_clients: list[dict] | None = None,
    ) -> list[dict]:
        """Run full 7-layer compaction pipeline.

        Mirrors autoCompactIfNeeded() + compactConversation() from Claude Code.
        """
        from core.memory.token_counter import count_messages_tokens

        original_tokens = count_messages_tokens(messages)

        # Circuit breaker check
        if self._circuit_breaker.is_tripped():
            logger.warning("Compaction: circuit breaker tripped, skipping")
            return messages

        # Threshold check
        if not force and not self.l3.should_compact(original_tokens):
            return messages

        # Update L1c timestamp
        if self._last_assistant_timestamp is not None:
            self.l1c.update_assistant_timestamp(self._last_assistant_timestamp)

        # ---- Non-LLM layers (L0 → L2b) ----
        # L0: ToolResultBudget — spill oversized results to disk
        messages = self.l0.apply(messages)

        # L1a: API-level context management
        messages = self.l1a.clear_tool_results(messages, original_tokens)
        messages = self.l1a.clear_thinking_blocks(messages)

        # L1b: CollapseReadSearch — UI-only, messages pass through
        messages = self.l1b.collapse(messages)

        # L1c: Time-based microcompact
        messages = self.l1c.clear_old_results(messages)

        # L2: CachedMicrocompact — generate cache edit metadata (no content change)
        messages = self.l2.scan(messages)

        # L2b: SnipCompact — independent snip of oversized tool results
        messages = self.l2b.compact(
            messages,
            aggressive=self.l1c.should_clear() if hasattr(self.l1c, "should_clear") else False,
        )

        # Check if L0-L2b freed enough space
        after_light = count_messages_tokens(messages)
        usage = after_light / self.model_limit

        if usage <= self.compact_threshold and not force:
            logger.info(
                "Compaction: L0-L2b sufficient, %d → %d tokens (saved %d)",
                original_tokens, after_light, original_tokens - after_light,
            )
            self._total_compactions += 1
            self._total_tokens_saved += original_tokens - after_light
            self._circuit_breaker.record_success()
            return messages

        # ---- LLM layers (L3 → L4) ----
        try:
            # L3: LLM compaction (with PTL retry)
            compaction_result = self.l3.compact(messages, force=force)

            # L4: Post-compact rebuild with attachments
            rebuilt = self.l4.build(
                compaction_result=compaction_result,
                recent_files=recent_files,
                skills=skills,
                active_agents=active_agents,
                plan_content=plan_content,
                plan_file_path=plan_file_path,
                is_plan_mode=is_plan_mode,
                tools=tools,
                mcp_clients=mcp_clients,
            )

            final_tokens = count_messages_tokens(rebuilt)
            self._total_compactions += 1
            self._total_tokens_saved += original_tokens - final_tokens
            self._circuit_breaker.record_success()

            logger.info(
                "Compaction: %d → %d tokens (saved %d, %d layers)",
                original_tokens, final_tokens, original_tokens - final_tokens, 7,
            )

            return rebuilt

        except Exception as e:
            logger.warning("Compaction: L3+L4 failed: %s", e)
            self._circuit_breaker.record_failure()

            # Fallback: session memory compaction (heuristic, no LLM)
            try:
                fallback_result = self.session_mem.compact(messages)
                rebuilt = self.l4.build(
                    compaction_result=fallback_result,
                    recent_files=recent_files,
                    skills=skills,
                )
                logger.info("Compaction: fell back to session memory compaction")
                return rebuilt
            except Exception as e2:
                logger.error("Compaction: all paths failed: %s", e2)
                return messages

    # ------------------------------------------------------------------
    # Reactive compaction (413 fallback)
    # ------------------------------------------------------------------

    def handle_api_error(self, messages: list[dict], error: Exception) -> list[dict]:
        """Handle API 413/PromptTooLong with reactive compaction."""
        error_msg = str(error).lower()
        if "prompt_too_long" in error_msg or "too long" in error_msg:
            return self.react.compact(messages, error_message=str(error))
        return messages

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_assistant_timestamp(self, timestamp: float | None = None) -> None:
        self._last_assistant_timestamp = timestamp or time.time()

    def get_compaction_stats(self) -> dict:
        return {
            "model_limit": self.model_limit,
            "total_compactions": self._total_compactions,
            "total_tokens_saved": self._total_tokens_saved,
            "circuit_breaker": self._circuit_breaker.get_stats(),
            "l0": self.l0.get_stats(),
            "l1a": self.l1a.get_stats(),
            "l1b": self.l1b.get_stats(),
            "l1c": self.l1c.get_stats(),
            "l2": self.l2.get_stats(),
            "l2b": self.l2b.get_stats(),
            "l3": self.l3.get_stats(),
            "l4": self.l4.get_rebuild_info(),
            "react": self.react.get_stats(),
            "session_mem": self.session_mem.get_stats(),
        }


_compactor: ContextCompactor | None = None


def get_compactor(
    model_limit: int = 8000,
    time_based_mc_enabled: bool = False,
) -> ContextCompactor:
    global _compactor
    if _compactor is None:
        _compactor = ContextCompactor(
            model_limit=model_limit,
            time_based_mc_enabled=time_based_mc_enabled,
        )
    return _compactor
