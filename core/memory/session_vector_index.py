"""Session Vector Index — 历史会话语义搜索（复用 ChromaDB）"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class SessionVectorIndex:
    def __init__(self):
        self._vm = None

    def _ensure(self):
        if self._vm is not None:
            return
        try:
            from core.memory.vector_memory import VectorMemoryStore
            self._vm = VectorMemoryStore()
            self._vm.wait_for_collection(timeout=3.0)
        except Exception as e:
            logger.debug(f"VectorMemoryStore init failed: {e}")

    def add_session(self, session_id: str, summary: str, task: str):
        self._ensure()
        if not self._vm:
            return
        try:
            content = f"[会话] {task}\n{summary[:1000]}"
            self._vm.add_memory(
                content=content,
                user_id="cli_user",
                category="experience",
                metadata={"session_id": session_id, "source": "session_artifact", "type": "session"},
            )
        except Exception as e:
            logger.debug(f"Session index add failed: {e}")

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        self._ensure()
        if not self._vm:
            return []
        try:
            memories = self._vm.search_memories(
                query=query, user_id="cli_user", top_k=top_k,
            )
            return [
                {"session_id": m.get("metadata", {}).get("session_id", ""),
                 "content": m.get("content", "")[:300]}
                for m in memories
                if m.get("content") and m.get("metadata", {}).get("source") == "session_artifact"
            ]
        except Exception as e:
            logger.debug(f"Session search failed: {e}")
            return []


def get_session_index() -> SessionVectorIndex:
    return SessionVectorIndex()
