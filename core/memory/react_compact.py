"""React compact — 413 fallback for prompt-too-long errors.

V1→V2: V1 反应式压缩层。由 ContextCompactor.handle_api_error() 调用。
  V2 的 react_core.py on_llm_invoke() 在捕获 API 413/PromptTooLong 异常时，
  通过 get_compactor().handle_api_error() 触发此层的即时压缩。
  Circuit breaker 内置防止重复失败。

保留原因: V2 目前只在 Exception handler 中捕获 413 后触发此层。若删除，
  413 错误将直接导致 LLM 调用失败中断，无法自动恢复。

Based on Claude Code's reactiveCompact:
- When API returns 413/PromptTooLong, trigger immediate compaction
- More aggressive than auto-compact (smaller token budget)
- Circuit breaker: stop after MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES (3)

Key behaviors:
- Triggered by API error, not proactive threshold check
- Uses smaller token budget to ensure it fits
- Resets circuit breaker on success
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Circuit breaker constants (from autoCompact.ts:70)
MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3


class ReactCompact:
    """Handles 413/PromptTooLong errors with immediate compaction.

    Based on Claude Code's reactiveCompact:
    - When API returns prompt-too-long, trigger immediate compaction
    - More aggressive than auto-compact (smaller token budget)
    - Circuit breaker to stop hammering the API

    Key insight from source:
    "Without this, sessions where context is irrecoverably over the limit
    hammer the API with doomed compaction attempts on every turn."
    """

    def __init__(self):
        self._consecutive_failures = 0
        self._reactive_compacts = 0
        self._total_tokens_saved = 0

    def should_react(self) -> bool:
        """Check if we should attempt reactive compaction.

        Circuit breaker: stop after MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES (3).
        """
        return self._consecutive_failures < MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES

    def compact(
        self,
        messages: List[Dict[str, Any]],
        error_message: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """React to a 413/PromptTooLong error with immediate compaction.

        More aggressive than auto-compact:
        - Smaller token budget (30% of model limit vs 50%)
        - Drop more old messages
        - Force compaction regardless of threshold

        Args:
            messages: List of message dicts.
            error_message: The API error message (for logging).

        Returns:
            Compacted message list.
        """
        if not self.should_react():
            logger.warning(
                "React compact: circuit breaker tripped (%d consecutive failures), "
                "skipping reactive compaction",
                self._consecutive_failures,
            )
            return messages

        from core.memory.token_counter import count_messages_tokens
        from core.memory.l3_llm_compaction import L3LLMCompaction
        from core.memory.l4_post_compact_rebuild import L4PostCompactRebuild

        original_tokens = count_messages_tokens(messages)

        try:
            # More aggressive compaction for reactive mode
            compactor = L3LLMCompaction(
                compact_threshold=0.5,
                force_threshold=0.7,
            )

            compaction_result = compactor.compact(messages, force=True)
            if compaction_result.get("skipped"):
                return messages

            # Build message list from compaction result via L4
            rebuilt = L4PostCompactRebuild().build(
                compaction_result=compaction_result,
            )
            final_tokens = count_messages_tokens(rebuilt)

            self._consecutive_failures = 0
            self._reactive_compacts += 1
            self._total_tokens_saved += original_tokens - final_tokens

            logger.info(
                "React compact: %d → %d tokens (saved %d, error: %s)",
                original_tokens, final_tokens,
                original_tokens - final_tokens,
                error_message[:100] if error_message else "unknown",
            )

            return rebuilt

        except Exception as e:
            self._consecutive_failures += 1
            logger.warning(
                "React compact: failed (attempt %d/3): %s",
                self._consecutive_failures,
                e,
            )

            # If compaction itself fails, truncate oldest messages as last resort
            if self._consecutive_failures >= MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES:
                logger.warning(
                    "React compact: circuit breaker tripped, truncating oldest messages"
                )
                return self._truncate_oldest(messages)

            return messages

    def _truncate_oldest(
        self,
        messages: List[Dict[str, Any]],
        drop_ratio: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """Truncate oldest messages as last resort.

        When compaction itself fails, drop oldest messages to reduce context.
        """
        system_prompt = messages[0] if messages and messages[0]["role"] == "system" else None
        start_idx = 1 if system_prompt else 0

        drop_count = max(1, int((len(messages) - start_idx) * drop_ratio))
        result = messages[:start_idx] + messages[start_idx + drop_count:]

        logger.warning(
            "React compact: truncated %d oldest messages (last resort)",
            drop_count,
        )

        return result

    def get_stats(self) -> Dict[str, int]:
        """Return reactive compaction statistics."""
        return {
            "consecutive_failures": self._consecutive_failures,
            "reactive_compacts": self._reactive_compacts,
            "total_tokens_saved": self._total_tokens_saved,
        }
