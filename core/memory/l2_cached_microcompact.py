"""L2: CachedMicrocompact — generate cache edit instructions, do NOT modify messages.

In Claude Code, CachedMicrocompact (cache_compact_20250129) scans messages to
find optimal cache breakpoints and generates pendingCacheEdits for the API layer.
It does NOT modify local messages — the edits are sent alongside the next API
request so the server sets cache_control breakpoints on selected content blocks.

For our Python backend without Anthropic's server-side caching, we compute
the same breakpoint metadata and store it. The API client layer (call_model)
reads it when constructing the API payload.

Ponytail: metadata-only. If the LLM backend doesn't support cache breakpoints,
this layer becomes a no-op that still runs for telemetry.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# System prompt + tools prefix should always be cached
CACHE_SYSTEM_PREFIX = True
# Cache the compaction boundary if present
CACHE_BOUNDARY = True
# Max cache breakpoints per request
MAX_BREAKPOINTS = 4


class CachedMicrocompactConfig:
    """Read-only config that mirrors what autoCompact reads from feature flags.

    Ponytail: flat namespace, no feature-flag infra. Flip booleans directly.
    """
    def __init__(
        self,
        enabled: bool = True,
        max_breakpoints: int = MAX_BREAKPOINTS,
        cache_boundary: bool = CACHE_BOUNDARY,
        min_cache_savings_tokens: int = 1000,
    ):
        self.enabled = enabled
        self.max_breakpoints = max_breakpoints
        self.cache_boundary = cache_boundary
        self.min_cache_savings_tokens = min_cache_savings_tokens


class L2CachedMicrocompact:
    """Scans messages and emits cache edit metadata.

    In Claude Code this sends pendingCacheEdits to the API. Here we attach
    _cache_edits metadata to messages so the API client can apply them.
    """
    def __init__(self, config: CachedMicrocompactConfig | None = None):
        self.config = config or CachedMicrocompactConfig()
        self._scans = 0
        self._edits_generated = 0

    def scan(self, messages: list[dict]) -> list[dict]:
        """Scan messages for cache breakpoint opportunities.

        Does NOT modify message content. Returns the same list with
        _cache_edits metadata attached to eligible messages.
        """
        if not self.config.enabled or len(messages) < 2:
            return messages

        edits = []
        remaining = self.config.max_breakpoints

        # 1. System prompt (always cache if present)
        if remaining > 0 and messages and messages[0].get("role") == "system":
            msg = messages[0]
            msg["_cache_control"] = {"type": "ephemeral"}
            edits.append({"index": 0, "type": "ephemeral", "target": "system"})
            remaining -= 1

        # 2. Compaction boundary (system message with compact metadata)
        if remaining > 0 and self.config.cache_boundary:
            for i, msg in enumerate(messages):
                if msg.get("role") == "system" and msg.get("compact_metadata"):
                    existing = any(e["index"] == i for e in edits)
                    if not existing:
                        msg["_cache_control"] = {"type": "ephemeral"}
                        edits.append({"index": i, "type": "ephemeral", "target": "boundary"})
                        remaining -= 1
                        break

        # 3. Recent tool result with content (largest first, up to remaining)
        candidates = []
        for i, msg in enumerate(messages):
            if msg.get("role") == "tool" and isinstance(msg.get("content"), str):
                tokens = len(msg["content"]) // 4
                if tokens >= self.config.min_cache_savings_tokens:
                    existing = any(e["index"] == i for e in edits)
                    if not existing:
                        candidates.append((i, tokens))
        candidates.sort(key=lambda x: -x[1])

        for idx, _ in candidates[:remaining]:
            msg = messages[idx]
            msg["_cache_control"] = {"type": "ephemeral"}
            edits.append({"index": idx, "type": "ephemeral", "target": "tool_result"})
            remaining -= 1

        if edits:
            self._scans += 1
            self._edits_generated += len(edits)
            messages[0]["_cache_edits"] = edits
            logger.debug("L2: generated %d cache edits", len(edits))

        return messages

    def get_stats(self) -> dict:
        return {
            "scans": self._scans,
            "edits_generated": self._edits_generated,
            "enabled": self.config.enabled,
        }
