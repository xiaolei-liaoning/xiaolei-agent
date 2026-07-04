"""L2b: SnipCompact — independent snip of oversized tool results.

V1→V2: V1 压缩层 L2b。由 ContextCompactor 编排，在 V1 pipeline 中作为第六层运行。
  对过大的旧工具结果进行截断（前半部分 + 后四分之一）。V2 ContextBudgetManager
  通过 ContextCompactor 间接调用此层。

保留原因: ContextCompactor 8-layer pipeline 的组成部分。与 V2 entry-level 压缩
  互补：V1 在此层做消息级别截断，V2 做条目级别摘要。

Runs BEFORE CachedMicrocompact (they don't conflict). Snips old tool results
exceeding max_chars by keeping first half + last quarter. This is the original
snip_old_tool_results from clawspring/compaction.py.

Ponytail: direct port, no abstraction. First-half + last-quarter heuristic
is verified by Claude Code production — good enough.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS = 2000
DEFAULT_PRESERVE_LAST_N_TURNS = 6


class L2bSnipCompact:
    def __init__(
        self,
        max_chars: int = DEFAULT_MAX_CHARS,
        preserve_last_n_turns: int = DEFAULT_PRESERVE_LAST_N_TURNS,
    ):
        self.max_chars = max_chars
        self.preserve_last_n_turns = preserve_last_n_turns
        self._compactions = 0
        self._trimmed_count = 0
        self._chars_snipped = 0

    def compact(self, messages: list[dict], aggressive: bool = False) -> list[dict]:
        if len(messages) <= self.preserve_last_n_turns:
            return messages

        effective_max = self.max_chars // 2 if aggressive else self.max_chars
        cutoff = max(0, len(messages) - self.preserve_last_n_turns)
        snipped_any = False

        for i in range(cutoff):
            m = messages[i]
            role = m.get("role", "")
            content = m.get("content", "")

            if role != "tool" and not (role == "user" and isinstance(content, str) and len(content) > effective_max):
                continue
            if not isinstance(content, str) or len(content) <= effective_max:
                continue

            first_half = content[:effective_max // 2]
            last_quarter = content[-(effective_max // 4):]
            snipped = len(content) - len(first_half) - len(last_quarter)

            m["content"] = (
                f"{first_half}\n"
                f"[... {snipped} chars snipped ...]\n"
                f"{last_quarter}"
            )
            m["_snipped"] = True
            snipped_any = True
            self._trimmed_count += 1
            self._chars_snipped += snipped

        if snipped_any:
            self._compactions += 1

        return messages

    def get_stats(self) -> dict:
        return {
            "compactions": self._compactions,
            "trimmed_count": self._trimmed_count,
            "chars_snipped": self._chars_snipped,
        }
