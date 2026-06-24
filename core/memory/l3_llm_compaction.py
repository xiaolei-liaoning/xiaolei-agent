"""L3: LLM Compaction — compactConversation() summary generation.

Mirrors Claude Code's compactConversation() core (~1308 lines):
1. Pre-compact hooks (custom instructions merge)
2. Fork agent / direct LLM call with NO_TOOLS_PREAMBLE + 9-section prompt
3. PTL retry loop: truncateHeadForPTLRetry on PROMPT_TOO_LONG (max 3 retries)
4. Format summary: strip <analysis> scratchpad, keep <summary>
5. Post-compact hooks
6. Build compaction result (boundary marker + summary + messagesToKeep)

Does NOT generate attachments — that's L4's job. Returns a CompactionResult
dict that L4 consumes.

Ponytail: single-threaded LLM call instead of forked agent with cache sharing
(the fork path exists for Anthropic's prompt caching — irrelevant here).
PTL retry loop and <analysis>/<summary> format kept 1:1 from source.
"""

import logging
import re
import time
from typing import Any

from core.memory.compact_prompt import (
    get_compact_prompt,
    get_partial_compact_prompt,
    format_compact_summary,
    get_compact_user_summary_message,
)

logger = logging.getLogger(__name__)

PROMPT_TOO_LONG_MARKER = "prompt_too_long"
MAX_PTL_RETRIES = 3
ERROR_MESSAGE_NOT_ENOUGH_MESSAGES = "Not enough messages to compact"
ERROR_MESSAGE_PROMPT_TOO_LONG = "Prompt too long for compaction"
ERROR_MESSAGE_INCOMPLETE_RESPONSE = "Incomplete response from LLM"


