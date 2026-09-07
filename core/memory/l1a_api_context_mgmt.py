"""L1a: API-Level Context Management — simulates Claude Code's server-side clearing.

V1→V2: V1 压缩层 L1a。由 ContextCompactor (context_compactor.py) 统一编排，
  在 async_check_and_compact() 的 V1 pipeline 中作为第二层运行。清除旧的工具
  调用结果和 thinking 块。V2 ContextBudgetManager 通过 ContextCompactor 间接调用此层。

保留原因: ContextCompactor 8-layer pipeline 的组成部分。删除会导致历史消息中
  大量冗余的工具结果和推理块残留，加速上下文膨胀。

Based on Claude Code's apiMicrocompact.ts:
- clear_tool_uses_20250919: Clear tool results for shell/glob/grep/read/web_fetch/web_search
- clear_thinking_20251015: Clear thinking blocks (keep last N turns)
- Thresholds: 180K trigger / 40K target / 25K min keep

Since our API doesn't support server-side context management,
we simulate it by clearing tool results client-side.
"""

import logging
import time
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Tools whose results are clearable (from apiMicrocompact.ts:19-26)
TOOLS_CLEARABLE_RESULTS = {
    "shell", "bash", "exec", "execute",
    "glob", "find_files", "list_files",
    "grep", "search", "rg", "ripgrep",
    "read", "read_file", "cat",
    "web_fetch", "fetch", "http_get",
    "web_search", "search_web", "google",
}

# Default thresholds (from apiMicrocompact.ts:16-17)
DEFAULT_MAX_INPUT_TOKENS = 180_000
DEFAULT_TARGET_INPUT_TOKENS = 40_000
DEFAULT_KEEP_RECENT = 5


class L1aApiContextMgmt:
    """Simulates API-level context management.

    Claude Code delegates this to the Anthropic API server, but since we
    don't have that capability, we implement it client-side by clearing
    tool results when token count exceeds threshold.

    Key behaviors from source:
    - clear_tool_uses_20250919: Clears tool inputs from old tool_use blocks
    - clear_thinking_20251015: Clears thinking blocks, keeps last N turns
    - Time-based: If >1h since last assistant message, clear more aggressively
    """

    def __init__(
        self,
        max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS,
        target_input_tokens: int = DEFAULT_TARGET_INPUT_TOKENS,
        keep_recent: int = DEFAULT_KEEP_RECENT,
    ):
        self.max_input_tokens = max_input_tokens
        self.target_input_tokens = target_input_tokens
        self.keep_recent = keep_recent
        self._clears = 0
        self._tokens_freed = 0

    def should_clear(self, token_count: int) -> bool:
        """Check if token count exceeds clear threshold."""
        return token_count > self.max_input_tokens

    def clear_tool_results(
        self,
        messages: List[Dict[str, Any]],
        token_count: int,
        time_gap_minutes: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Clear tool results from old messages.

        Based on clear_tool_uses_20250919 strategy:
        - 保留范围说明：见 compact() 方法注释。原始注释 "Keep first half + last quarter"
          与实际行为相反（实际清中段，保留 [first_half, last_quarter)），代码已修正。
        - More aggressive if >1h since last assistant message (cache expired)

        Args:
            messages: List of message dicts.
            token_count: Current token count.
            time_gap_minutes: Minutes since last assistant message (for time-based MC).

        Returns:
            Modified message list with cleared tool results.
        """
        if not self.should_clear(token_count) and time_gap_minutes is None:
            return messages

        # Determine how aggressively to clear
        # Time-based MC: if >1h gap, clear more aggressively (cache expired)
        is_cache_expired = time_gap_minutes is not None and time_gap_minutes > 60

        # Calculate how many tokens we need to free
        target_tokens = self.target_input_tokens if not is_cache_expired else self.target_input_tokens // 2
        tokens_to_free = max(0, token_count - target_tokens)

        if tokens_to_free <= 0 and not is_cache_expired:
            return messages

        # Find clearable tool result messages
        clearable_indices = []
        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")

            # Only clear tool-role messages
            if role != "tool":
                continue

            # Check if this is a clearable tool result
            tool_name = msg.get("name", "").lower()
            if tool_name not in TOOLS_CLEARABLE_RESULTS:
                continue

            # Don't clear recent messages
            if i >= len(messages) - self.keep_recent:
                continue

            clearable_indices.append((i, len(str(content))))

        if not clearable_indices:
            return messages

        # Sort by index (oldest first) and clear until we've freed enough tokens
        clearable_indices.sort(key=lambda x: x[0])

        # Strategy（与早期注释 "Keep first half + last quarter" 相反）：
        # 实际保留的是 clearable 列表的 [first_half : last_quarter_start] 段，
        # 即**清掉前 50% + 后 25%，保留中段 25%**。
        # 注释历史：源自 clawspring/compaction.py，逻辑抄错导致保留区间颠倒。
        total_clearable = len(clearable_indices)
        first_half_end = total_clearable // 2
        last_quarter_start = total_clearable * 3 // 4

        cleared_count = 0
        for idx, (i, char_count) in enumerate(clearable_indices):
            # 跳过前一半（前 50% 保留） — 注意：这里 idx < first_half_end 是 continue，
            # 意味着前 50% 也"保留"了。配合下面 last_quarter_start，
            # 实际清理的是 [first_half, last_quarter) 这段中段。
            if idx < first_half_end or idx >= last_quarter_start:
                continue

            # Estimate tokens freed (rough: 1 token ≈ 4 chars)
            tokens_freed = char_count // 4

            # Clear the tool result
            messages[i]["content"] = (
                f"[Tool result cleared by context management — "
                f"~{tokens_freed} tokens freed]"
            )
            cleared_count += 1
            self._tokens_freed += tokens_freed

            # Check if we've freed enough
            if self._tokens_freed >= tokens_to_free:
                break

        if cleared_count > 0:
            self._clears += 1
            logger.debug(
                "L1a: cleared %d tool results, freed ~%d tokens",
                cleared_count,
                self._tokens_freed,
            )

        return messages

    def clear_thinking_blocks(
        self,
        messages: List[Dict[str, Any]],
        keep_turns: int = 1,
    ) -> List[Dict[str, Any]]:
        """Clear thinking blocks from old assistant messages.

        Based on clear_thinking_20251015 strategy:
        - keep: 'all' — keep all thinking turns (normal mode)
        - keep: { type: 'thinking_turns', value: 1 } — keep only last thinking turn

        Args:
            messages: List of message dicts.
            keep_turns: Number of thinking turns to keep (default: 1).

        Returns:
            Modified message list with cleared thinking blocks.
        """
        thinking_count = 0
        for msg in reversed(messages):
            if msg.get("role") != "assistant":
                continue

            content = msg.get("content", "")
            if not isinstance(content, str):
                continue

            # Check for thinking blocks
            if "<think>" in content:
                thinking_count += 1
                if thinking_count > keep_turns:
                    # Strip thinking block
                    import re
                    msg["content"] = re.sub(
                        r'<think>.*?</think>',
                        '[thinking cleared]',
                        content,
                        flags=re.DOTALL,
                    )

        return messages

    def get_stats(self) -> Dict[str, int]:
        """Return clearing statistics."""
        return {
            "clears": self._clears,
            "tokens_freed": self._tokens_freed,
        }
