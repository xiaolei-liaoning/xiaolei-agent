"""L1b: CollapseReadSearch — UI-only display metadata tracker.

In Claude Code this is a rendering concern: consecutive Read/Grep/Search
tool_use blocks are collapsed into a summary group for the UI. The message
array sent to the API is NEVER modified.

For our Python backend (no UI), we track the metadata that the UI layer
WOULD use for collapse, but messages pass through unchanged. The tracked
data feeds into logging and the compaction telemetry event.

Ponytail: message-pass-through only. The 1109-line original
(collapseReadSearch.ts) is 95% UI rendering logic — irrelevant here.
"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

COLLAPSIBLE_SEARCH = {"grep", "search", "rg", "ripgrep", "find_in_files"}
COLLAPSIBLE_READ = {"read", "read_file", "cat", "head", "tail"}
COLLAPSIBLE_LIST = {"ls", "list_files", "find_files", "tree", "dir"}
COLLAPSIBLE_SHELL = {"shell", "bash", "exec", "execute"}

COMMIT_SHA_RE = re.compile(r"(?:commit|hash)\s+([0-9a-f]{7,40})", re.IGNORECASE)
PR_URL_RE = re.compile(r"(?:pull|pr)/(\d+)", re.IGNORECASE)
BRANCH_RE = re.compile(r"(?:branch|ref)\s+(\S+)", re.IGNORECASE)


class CollapseReadSearchManager:
    def __init__(self):
        self._tracked = 0

    def collapse(self, messages: list[dict]) -> list[dict]:
        """Pass through — do NOT modify messages. UI-only in Claude Code.

        Returns messages unchanged. Populates display metadata for logging.
        """
        groups: list[dict] = []
        current: dict | None = None
        pending_ids: set[str] = set()

        for msg in messages:
            role = msg.get("role", "")
            name = (msg.get("name", "") or "").lower()
            content = msg.get("content", "")

            tool_calls = msg.get("tool_calls") or []
            tool_call = tool_calls[0] if tool_calls else {}
            fn_name = (
                tool_call.get("function", {}).get("name", "").lower()
                if tool_call
                else ""
            )

            collapsible = fn_name in COLLAPSIBLE_SEARCH | COLLAPSIBLE_READ | COLLAPSIBLE_LIST | COLLAPSIBLE_SHELL
            if role == "assistant" and collapsible:
                if current is None:
                    current = {"search": 0, "read": 0, "list": 0, "shell": 0,
                               "files": set(), "patterns": [], "commits": [],
                               "prs": [], "branches": []}
                try:
                    inp = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
                except json.JSONDecodeError:
                    inp = {}
                tid = tool_call.get("id", "")
                if tid:
                    pending_ids.add(tid)
                if fn_name in COLLAPSIBLE_SEARCH:
                    current["search"] += 1
                    p = inp.get("pattern") or inp.get("query")
                    if p:
                        current["patterns"].append(p)
                elif fn_name in COLLAPSIBLE_READ:
                    fp = inp.get("file_path") or inp.get("path")
                    if fp:
                        current["files"].add(fp)
                    current["read"] += 1
                elif fn_name in COLLAPSIBLE_LIST:
                    current["list"] += 1
                elif fn_name in COLLAPSIBLE_SHELL:
                    current["shell"] += 1
                continue

            if role == "tool" and pending_ids:
                tid = msg.get("tool_call_id", "")
                if tid in pending_ids:
                    pending_ids.discard(tid)
                    if current is not None and isinstance(content, str):
                        for sha_m in COMMIT_SHA_RE.finditer(content):
                            s = sha_m.group(1)
                            if not any(c["sha"] == s for c in current["commits"]):
                                current["commits"].append({"sha": s, "kind": "commit"})
                        for pr_m in PR_URL_RE.finditer(content):
                            n = int(pr_m.group(1))
                            if not any(p["number"] == n for p in current["prs"]):
                                current["prs"].append({"number": n, "kind": "pr"})
                        for b_m in BRANCH_RE.finditer(content):
                            b = b_m.group(1)
                            if b not in current["branches"]:
                                current["branches"].append(b)
                    continue

            if current is not None:
                groups.append(self._summarize(current))
                current = None
            pending_ids.clear()

        if current is not None:
            groups.append(self._summarize(current))

        if groups:
            self._tracked += sum(g["count"] for g in groups)
            logger.debug("L1b: tracked %d collapsible groups via metadata", len(groups))

        return messages

    def _summarize(self, g: dict) -> dict:
        parts = []
        if g["search"]:
            parts.append(f"searched {g['search']} patterns")
        if g["read"]:
            parts.append(f"read {g['read']} files")
        if g["list"]:
            parts.append(f"listed {g['list']} dirs")
        if g["shell"]:
            parts.append(f"ran {g['shell']} commands")
        if g["commits"]:
            parts.append(f"commits: {', '.join(c['sha'][:7] for c in g['commits'][:3])}")
        if g["prs"]:
            parts.append(f"PRs: #{', #'.join(str(p['number']) for p in g['prs'][:3])}")
        hint = ""
        if g["patterns"]:
            hint = g["patterns"][-1]
        elif g["files"]:
            hint = list(g["files"])[-1]
        return {
            "type": "collapse_group",
            "summary": "; ".join(parts) if parts else "multiple operations",
            "count": g["search"] + g["read"] + g["list"] + g["shell"],
            "files": list(g["files"]),
            "patterns": g["patterns"],
            "hint": hint,
        }

    def get_stats(self) -> dict:
        return {"groups_tracked": self._tracked}