class L3LLMCompaction:
    """LLM-driven conversation compaction with PTL retry.

    Mirrors compactConversation() — the core of Claude Code's compaction.
    Calls an LLM with the 9-section <analysis>+<summary> prompt, retries on
    prompt-too-long, and returns a structured CompactionResult.
    """

    def __init__(
        self,
        model_limit: int = 8000,
        compact_threshold: float = 0.7,
        force_threshold: float = 0.85,
    ):
        self.model_limit = model_limit
        self.compact_threshold = compact_threshold
        self.force_threshold = force_threshold
        self._compactions = 0
        self._ptl_retries = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    def should_compact(self, token_count: int, force: bool = False) -> bool:
        usage = token_count / self.model_limit
        return usage > self.compact_threshold or force

    def compact(
        self,
        messages: list[dict],
        force: bool = False,
        compact_type: str = "base",
        custom_instructions: str | None = None,
    ) -> dict:
        """Generate compaction summary from messages.

        Args:
            messages: Full message list.
            force: Skip threshold check.
            compact_type: "base" (full summary) or "partial" (recent only).
            custom_instructions: Optional user/hook-supplied instructions.

        Returns:
            CompactionResult dict:
                boundary_marker: system message with compact metadata
                summary_messages: list of user message(s) with summary text
                messages_to_keep: recent messages preserved verbatim
                pre_compact_token_count: int
                post_compact_token_count: int
                summary_text: raw formatted summary string
        """
        from core.memory.token_counter import count_messages_tokens

        total_tokens = count_messages_tokens(messages)
        if not self.should_compact(total_tokens, force):
            return {"skipped": True, "messages": messages}

        if len(messages) == 0:
            raise ValueError(ERROR_MESSAGE_NOT_ENOUGH_MESSAGES)

        self._total_input_tokens += total_tokens

        # 1. Pre-compact: build prompt with custom instructions
        prompt = get_compact_prompt(custom_instructions)
        if compact_type == "partial":
            prompt = get_partial_compact_prompt(custom_instructions)

        # 2. Fork agent / LLM call with PTL retry loop
        messages_to_summarize = list(messages)
        ptl_attempts = 0
        summary_text: str | None = None

        while True:
            summary_text = self._call_llm_for_summary(messages_to_summarize, prompt)
            if summary_text and not summary_text.startswith(PROMPT_TOO_LONG_MARKER):
                break

            ptl_attempts += 1
            if ptl_attempts > MAX_PTL_RETRIES:
                logger.error(
                    "L3: PTL retry exhausted after %d attempts", ptl_attempts
                )
                raise ValueError(ERROR_MESSAGE_PROMPT_TOO_LONG)

            truncated = self._truncate_head_for_ptl_retry(
                messages_to_summarize, summary_text
            )
            if not truncated:
                raise ValueError(ERROR_MESSAGE_PROMPT_TOO_LONG)

            self._ptl_retries += 1
            logger.warning(
                "L3: PTL retry %d/%d, dropped %d messages",
                ptl_attempts, MAX_PTL_RETRIES,
                len(messages_to_summarize) - len(truncated),
            )
            messages_to_summarize = truncated

        if not summary_text:
            raise ValueError(ERROR_MESSAGE_INCOMPLETE_RESPONSE)

        # 3. Format summary: strip <analysis>, keep <summary>
        formatted = format_compact_summary(summary_text)

        # 4. Build compaction result
        boundary_marker = self._create_boundary_marker(messages, total_tokens)
        summary_msgs = self._create_summary_messages(formatted)

        # Keep last few turns verbatim
        messages_to_keep = messages[-6:] if len(messages) >= 6 else messages[-min(len(messages), 4):]

        post_compact_tokens = count_messages_tokens(
            [boundary_marker] + summary_msgs + messages_to_keep
        )
        self._total_output_tokens += post_compact_tokens
        self._compactions += 1

        logger.info(
            "L3: compacted %d → ~%d tokens (saved %d)",
            total_tokens, post_compact_tokens, total_tokens - post_compact_tokens,
        )

        return {
            "boundary_marker": boundary_marker,
            "summary_messages": summary_msgs,
            "messages_to_keep": messages_to_keep,
            "pre_compact_token_count": total_tokens,
            "post_compact_token_count": post_compact_tokens,
            "summary_text": formatted,
        }

    def _call_llm_for_summary(self, messages: list[dict], prompt: str) -> str | None:
        """Direct LLM call with the compaction prompt.

        In Claude Code this goes through streamCompactSummary() which tries
        forked-agent-with-cache-sharing first, then falls back to streaming.
        Our Python backend does a single chat completion.
        """
        try:
            from core.engine.llm_backend import get_llm_router
            router = get_llm_router()

            # Format messages for the LLM
            formatted = self._format_for_llm(messages)

            import asyncio
            async def _call():
                return await router.chat(
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": formatted},
                    ],
                    temperature=0.1,
                    max_tokens=2000,
                )

            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(lambda: asyncio.run(_call())).result(timeout=30)
            else:
                result = loop.run_until_complete(_call())

            return result
        except Exception as e:
            logger.warning("L3: LLM call failed: %s", e)
            return self._template_summary(messages)

    def _format_for_llm(self, messages: list[dict]) -> str:
        lines = []
        for m in messages:
            role = m.get("role", "?")
            content = m.get("content", "")
            if isinstance(content, str):
                if len(content) > 500:
                    content = content[:500] + f"... ({len(content)} chars total)"
                lines.append(f"[{role}]: {content}")
            elif isinstance(content, list):
                txt_parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                full = " ".join(txt_parts)
                if len(full) > 500:
                    full = full[:500] + "..."
                lines.append(f"[{role}]: {full}" if full else f"[{role}]: (structured, {len(content)} blocks)")
        return "\n".join(lines)

    def _template_summary(self, messages: list[dict]) -> str:
        user_msgs = [m for m in messages if m.get("role") == "user"]
        return (
            "<analysis>Template fallback — LLM unavailable</analysis>\n\n"
            "<summary>\n"
            "1. Primary Request and Intent:\n"
            f"   {user_msgs[-1].get('content', 'unknown')[:200] if user_msgs else 'N/A'}\n\n"
            "2. Key Technical Concepts:\n"
            "   [LLM unavailable — template summary]\n\n"
            "3. Files and Code Sections:\n"
            f"   {len(messages)} messages total\n\n"
            "4. Errors and fixes:\n"
            "   [LLM unavailable]\n\n"
            "5. Problem Solving:\n"
            "   [LLM unavailable]\n\n"
            "6. All user messages:\n"
            f"   {len(user_msgs)} user messages\n\n"
            "7. Pending Tasks:\n"
            "   [LLM unavailable]\n\n"
            "8. Current Work:\n"
            f"   Last user: {user_msgs[-1].get('content', '')[:100] if user_msgs else 'N/A'}\n\n"
            "9. Optional Next Step:\n"
            "   [LLM unavailable]\n"
            "</summary>"
        )

    def _truncate_head_for_ptl_retry(
        self, messages: list[dict], summary_text: str | None = None
    ) -> list[dict] | None:
        """Drop oldest API-round groups on prompt-too-long.

        Mirrors truncateHeadForPTLRetry() from compact.ts.
        """
        if len(messages) < 3:
            return None

        drop_count = max(1, len(messages) // 5)
        system_prompt = messages[0] if messages and messages[0].get("role") == "system" else None
        start = 1 if system_prompt else 0
        truncated = messages[:start] + messages[start + drop_count:]
        return truncated if len(truncated) >= 2 else None

    def _create_boundary_marker(self, messages: list[dict], pre_compact_tokens: int) -> dict:
        last_uuid = None
        for m in reversed(messages):
            if m.get("uuid"):
                last_uuid = m["uuid"]
                break
        return {
            "role": "system",
            "content": (
                "[System notice: Due to context length, this conversation has been "
                "automatically compacted. The summary below covers the earlier portion.]"
            ),
            "compact_metadata": {
                "type": "auto",
                "pre_compact_token_count": pre_compact_tokens,
                "created_at": time.time(),
            },
        }

    def _create_summary_messages(self, summary_text: str) -> list[dict]:
        msg_text = get_compact_user_summary_message(summary_text)
        return [
            {
                "role": "user",
                "content": msg_text,
                "is_compact_summary": True,
            }
        ]

    def get_stats(self) -> dict:
        return {
            "compactions": self._compactions,
            "ptl_retries": self._ptl_retries,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
        }
