"""标准 Session 状态机 + SQLite 持久化层 — 借鉴 hermes-agent 三层设计 (gateway/session_state.py + session_lifecycle.py + session_persistence.py)。

设计核心 (对照 hermes-agent)：
  - TurnState        : 单回合状态，每回合清 (agent/started_ts/lease)
  - ConversationState: 跨回合状态，会话边界清 (model_override/reasoning_override/service_tier)
  - PersistentState  : 独立生命周期，永不整体清 (approvals/run_generation)

持久化：SQLite 主库 (StandardSessionDB, 单写者 registry 参考 acquire())，
  + index.json 文件式 (legacy 镜像，对齐现有 session_manager.py 的目录结构)。
本层为"增强补丁"，不改动现有 session_manager.py 的方法契约 (create_session/
  record_round/record_artifact/finalize_session)，只在旁边提供标准状态机供比对。
"""

import json
import logging
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 持久化路径 ────────────────────────────────────────────────────────────────
SESSION_DB_PATH = os.path.expanduser("~/.xiaolei/session_standard.db")
SESSION_ROOT = Path(os.path.expanduser("~/.xiaolei/sessions"))


# ── 生命周期状态（对齐 hermes classify_session_status + session_lifecycle）──
SESSION_STATUS_COMPLETE = "complete"
SESSION_STATUS_INTERRUPTED = "interrupted"
SESSION_STATUS_ERROR = "error"
SESSION_STATUS_EMPTY = "empty"
STATUS_PENDING = "running"  # 副本现有 running，保留兼容


def _new_session_id(now: Optional[datetime] = None) -> str:
    """会话 ID 生成：时间戳 + uuid 片段 (对齐 gateway/session_lifecycle.py._new_session_id)。"""
    import uuid
    now = now or datetime.now()
    return f"{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def _slug(text: str, max_len: int = 30) -> str:
    safe = re.sub(r"[^\w\u4e00-\u9fff]+", "_", text.strip())[:max_len]
    return safe.strip("_") or "session"


# ── 三层状态机 (dataclass, 对齐 gateway/session_state.py) ────────────────────
@dataclass
class TurnState:
    """单回合状态。结束回合时 clear()，但不触碰 persistent 字段。"""
    agent: Any = None          # 正在运行的 agent (None = idle)
    started_ts: float = 0.0    # 0.0 = 未运行
    lease: Any = None          # 跨进程 active-session 槽位租约
    busy_ack_ts: float = 0.0   # debounce；0.0 = 从未确认

    def clear(self) -> None:
        self.agent = self.lease = None
        self.started_ts = self.busy_ack_ts = 0.0


@dataclass
class ConversationState:
    """跨回合状态。会话边界 (/new, /resume, auto-reset) 时 clear()。"""
    model_override: Optional[Dict[str, Any]] = None      # /model 每会话覆盖
    reasoning_override: Optional[Dict[str, Any]] = None  # /reasoning 覆盖
    service_tier_override: Any = None                    # /fast priority
    last_resolved_model: str = ""
    queued_events: List[Any] = field(default_factory=list)
    ephemeral_pin: Optional[Any] = None

    def clear(self) -> None:
        """重置所有字段为默认，新字段自动被清。"""
        self.__dict__.update(ConversationState().__dict__)


@dataclass
class PersistentState:
    """独立生命周期状态：不被回合/边界整体清 (对齐 hermes PersistentState)。"""
    approvals: Optional[Dict[str, Any]] = None
    update_prompt_pending: bool = False
    run_generation: int = 0        # 单调递增，永不置0 (stale-run 检测依赖)
    native_image_paths: List[str] = field(default_factory=list)


# ── 单写者 registry (对齐 gateway/session_persistence.acquire) ────────────────
_registry: Dict[str, sqlite3.Connection] = {}
_registry_lock = threading.Lock()


