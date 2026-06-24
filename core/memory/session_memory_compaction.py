"""Session Memory Compaction — experimental LLM-free compaction path.

Heuristic-based compaction for when LLM compaction is unavailable or
when the session is too large to fit even the compaction prompt. Uses
pattern matching to identify and preserve key context: user requests,
file paths, error messages, pending tasks.

Ponytail: heuristic-only. If LLM is available, L3 always wins.
This is a fallback path for when LLM call fails or circuit breaker is tripped.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

KEY_SECTIONS = [
    (r"(?:request|requirement|need|want|please|帮|请|需要)", "user_request"),
    (r"(?:error|fail|bug|crash|exception|stack|trace|报错|错误|失败)", "error"),
    (r"(?:file|path|/[\w/.-]+)", "file_path"),
    (r"(?:pending|todo|next|继续|下一步|接下来)", "pending_task"),
    (r"(?:commit|merge|push|pr|pull|branch|合并)", "git_op"),
    (r"(?:decision|reason|because|因为|所以|决定)", "decision"),
]


class SessionMemoryCompaction:
    """Heuristic compaction that extracts key sections without LLM.

    Scans messages for patterns matching user requests, errors, file
    paths, pending tasks, and decisions. Produces a structured summary
    that mimics the 9-section format but without an LLM call.
    """

    def __init__(self, max_summary_chars: int = 4000):
        self.max_summary_chars = max_summary_chars
        self._compactions = 0

    def compact(self, messages: list[dict]) -> list[dict]:
        """Compact messages using heuristic extraction.

        Returns a dict in the same CompactionResult format as L3,
        so the orchestrator can swap L3 for this when LLM is unavailable.
        """
        user_msgs = [m for m in messages if m.get("role") == "user"]
        assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
        tool_msgs = [m for m in messages if m.get("role") == "tool"]

        sections: dict[str, list[str]] = {
            "user_request": [], "error": [], "file_path": [],
            "pending_task": [], "git_op": [], "decision": [],
            "general": [],
        }

        for m in user_msgs + assistant_msgs:
            content = m.get("content", "")
            if not isinstance(content, str):
                continue
            matched = False
            for pattern, section in KEY_SECTIONS:
                if re.search(pattern, content, re.IGNORECASE):
                    sections[section].append(self._trim(content, 200))
                    matched = True
                    break
            if not matched:
                sections["general"].append(self._trim(content, 200))

        summary_parts = []
        if sections["user_request"]:
            summary_parts.append("1. Primary Requests:\n" + "\n".join(f"   - {s}" for s in sections["user_request"][:5]))
        if sections["error"]:
            summary_parts.append("2. Errors:\n" + "\n".join(f"   - {s}" for s in sections["error"][:5]))
        if sections["pending_task"]:
            summary_parts.append("3. Pending Tasks:\n" + "\n".join(f"   - {s}" for s in sections["pending_task"][:5]))
        if sections["decision"]:
            summary_parts.append("4. Decisions:\n" + "\n".join(f"   - {s}" for s in sections["decision"][:5]))
        if sections["file_path"]:
            paths = set()
            for s in sections["file_path"]:
                for p in re.findall(r"/[\w/.-]+", s):
                    paths.add(p)
            if paths:
                summary_parts.append("5. Files Referenced:\n" + "\n".join(f"   - {p}" for p in sorted(paths)[:10]))
        if sections["general"]:
            summary_parts.append(f"6. Other Context: {len(sections['general'])} items")

        summary = "\n\n".join(summary_parts)
        if len(summary) > self.max_summary_chars:
            summary = summary[:self.max_summary_chars] + "\n\n[... truncated ...]"

        boundary = {
            "role": "system",
            "content": (
                "[System notice: Conversation compacted via session memory compaction "
                "(LLM-free heuristic path).]"
            ),
        }

        summary_msgs = [{
            "role": "user",
            "content": (
                "This session is being continued from a previous conversation.\n\n"
                f"{summary}"
            ),
            "is_compact_summary": True,
        }]

        messages_to_keep = messages[-4:] if len(messages) >= 4 else messages

        self._compactions += 1

        return {
            "boundary_marker": boundary,
            "summary_messages": summary_msgs,
            "messages_to_keep": messages_to_keep,
            "pre_compact_token_count": sum(len(str(m.get("content", ""))) for m in messages) // 4,
            "post_compact_token_count": sum(len(str(m.get("content", ""))) for m in [boundary] + summary_msgs + messages_to_keep) // 4,
            "summary_text": summary,
        }

    def _trim(self, text: str, max_chars: int) -> str:
        return text[:max_chars] + "..." if len(text) > max_chars else text

    def get_stats(self) -> dict:
        return {"compactions": self._compactions}
