"""L1b: CollapseReadSearch — UI-only display metadata tracker.

V1→V2: V1 压缩层 L1b。由 ContextCompactor.compact() line 198 主动调用，
  纯消息透传（不修改内容），跟踪 UI 折叠元数据。

⚠️ 当前是 no-op（passthrough）：
  - V2 没 UI 层（React/CLI/TUI）所以折叠元数据没用
  - collapse() 直接 return messages，原样返回
  - 仍被 ContextCompactor.compact() 调用，因为删这一层要同时改 ContextCompactor

保留原因: ContextCompactor 8-layer pipeline 的组成部分。删前需先改
  ContextCompactor.compact() line 197-198（移除 self.l1b.collapse(messages)）。
  删完 ContextCompactor 调用后，本文件即可整个删除（156 行）。

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
from typing import Any

logger = logging.getLogger(__name__)

COLLAPSIBLE_SEARCH = {"grep", "search", "rg", "ripgrep", "find_in_files"}
COLLAPSIBLE_READ = {"read", "read_file", "cat", "head", "tail"}
COLLAPSIBLE_LIST = {"ls", "list_files", "find_files", "tree", "dir"}
COLLAPSIBLE_SHELL = {"shell", "bash", "exec", "execute"}


class CollapseReadSearchManager:
    def __init__(self):
        self._tracked = 0

    def collapse(self, messages: list[dict]) -> list[dict]:
        """Pass through — do NOT modify messages. UI-only in Claude Code.

        Returns messages unchanged. Populates display metadata for logging.

        修复 #120: 原实现用多个昂贵 regex (COMMIT_SHA_RE/PR_URL_RE/BRANCH_RE)
        在每条 tool 结果上做提取, 但 _tracked 仅用于 get_stats()/logging (telemetry),
        数值从未被注入消息。纯属浪费 CPU。降级为轻量——只统计分组, 不做 regex 提取。
        """
        groups: list[dict] = []
        current: dict | None = None

        for msg in messages:
            role = msg.get("role", "")
            name = (msg.get("name", "") or "").lower()
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
                               "files": set(), "patterns": []}
                try:
                    inp = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
                except json.JSONDecodeError:
                    inp = {}
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

            if current is not None:
                groups.append(self._summarize(current))
                current = None

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