def acquire(db_path: str) -> sqlite3.Connection:
    """进程级单写者 registry：同一路径只开一个连接 (对齐 hermes acquire())。"""
    with _registry_lock:
        conn = _registry.get(db_path)
        if conn is None:
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                parent_id TEXT,
                status TEXT,
                lifecycle_flags TEXT,   -- JSON: {end, reopen, archive, pin, hide, read}
                model_config TEXT,      -- JSON (对齐 hermes model_config)
                created_at TEXT,
                updated_at TEXT,
                meta_json TEXT
            )""")
            conn.commit()
            _registry[db_path] = conn
        return conn


# ── SQLite 持久化主库 ────────────────────────────────────────────────────────
class StandardSessionDB:
    """标准 Session SQLite 主库：upsert/inherit/lifecycle flags/list/count/delete。

    为不破坏现有 session_manager.py，本类只做"标准化增强"，不接管它的文件式路径。
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or SESSION_DB_PATH
        self._conn = acquire(self.db_path)
        self._conn.row_factory = sqlite3.Row  # 按列名访问（生命周期的 _row 依赖）

    def upsert(
        self,
        sid: str,
        status: str = SESSION_STATUS_INTERRUPTED,
        parent_id: Optional[str] = None,
        lifecycle_flags: Optional[Dict[str, Any]] = None,
        model_config: Optional[Dict[str, Any]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self._conn.execute(
            """INSERT INTO sessions (id, parent_id, status, lifecycle_flags, model_config,
                                     created_at, updated_at, meta_json)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 status=excluded.status,
                 lifecycle_flags=excluded.lifecycle_flags,
                 model_config=excluded.model_config,
                 updated_at=excluded.updated_at,
                 meta_json=excluded.meta_json""",
            (sid, parent_id, status,
             json.dumps(lifecycle_flags or {}),
             json.dumps(model_config or {}),
             now, now, json.dumps(meta or {})),
        )
        self._conn.commit()

    def lifecycle(self, sid: str, *, end: bool = False, reopen: bool = False,
                  archive: bool = False, hide: bool = False, read: bool = False) -> None:
        """生命周期标记 (对齐 session_lifecycle lifecycle flags)。"""
        flags = self.get_lifecycle_flags(sid) or {}
        if end:
            flags["end"] = True
        if reopen:
            flags["reopen"] = True
        if archive:
            flags["archive"] = True
        if hide:
            flags["hide"] = True
        if read:
            flags["read"] = True
        row = self._row(sid)
        status = "complete" if (row and row["status"] == SESSION_STATUS_COMPLETE) else (row["status"] if row else SESSION_STATUS_INTERRUPTED)
        self.upsert(sid, status=status, lifecycle_flags=flags,
                    parent_id=row["parent_id"] if row else None,
                    meta=json.loads(row["meta_json"]) if row and row["meta_json"] else None)

    def get_lifecycle_flags(self, sid: str) -> Optional[Dict[str, Any]]:
        row = self._row(sid)
        return json.loads(row["lifecycle_flags"]) if row and row["lifecycle_flags"] else None

    def _row(self, sid: str) -> Optional[sqlite3.Row]:
        cur = self._conn.execute("SELECT * FROM sessions WHERE id=?", (sid,))
        return cur.fetchone()

    def list(self, *, include_archived: bool = True, status: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT id, status, parent_id, lifecycle_flags, created_at, updated_at FROM sessions"
        clauses, params = [], []
        if not include_archived:
            clauses.append("(lifecycle_flags IS NULL OR json_extract(lifecycle_flags,'$.archive') IS NOT 1)")
        if status:
            clauses.append("status=?")
            params.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY updated_at DESC"
        return [dict(r) for r in self._conn.execute(sql, params)]

    def count(self, *, status: Optional[str] = None) -> int:
        sql = "SELECT COUNT(*) FROM sessions"
        params = []
        if status:
            sql += " WHERE status=?"
            params.append(status)
        return self._conn.execute(sql, params).fetchone()[0]

    def delete(self, sid: str, cascade_children: bool = False) -> None:
        self._conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
        if cascade_children:
            self._conn.execute("DELETE FROM sessions WHERE parent_id=?", (sid,))
        self._conn.commit()


# ── 生命周期辅助 (对齐 session_lifecycle auto_continue_freshness_window) ──────
def auto_continue_freshness_window() -> float:
    """自动续聊新鲜度窗口：默认 1 小时。环境变量 HERMES_AUTO_CONTINUE_FRESHNESS 覆盖。"""
    raw = os.environ.get("HERMES_AUTO_CONTINUE_FRESHNESS")
    try:
        return float(raw) if raw else 60 * 60
    except (TypeError, ValueError):
        return 60 * 60
