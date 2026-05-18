"""
Task snapshot persistence — lightweight, agent-disposable persistence.

Persists only:
1. Task state & context snapshots
2. Final results & key decision logs
3. ActionResult summaries per step

Agents are discarded after use; task can be rebuilt from snapshots.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default storage directory
SNAPSHOT_DIR = Path("data") / "task_snapshots"


class TaskSnapshotStore:
    """Stores and retrieves task snapshots as JSON files."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or SNAPSHOT_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._in_memory: Dict[str, dict] = {}

    # ─── Write ──────────────────────────────────────────────

    async def save(self, task_id: str, snapshot: dict) -> None:
        """Save a task snapshot (in-memory + file)."""
        snapshot["_updated_at"] = time.time()
        self._in_memory[task_id] = snapshot
        await self._flush_to_disk(task_id, snapshot)

    async def append_decision(self, task_id: str, decision: dict) -> None:
        """Append a decision log entry."""
        snap = self._in_memory.get(task_id)
        if snap is None:
            snap = await self.load(task_id) or {}
            self._in_memory[task_id] = snap
        decisions = snap.setdefault("decision_log", [])
        decisions.append({**decision, "timestamp": time.time()})
        await self._flush_to_disk(task_id, snap)

    async def update_status(self, task_id: str, status: str, extra: dict = None) -> None:
        """Update task status."""
        snap = self._in_memory.get(task_id)
        if snap is None:
            snap = await self.load(task_id) or {}
            self._in_memory[task_id] = snap
        snap["status"] = status
        if extra:
            snap.update(extra)
        await self._flush_to_disk(task_id, snap)

    # ─── Read ───────────────────────────────────────────────

    async def load(self, task_id: str) -> Optional[dict]:
        """Load a task snapshot (memory first, then disk)."""
        if task_id in self._in_memory:
            return self._in_memory[task_id]
        filepath = self._filepath(task_id)
        if filepath.exists():
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._in_memory[task_id] = data
                return data
            except Exception as e:
                logger.warning(f"Failed to load snapshot {task_id}: {e}")
        return None

    async def list_active(self) -> List[str]:
        """List task IDs that are not in a terminal state."""
        active = []
        for path in self.storage_dir.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("status") not in ("completed", "failed", "cancelled"):
                    active.append(data.get("task_id", path.stem))
            except Exception:
                pass
        return active

    # ─── Cleanup ────────────────────────────────────────────

    async def delete(self, task_id: str) -> None:
        """Delete a task snapshot."""
        self._in_memory.pop(task_id, None)
        filepath = self._filepath(task_id)
        if filepath.exists():
            filepath.unlink()

    async def clean_old(self, max_age_hours: int = 72) -> int:
        """Remove snapshots older than max_age_hours."""
        cutoff = time.time() - max_age_hours * 3600
        removed = 0
        for path in self.storage_dir.glob("*.json"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except Exception:
                pass
        return removed

    # ─── Internal ───────────────────────────────────────────

    def _filepath(self, task_id: str) -> Path:
        safe = task_id.replace("/", "_").replace("\\", "_")
        return self.storage_dir / f"{safe}.json"

    async def _flush_to_disk(self, task_id: str, data: dict) -> None:
        filepath = self._filepath(task_id)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Failed to write snapshot {task_id}: {e}")


# Global instance
_store: Optional[TaskSnapshotStore] = None


def get_snapshot_store() -> TaskSnapshotStore:
    global _store
    if _store is None:
        _store = TaskSnapshotStore()
    return _store
