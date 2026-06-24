"""Unified conversation history manager — storage + compression + vector memory.

Combines:
- Short-term: In-memory per-user conversation history
- Long-term: ChromaDB vector memory with Chinese embedding (BGE)
- Compression: 7-layer compaction (Claude Code architecture) when history exceeds threshold
"""

import logging
import time
from typing import List, Dict, Any, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class ConversationHistory:
    """Unified conversation history manager with vector memory.

    Stores messages per user and automatically:
    1. Compresses when history exceeds threshold (5-layer compaction)
    2. Stores important messages in vector memory (long-term recall)
    3. Retrieves relevant memories for context enrichment
    """

    def __init__(
        self,
        max_messages: int = 100,
        compress_threshold: int = 20,
        model_limit: int = 8000,
        vector_memory_enabled: bool = True,
    ):
        self.max_messages = max_messages
        self.compress_threshold = compress_threshold
        self.model_limit = model_limit
        self.vector_memory_enabled = vector_memory_enabled

        # Per-user storage: {user_id: [messages]}
        self._store: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        self._last_activity: Dict[int, float] = {}

        # Vector memory (lazy init)
        self._vector_store = None

    def _get_vector_store(self):
        """Lazy init vector memory store."""
        if self._vector_store is None and self.vector_memory_enabled:
            try:
                from core.memory.vector_memory import VectorMemoryStore
                self._vector_store = VectorMemoryStore()
            except Exception as e:
                logger.warning("Vector memory init failed: %s", e)
                self._vector_store = False  # Mark as failed
        return self._vector_store if self._vector_store is not False else None

    def add_message(
        self,
        user_id: int,
        role: str,
        content: str,
        **kwargs,
    ) -> None:
        """Add a message to user's history.

        Args:
            user_id: User ID.
            role: Message role (user/assistant/system).
            content: Message content.
            **kwargs: Additional fields (tool_calls, name, etc.).
        """
        msg = {"role": role, "content": content, **kwargs}
        self._store[user_id].append(msg)
        self._last_activity[user_id] = time.time()

        # Store in vector memory for long-term recall
        self._store_in_vector(user_id, role, content)

        # Auto-compress if history exceeds threshold
        if len(self._store[user_id]) > self.compress_threshold:
            self._compress(user_id)

        # Trim if exceeds max
        if len(self._store[user_id]) > self.max_messages:
            self._store[user_id] = self._store[user_id][-self.max_messages:]

    def _store_in_vector(self, user_id: int, role: str, content: str) -> None:
        """Store message in vector memory for long-term recall."""
        vector_store = self._get_vector_store()
        if not vector_store:
            return

        try:
            # Only store user and assistant messages (not system)
            if role not in ("user", "assistant"):
                return

            # Skip very short messages
            if len(content) < 10:
                return

            # Determine category based on content
            category = self._categorize_message(content)

            # Store with metadata
            vector_store.add_memory(
                user_id=user_id,
                content=content,
                category=category,
                metadata={
                    "role": role,
                    "timestamp": time.time(),
                    "source": "conversation",
                },
            )
        except Exception as e:
            logger.debug("Vector store failed (non-critical): %s", e)

    def _categorize_message(self, content: str) -> str:
        """Categorize message for vector storage."""
        content_lower = content.lower()

        # Check for preferences
        if any(w in content_lower for w in ["喜欢", "偏好", "prefer", "like"]):
            return "preference"

        # Check for facts
        if any(w in content_lower for w in ["是", "位于", "地址", "电话", "is", "located"]):
            return "fact"

        # Check for experiences
        if any(w in content_lower for w in ["做过", "完成", "经验", "done", "completed"]):
            return "experience"

        return "general"

    def get_history(
        self,
        user_id: int,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get conversation history for a user.

        Args:
            user_id: User ID.
            limit: Maximum messages to return (default: all).

        Returns:
            List of message dicts.
        """
        history = self._store.get(user_id, [])
        if limit:
            return history[-limit:]
        return history

    def get_relevant_memories(
        self,
        user_id: int,
        query: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Get relevant memories from vector store.

        Args:
            user_id: User ID.
            query: Search query.
            top_k: Number of results.

        Returns:
            List of relevant memories.
        """
        vector_store = self._get_vector_store()
        if not vector_store:
            return []

        try:
            memories = vector_store.search_memories(
                query=query,
                user_id=user_id,
                top_k=top_k,
            )
            return memories
        except Exception as e:
            logger.debug("Vector search failed: %s", e)
            return []

    def get_context_info(self, user_id: int) -> Dict[str, Any]:
        """Get context info for API response.

        Returns:
            Dict with context metadata and compaction stats.
        """
        history = self._store.get(user_id, [])
        last_activity = self._last_activity.get(user_id)

        # Get vector memory stats
        vector_store = self._get_vector_store()
        vector_count = 0
        if vector_store:
            try:
                vector_count = vector_store.count()
            except Exception:
                pass

        return {
            "has_context": len(history) > 0,
            "message_count": len(history),
            "recent_messages": [
                {"role": m["role"], "content": str(m.get("content", ""))[:100]}
                for m in history[-5:]
            ],
            "last_activity": last_activity,
            "vector_memory_count": vector_count,
        }

    def _compress(self, user_id: int) -> None:
        """Compress user's history using 7-layer compaction."""
        history = self._store.get(user_id, [])
        if len(history) <= self.compress_threshold:
            return

        try:
            from core.memory.context_compactor import get_compactor
            compactor = get_compactor(model_limit=self.model_limit)

            # Update timestamp for time-based MC (L1c)
            compactor.update_assistant_timestamp()

            # Run 7-layer compaction
            compressed = compactor.compact(history)

            # Replace history with compressed version
            self._store[user_id] = compressed

            stats = compactor.get_compaction_stats()
            logger.info(
                "Compressed user %d: %d → %d messages (saved %d tokens)",
                user_id,
                len(history),
                len(compressed),
                stats["total_tokens_saved"],
            )

        except Exception as e:
            logger.warning("Compression failed for user %d: %s", user_id, e)

    def clear(self, user_id: int) -> None:
        """Clear user's history."""
        self._store.pop(user_id, None)
        self._last_activity.pop(user_id, None)

    def get_stats(self) -> Dict[str, Any]:
        """Get global statistics."""
        vector_store = self._get_vector_store()
        vector_count = 0
        if vector_store:
            try:
                vector_count = vector_store.count()
            except Exception:
                pass

        return {
            "total_users": len(self._store),
            "total_messages": sum(len(v) for v in self._store.values()),
            "avg_messages_per_user": (
                sum(len(v) for v in self._store.values()) / len(self._store)
                if self._store else 0
            ),
            "vector_memory_count": vector_count,
        }


# Global instance
_history: Optional[ConversationHistory] = None


def get_history_manager(
    max_messages: int = 100,
    compress_threshold: int = 20,
    model_limit: int = 8000,
    vector_memory_enabled: bool = True,
) -> ConversationHistory:
    """Get or create the global conversation history manager."""
    global _history
    if _history is None:
        _history = ConversationHistory(
            max_messages=max_messages,
            compress_threshold=compress_threshold,
            model_limit=model_limit,
            vector_memory_enabled=vector_memory_enabled,
        )
    return _history
