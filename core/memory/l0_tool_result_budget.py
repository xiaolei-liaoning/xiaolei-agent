"""L0: ToolResultBudget — per-message char limit enforcement.

V1→V2: V1 压缩层 L0。由 ContextCompactor (context_compactor.py) 统一编排，
  在 async_check_and_compact() 的 V1 pipeline 中作为第一层运行。V2
  ContextBudgetManager 通过 ContextCompactor 间接调用此层。

保留原因: ContextCompactor 8-layer pipeline 的组成部分。删除会导致超大工具
  结果无法溢出到磁盘，撑爆上下文窗口。

When a tool result exceeds the per-message limit, write the full result to
disk and replace inline content with a file reference. Prevents any single
tool result from blowing up the context window.

Ponytail: simple char threshold + disk spill. Upgrade to token-aware budget
if the LLM backend provides per-message token counts.
"""

import json
import logging
import os
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS = 100_000  # ponytail: 100K chars ≈ 25K tokens, enough for most results
DEFAULT_SPILL_DIR = None  # auto: $TMPDIR/opencode_spill/


class L0ToolResultBudget:
    def __init__(self, max_chars: int = DEFAULT_MAX_CHARS, spill_dir: str | None = None):
        self.max_chars = max_chars
        self.spill_dir = spill_dir or os.path.join(
            os.environ.get("TMPDIR", "/tmp"), "opencode_spill"
        )
        self._budgeted = 0
        self._spilled = 0
        self._chars_saved = 0

    def apply(self, messages: list[dict]) -> list[dict]:
        """Enforce per-message char limit on tool results.

        Messages with role='tool' whose content exceeds max_chars get their
        content spilled to disk and replaced with a file-reference block.
        """
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role != "tool" or not isinstance(content, str):
                continue
            if len(content) <= self.max_chars:
                continue

            spill_path = self._write_spill(content, msg)
            msg["content"] = (
                f"[Tool result exceeds character budget ({len(content)} > {self.max_chars}). "
                f"Full content written to: {spill_path}]"
            )
            msg["_spilled"] = True
            msg["_spill_path"] = spill_path
            self._budgeted += 1
            self._chars_saved += len(content) - len(msg["content"])

            logger.debug(
                "L0: spilled tool result (%d chars → %s)",
                len(content), spill_path,
            )

        return messages

    def _write_spill(self, content: str, msg: dict) -> str:
        os.makedirs(self.spill_dir, exist_ok=True)
        tool_name = msg.get("name", "unknown")
        stamp = time.strftime("%Y%m%d_%H%M%S")
        fid = uuid.uuid4().hex[:8]
        path = os.path.join(self.spill_dir, f"{tool_name}_{stamp}_{fid}.txt")
        with open(path, "w") as f:
            f.write(content)
        self._spilled += 1
        return path

    def get_stats(self) -> dict:
        return {
            "budgeted": self._budgeted,
            "spilled": self._spilled,
            "chars_saved": self._chars_saved,
            "max_chars": self.max_chars,
        }
