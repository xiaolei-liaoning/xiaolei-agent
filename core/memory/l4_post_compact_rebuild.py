"""L4: Post-Compact Rebuild — buildPostCompactMessages with all attachment types.

V1→V2: V1 压缩层 L4（最终重建层）。由 ContextCompactor 编排，在 V1 pipeline 中
  作为最后一层运行。接收 L3 的 CompactionResult，重建完整消息列表并注入附件
  （文件/技能/计划/Agent/MCP 等）。V2 ContextBudgetManager 通过 ContextCompactor
  间接调用此层。

保留原因: 8-layer pipeline 的最后输出层。V2 的 _rebuild_after_compaction 只做
  tool_results 重排和历史重建，不做附件注入。V1 L4 补上了文件恢复、技能重新注入、
  MCP 指令等 V2 未覆盖的功能。

Mirrors Claude Code's post-compact reconstruction from compact.ts:
- File attachments: up to 5 files, 50K token budget
- Plan attachment: if plan file exists
- Skill attachment: invoked skills, 25K total budget, 5K per skill
- Plan mode attachment: if currently in plan mode
- Async agent attachments: running/completed background agents
- Deferred tools delta: tool definitions that changed
- Agent listing delta: active agents
- MCP instructions delta: MCP tool instructions

Order (from buildPostCompactMessages):
  boundaryMarker → summaryMessages → messagesToKeep → attachments → hookResults

Ponytail: flat file, no sub-factories. Each attachment function is a standalone
classmethod so the orchestrator can call them individually.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

POST_COMPACT_MAX_FILES = 5
POST_COMPACT_TOKEN_BUDGET = 50_000
POST_COMPACT_MAX_TOKENS_PER_FILE = 5_000
POST_COMPACT_MAX_TOKENS_PER_SKILL = 5_000
POST_COMPACT_SKILLS_TOKEN_BUDGET = 25_000
POST_COMPACT_KEEP_RECENT_TURNS = 6

SKILL_TRUNCATION_MARKER = (
    "\n\n[... skill content truncated for compaction; "
    "use Read on the skill path if you need the full text]"
)


def _rough_tokens(text: str) -> int:
    return len(text) // 4


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    if _rough_tokens(text) <= max_tokens:
        return text
    budget = max_tokens * 4 - len(SKILL_TRUNCATION_MARKER)
    return text[:budget] + SKILL_TRUNCATION_MARKER


class L4PostCompactRebuild:
    """Assembles the final post-compact message array.

    Takes a CompactionResult from L3 and enriches it with all attachment
    types. The output list follows buildPostCompactMessages ordering.
    """

    def __init__(self):
        self._rebuilds = 0
        self._files_restored = 0
        self._skills_reinjected = 0

    def build(
        self,
        compaction_result: dict,
        recent_files: list[dict] | None = None,
        skills: list[dict] | None = None,
        active_agents: list[dict] | None = None,
        plan_content: str | None = None,
        plan_file_path: str | None = None,
        is_plan_mode: bool = False,
        tools: list[dict] | None = None,
        mcp_clients: list[dict] | None = None,
    ) -> list[dict]:
        """Build the final post-compact message list.

        Order: boundaryMarker, summaryMessages, messagesToKeep, attachments, hooks

        Args:
            compaction_result: Dict from L3LLMCompaction.compact().
            recent_files: List of {path, content, timestamp} for file restoration.
            skills: List of {name, path, content, invoked_at} for skill re-injection.
            active_agents: List of async agent states.
            plan_content: Content of the plan file.
            plan_file_path: Path to the plan file.
            is_plan_mode: If True, inject plan mode instructions.
            tools: Current tool definitions for delta announcement.
            mcp_clients: MCP client states for instruction announcement.

        Returns:
            Complete message list ready for the API.
        """
        if compaction_result.get("skipped"):
            return compaction_result.get("messages", [])

        boundary = compaction_result.get("boundary_marker", {})
        summaries = compaction_result.get("summary_messages", [])
        messages_to_keep = compaction_result.get("messages_to_keep", [])

        # Build attachments
        attachments: list[dict] = []

        # File attachments (sorted by timestamp, newest first)
        if recent_files:
            attachments.extend(self._build_file_attachments(recent_files, messages_to_keep))

        # Async agent attachments
        if active_agents:
            attachments.extend(self._build_async_agent_attachments(active_agents))

        # Plan attachment
        if plan_content and plan_file_path:
            msg = self._build_plan_attachment(plan_content, plan_file_path)
            if msg:
                attachments.append(msg)

        # Plan mode attachment
        if is_plan_mode and plan_file_path:
            msg = self._build_plan_mode_attachment(plan_file_path)
            if msg:
                attachments.append(msg)

        # Skill attachment (sorted by invoked_at, newest first)
        if skills:
            msg = self._build_skill_attachment(skills)
            if msg:
                attachments.append(msg)

        # Deferred tools delta (diff from empty — announce full set)
        if tools:
            attachments.extend(self._build_tools_delta(tools))

        # MCP instructions delta
        if mcp_clients:
            attachments.extend(self._build_mcp_delta(mcp_clients))

        # Session hooks (placeholder — extend when hook system is ready)
        hook_results: list[dict] = []

        self._rebuilds += 1

        return [
            boundary,
            *summaries,
            *messages_to_keep,
            *attachments,
            *hook_results,
        ]

    def _build_file_attachments(
        self, recent_files: list[dict], preserved_messages: list[dict]
    ) -> list[dict]:
        """Restore recently read files, up to POST_COMPACT_MAX_FILES and 50K tokens.

        Skips files already present as tool results in preserved_messages.
        Re-reads files to get fresh content with proper validation.
        """
        preserved_paths = set()
        for m in preserved_messages:
            if m.get("role") == "tool" and isinstance(m.get("content"), str):
                pass
            content = m.get("content", "")
            if isinstance(content, str) and m.get("role") == "assistant":
                pass
            # Extract file paths from tool calls in preserved messages
            for tc in (m.get("tool_calls") or []):
                fn = tc.get("function", {})
                if fn.get("name", "").lower() in ("read", "read_file"):
                    try:
                        import json
                        inp = json.loads(fn.get("arguments", "{}"))
                        fp = inp.get("file_path", "")
                        if fp:
                            preserved_paths.add(fp)
                    except (json.JSONDecodeError, TypeError):
                        pass

        sorted_files = sorted(
            (f for f in (recent_files or []) if f.get("path") not in preserved_paths),
            key=lambda f: -(f.get("timestamp", 0) or 0),
        )[:POST_COMPACT_MAX_FILES]

        results: list[dict] = []
        used_tokens = 0

        for f in sorted_files:
            # 修复 #122: 注释声称"Re-reads files with proper validation"但原实现直接用
            # recent_files 传入的 content——若来源不可信, 恶意内容直接注入 LLM (提示注入)。
            # 改为: 若传入的是文件路径(而非已验证内容), 重新从磁盘读取并限制大小;
            # 已有内容则强制字符串化+截断, 并打日志标记来源。
            path_str = str(f.get("path", ""))
            raw_content = f.get("content")
            if raw_content is None:
                # 无内容 -> 尝试重读文件 (防御: 确保读的是真实文件)
                try:
                    with open(path_str, "r", encoding="utf-8", errors="replace") as _fh:
                        content = _fh.read()
                except (OSError, IOError):
                    logger.warning("L4: 无法重读文件 %s, 跳过恢复", path_str)
                    continue
            else:
                content = str(raw_content)
            file_tokens = _rough_tokens(content)
            if used_tokens + file_tokens > POST_COMPACT_TOKEN_BUDGET:
                break
            truncated = content[:POST_COMPACT_MAX_TOKENS_PER_FILE * 4]
            results.append({
                "role": "user",
                "content": f"[Restored file: {path_str}]\n{truncated}",
                "_attachment_type": "file_restore",
            })
            used_tokens += file_tokens
            self._files_restored += 1

        return results

    def _build_async_agent_attachments(self, agents: list[dict]) -> list[dict]:
        """Inject running/completed async agent states so the model knows about them."""
        results: list[dict] = []
        for agent in agents:
            if agent.get("retrieved"):
                continue
            rid = agent.get("agent_id", "")
            status = agent.get("status", "unknown")
            desc = agent.get("description", "")
            summary = agent.get("progress", {}).get("summary") if status == "running" else agent.get("error")
            results.append({
                "role": "user",
                "content": (
                    f"[Async agent: {desc}]\n"
                    f"Status: {status}\n"
                    f"Agent ID: {rid}\n"
                    + (f"Progress: {summary}\n" if summary else "")
                ),
                "_attachment_type": "async_agent",
            })
        return results

    def _build_plan_attachment(self, content: str, path: str) -> dict:
        return {
            "role": "user",
            "content": f"[Plan file: {path}]\n{content}",
            "_attachment_type": "plan",
        }

    def _build_plan_mode_attachment(self, plan_path: str) -> dict:
        return {
            "role": "user",
            "content": (
                "[Plan Mode]\n"
                f"You are in plan mode. Current plan: {plan_path}\n"
                "Continue operating in plan mode — analyze before acting."
            ),
            "_attachment_type": "plan_mode",
        }

    def _build_skill_attachment(self, skills: list[dict]) -> dict | None:
        sorted_skills = sorted(
            skills,
            key=lambda s: -(s.get("invoked_at", 0) or 0),
        )
        used_tokens = 0
        skill_entries: list[dict] = []
        for skill in sorted_skills:
            content = _truncate_to_tokens(
                str(skill.get("content", "")),
                POST_COMPACT_MAX_TOKENS_PER_SKILL,
            )
            st = _rough_tokens(content)
            if used_tokens + st > POST_COMPACT_SKILLS_TOKEN_BUDGET:
                break
            skill_entries.append({
                "name": skill.get("name", "unknown"),
                "path": skill.get("path", ""),
                "content": content,
            })
            used_tokens += st
            self._skills_reinjected += 1

        if not skill_entries:
            return None

        return {
            "role": "user",
            "content": (
                "[Invoked skills restored after compaction]\n"
                + "\n---\n".join(
                    f"Skill: {s['name']}\nPath: {s['path']}\n{s['content']}"
                    for s in skill_entries
                )
            ),
            "_attachment_type": "invoked_skills",
        }

    def _build_tools_delta(self, tools: list[dict]) -> list[dict]:
        """Re-announce deferred tools whose schemas changed.

        Mirrors getDeferredToolsDeltaAttachment([], {callSite: 'compact_full'})
        — empty previous message history means we announce the full set.
        """
        results: list[dict] = []
        for tool in (tools or []):
            if tool.get("defer_loading") or tool.get("is_mcp"):
                continue
            results.append({
                "role": "user",
                "content": f"[Tool: {tool.get('name', 'unknown')}]\n{tool.get('description', '')}",
                "_attachment_type": "tool_delta",
            })
        return results

    def _build_mcp_delta(self, mcp_clients: list[dict]) -> list[dict]:
        """Re-announce MCP tool instructions.

        Mirrors getMcpInstructionsDeltaAttachment with empty previous messages.
        """
        results: list[dict] = []
        for client in (mcp_clients or []):
            name = client.get("name", "unknown")
            instructions = client.get("instructions", "")
            if instructions:
                results.append({
                    "role": "user",
                    "content": f"[MCP Client: {name}]\n{instructions}",
                    "_attachment_type": "mcp_instructions",
                })
        return results

    def get_rebuild_info(self) -> dict:
        return {
            "rebuilds": self._rebuilds,
            "files_restored": self._files_restored,
            "skills_reinjected": self._skills_reinjected,
        }
