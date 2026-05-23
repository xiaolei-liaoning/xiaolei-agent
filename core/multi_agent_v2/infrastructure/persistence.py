"""
Task snapshot persistence — lightweight, agent-disposable persistence.

Persists only:
1. Task state & context snapshots
2. Final results & key decision logs
3. ActionResult summaries per step

Agents are discarded after use; task can be rebuilt from snapshots.

Supports two backends:
- JSON files (default, lightweight)
- MySQL via SQLAlchemy (for production recovery)
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

_TERMINAL_STATES = {"completed", "failed", "cancelled"}


class TaskSnapshotStore:
    """Stores and retrieves task snapshots.

    Dual backend: JSON files by default + optional MySQL sync.
    """

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

    # ─── MySQL Sync (via SQLAlchemy) ─────────────────────────

    def sync_to_db(self, task_id: str, snapshot: dict) -> None:
        """Sync a snapshot to MySQL (upsert by task_id)."""
        try:
            from core.infrastructure.database import get_db_session, TaskContextSnapshot
            from datetime import datetime

            context_json = {
                "decision_log": snapshot.get("decision_log", []),
                "partial_results": snapshot.get("partial_results", {}),
                "assigned_agents": snapshot.get("assigned_agents", {}),
                "final_result": snapshot.get("final_result"),
                "metadata": snapshot.get("metadata", {}),
            }

            with get_db_session() as session:
                existing = session.query(TaskContextSnapshot).filter(
                    TaskContextSnapshot.task_id == task_id
                ).first()

                if existing:
                    existing.state = snapshot.get("status", "unknown")
                    existing.context_json = context_json
                    existing.updated_at = datetime.now()
                else:
                    record = TaskContextSnapshot(
                        task_id=task_id,
                        state=snapshot.get("status", "pending"),
                        original_request=snapshot.get("original_request", ""),
                        context_json=context_json,
                        agent_registry=snapshot.get("agent_registry"),
                        trace_id=snapshot.get("trace_id"),
                    )
                    session.add(record)
        except Exception as e:
            logger.debug(f"sync_to_db failed (non-fatal): {e}")

    def sync_delete_from_db(self, task_id: str) -> None:
        """Delete a snapshot from MySQL."""
        try:
            from core.infrastructure.database import get_db_session, TaskContextSnapshot

            with get_db_session() as session:
                session.query(TaskContextSnapshot).filter(
                    TaskContextSnapshot.task_id == task_id
                ).delete()
        except Exception as e:
            logger.debug(f"sync_delete_from_db failed (non-fatal): {e}")

    def restore_active_tasks(self) -> Dict[str, dict]:
        """Restore all non-terminal task snapshots from MySQL.

        Returns a dict of task_id → snapshot that can be loaded into
        GlobalContextCenter on startup.
        """
        result: Dict[str, dict] = {}
        try:
            from core.infrastructure.database import get_db_session, TaskContextSnapshot

            with get_db_session() as session:
                rows = session.query(TaskContextSnapshot).filter(
                    ~TaskContextSnapshot.state.in_(_TERMINAL_STATES)
                ).all()

            for row in rows:
                snapshot = {
                    "task_id": row.task_id,
                    "status": row.state,
                    "original_request": row.original_request,
                    "trace_id": row.trace_id,
                    **(row.context_json or {}),
                }
                if row.agent_registry:
                    snapshot["agent_registry"] = row.agent_registry
                self._in_memory[row.task_id] = snapshot
                result[row.task_id] = snapshot

            if result:
                logger.info(f"Restored {len(result)} active tasks from MySQL")
        except Exception as e:
            logger.debug(f"restore_active_tasks failed (non-fatal): {e}")
        return result


# Global instance
_store: Optional[TaskSnapshotStore] = None


def get_snapshot_store() -> TaskSnapshotStore:
    global _store
    if _store is None:
        _store = TaskSnapshotStore()
    return _store
