"""
ConversationStore — SQLite 持久化对话历史

对标 Opencode 的 SQLite 存储层（message + part 表），
轻量单表实现，按 session_id 分区存储。
"""

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "data", "conversations.db",
)


class ConversationStore:
    """轻量级 SQLite 对话持久化存储

    提供按 session_id 分区的对话记录读写。
    线程安全（thread-local connections）。
    """

    _instance: Optional['ConversationStore'] = None
    _lock = threading.Lock()

    def __init__(self, db_path: str = ""):
        self.db_path = os.path.abspath(db_path or _DEFAULT_DB)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._local = threading.local()
        self._init_db()

    @classmethod
    def get_instance(cls, db_path: str = "") -> 'ConversationStore':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(db_path)
        return cls._instance

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                task_description TEXT,
                created_at TEXT,
                updated_at TEXT,
                metadata TEXT
            );
            CREATE TABLE IF NOT EXISTS tool_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                round_num INTEGER NOT NULL,
                tool_name TEXT,
                success INTEGER,
                result TEXT,
                arguments TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                round_num INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                tool_call_id TEXT,
                name TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS compaction_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                round_num INTEGER NOT NULL,
                summary TEXT,
                tail_start_round INTEGER,
                created_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_tool_results_session
                ON tool_results(session_id, round_num);
            CREATE INDEX IF NOT EXISTS idx_conv_msgs_session
                ON conversation_messages(session_id, round_num);
            CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                round_num INTEGER NOT NULL,
                state_json TEXT NOT NULL,
                created_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_compaction_session
                ON compaction_log(session_id, round_num);
            CREATE INDEX IF NOT EXISTS idx_checkpoints_session
                ON checkpoints(session_id, round_num);
        """)
        conn.commit()

    def save_session(self, session_id: str, task_description: str,
                     metadata: Optional[Dict] = None):
        now = datetime.now().isoformat()
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO sessions (id, task_description, created_at, updated_at, metadata) VALUES (?, ?, ?, ?, ?)",
            (session_id, task_description, now, now,
             json.dumps(metadata or {}, ensure_ascii=False)),
        )
        conn.commit()

    def load_session(self, session_id: str) -> Optional[Dict]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return dict(row) if row else None

    def save_tool_result(self, session_id: str, round_num: int, entry: Dict):
        conn = self._get_conn()
        result_str = json.dumps(entry.get("result", {}), ensure_ascii=False, default=str)
        args_str = json.dumps(
            entry.get("tool_call", {}).get("arguments", {}),
            ensure_ascii=False, default=str,
        )
        conn.execute(
            "INSERT INTO tool_results (session_id, round_num, tool_name, success, result, arguments, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                session_id, round_num,
                entry.get("tool_call", {}).get("name", ""),
                1 if entry.get("success") else 0,
                result_str[:10000], args_str,
                datetime.now().isoformat(),
            ),
        )
        conn.commit()

    def save_conversation_messages(self, session_id: str, round_num: int,
                                   messages: List[Dict]):
        conn = self._get_conn()
        now = datetime.now().isoformat()
        for msg in messages:
            content = msg.get("content", "")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            conn.execute(
                "INSERT INTO conversation_messages (session_id, round_num, role, content, tool_call_id, name, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id, round_num,
                    msg.get("role", ""),
                    content[:10000],
                    msg.get("tool_call_id", ""),
                    msg.get("name", ""),
                    now,
                ),
            )
        conn.commit()

    def save_compaction(self, session_id: str, round_num: int,
                        summary: str, tail_start_round: int):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO compaction_log (session_id, round_num, summary, tail_start_round, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, round_num, summary, tail_start_round,
             datetime.now().isoformat()),
        )
        conn.commit()

    def get_latest_compaction(self, session_id: str) -> Optional[Dict]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM compaction_log WHERE session_id = ? ORDER BY round_num DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

    def close(self):
        """关闭当前线程的连接"""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    def save_checkpoint(self, session_id: str, round_num: int, state: Dict):
        """保存执行检查点"""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO checkpoints (session_id, round_num, state_json, created_at) VALUES (?, ?, ?, ?)",
            (session_id, round_num, json.dumps(state, ensure_ascii=False, default=str),
             datetime.now().isoformat()),
        )
        conn.commit()

    def load_latest_checkpoint(self, session_id: str) -> Optional[Dict]:
        """加载最新的检查点"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM checkpoints WHERE session_id = ? ORDER BY round_num DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["state"] = json.loads(result["state_json"])
        return result

    def list_checkpoints(self, session_id: str) -> List[Dict]:
        """列出所有检查点摘要"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT round_num, created_at FROM checkpoints WHERE session_id = ? ORDER BY round_num",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_checkpoints(self, session_id: str):
        """清除某 session 的所有检查点"""
        conn = self._get_conn()
        conn.execute("DELETE FROM checkpoints WHERE session_id = ?", (session_id,))
        conn.commit()

    def get_compaction_summaries(self, session_id: str) -> List[str]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT summary FROM compaction_log WHERE session_id = ? ORDER BY round_num ASC",
            (session_id,),
        ).fetchall()
        return [r["summary"] for r in rows if r["summary"]]
