"""L1c: Time-based microcompact — clears old results when cache expires.

V1→V2: V1 压缩层 L1c。由 ContextCompactor 编排，在 V1 pipeline 中作为第四层运行。
  基于时间间隔清除旧工具结果（>60min 仅保留最近 5 条）。V2 ContextBudgetManager
  通过 ContextCompactor 间接调用此层。

保留原因: ContextCompactor 8-layer pipeline 的组成部分。防止长时间会话中
  上下文因旧结果堆积而膨胀。V2 的 entry-level 压缩不处理时间维度。

Based on Claude Code's timeBasedMCConfig.ts:
- Triggers content-clearing when gap since last assistant message > threshold
- Server-side prompt cache has ~1h TTL, so full prefix will be rewritten
- Clearing old tool results before request shrinks what gets rewritten
- Runs BEFORE API call (in microcompactMessages, upstream of callModel)

Default config:
- enabled: false（参数字段，但 clear_old_results() 实际不读此字段，每次都执行）
  注意：原注释说 "opt-in via feature flag"，但代码里没有 feature flag 机制
  —— enabled 只控制 should_clear() 返回值，不影响 clear_old_results() 调用
- gapThresholdMinutes: 60 (matches server's 1h cache TTL)
- keepRecent: 5 (keep most recent N compactable tool results)
"""

import logging
import time
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Default configuration (from timeBasedMCConfig.ts:30-34)
DEFAULT_GAP_THRESHOLD_MINUTES = 60
DEFAULT_KEEP_RECENT = 5

# Tools whose results are clearable by time-based MC
TIME_BASED_CLEARABLE_TOOLS = {
    "shell", "bash", "exec", "execute",
    "glob", "find_files", "list_files",
    "grep", "search", "rg", "ripgrep",
    "read", "read_file", "cat",
    "web_fetch", "fetch", "http_get",
    "web_search", "search_web", "google",
}


class L1cTimeBasedMicrocompact:
    """Time-based microcompact for cache expiration.

    Based on Claude Code's timeBasedMCConfig:
    - When gap since last assistant message > threshold (default 60min),
      the server's prompt cache has expired
    - Clear old tool results to shrink what gets rewritten
    - Runs BEFORE the API call so the shrunk prompt is what gets sent

    Key insight: Running after the first cache miss would only help
    subsequent turns, so we run proactively when we detect the gap.
    """

    def __init__(
        self,
        enabled: bool = False,
        gap_threshold_minutes: float = DEFAULT_GAP_THRESHOLD_MINUTES,
        keep_recent: int = DEFAULT_KEEP_RECENT,
    ):
        self.enabled = enabled
        self.gap_threshold_minutes = gap_threshold_minutes
        self.keep_recent = keep_recent
        self._clears = 0
        self._tokens_freed = 0
        self._last_assistant_timestamp: Optional[float] = None

    def update_assistant_timestamp(self, timestamp: Optional[float] = None) -> None:
        """Update the timestamp of the last assistant message."""
        self._last_assistant_timestamp = timestamp or time.time()

    def should_clear(self) -> bool:
        """Check if time-based clearing should trigger."""
        if not self.enabled:
            return False

        if self._last_assistant_timestamp is None:
            return False

        gap_minutes = (time.time() - self._last_assistant_timestamp) / 60
        return gap_minutes > self.gap_threshold_minutes

    def clear_old_results(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Clear old tool results when cache has expired.

        Based on Claude Code's time-based MC:
        - Keep only the most recent N compactable tool results
        - Older results are cleared since cache has expired

        Args:
            messages: List of message dicts.

        Returns:
            Modified message list with cleared old results.
        """
        if not self.should_clear():
            return messages

        # Find clearable tool result messages (oldest first)
        # 修复 #130: OpenAI 格式的 tool 消息没有 "name" 字段（工具名在前面
        # assistant 消息的 tool_calls 里），原实现 name 永远空 → 永远清不了。
        # Claude Code 的 time-based MC 本意就是"cache 过期后清旧 tool results"，
        # 不依赖工具名过滤——因此放宽为所有 tool 结果均可清理。
        clearable_indices = []
        for i, msg in enumerate(messages):
            if msg.get("role", "") == "tool":
                clearable_indices.append(i)

        if len(clearable_indices) <= self.keep_recent:
            return messages

        # Keep only the most recent N, clear the rest
        to_clear = clearable_indices[:len(clearable_indices) - self.keep_recent]

        cleared_count = 0
        for i in to_clear:
            content = str(messages[i].get("content", ""))
            tokens_freed = len(content) // 4

            messages[i]["content"] = (
                f"[Tool result cleared by time-based MC — "
                f"cache expired, ~{tokens_freed} tokens freed]"
            )
            cleared_count += 1
            self._tokens_freed += tokens_freed

        if cleared_count > 0:
            self._clears += 1
            gap_minutes = (time.time() - self._last_assistant_timestamp) / 60
            logger.debug(
                "L1c: time-based MC cleared %d results (gap=%.1fmin > threshold=%.1fmin), "
                "freed ~%d tokens",
                cleared_count,
                gap_minutes,
                self.gap_threshold_minutes,
                self._tokens_freed,
            )

        return messages

    def get_stats(self) -> Dict[str, int]:
        """Return clearing statistics."""
        return {
            "clears": self._clears,
            "tokens_freed": self._tokens_freed,
            "enabled": 1 if self.enabled else 0,
        }
