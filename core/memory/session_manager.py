"""Session Artifact Manager — 将会话关键信息持久化为文件

目录结构:
  ~/.xiaolei/sessions/
    ├── index.json
    ├── 2026-07-04_110214_open-design/
    │   ├── session.md
    │   ├── round_001.md ~ round_NNN.md
    │   └── artifacts/
    │       ├── tool_codegraph_explore.md
    │       ├── final_answer.md
    │       └── ...
    └── ...
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SESSION_ROOT = Path(os.path.expanduser("~/.xiaolei/sessions"))


def _slug(text: str, max_len: int = 30) -> str:
    safe = re.sub(r"[^\w\u4e00-\u9fff]+", "_", text.strip())[:max_len]
    return safe.strip("_") or "session"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class SessionManager:
    _instance = None

    def __init__(self):
        self._index_path = SESSION_ROOT / "index.json"
        self._index: Dict[str, Any] = {}
        # 修复(跨用户泄漏): 当前归属用户（由 coordinator 注入），
        # create_session 时写入 entry.user_id
        self._owner_user_id: str = ""
        self._stack: List[Dict[str, Any]] = []  # stack of {sid, dir}
        self._load_index()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_index(self):
        if self._index_path.exists():
            try:
                self._index = json.loads(self._index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._index = {}
        SESSION_ROOT.mkdir(parents=True, exist_ok=True)

    def _save_index(self):
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._index, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._index_path)

    def create_session(self, task_description: str) -> str:
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        slug = _slug(task_description)
        session_id = f"{ts}_{slug}"
        session_dir = SESSION_ROOT / session_id
        artifacts_dir = session_dir / "artifacts"
        session_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        self._stack.append({"sid": session_id, "dir": session_dir})

        entry = {
            "session_id": session_id,
            "task": task_description[:200],
            "created_at": _now_iso(),
            "rounds": 0,
            "artifacts": [],
            "status": "running",
            "summary": "",
            # 修复(跨用户泄漏): 记录归属用户，get_recent_sessions 按此过滤
            "user_id": str(getattr(self, "_owner_user_id", "") or ""),
        }
        self._index[session_id] = entry
        self._save_index()

        md = (
            f"# Session: {task_description}\n\n"
            f"- **ID**: {session_id}\n"
            f"- **Created**: {_now_iso()}\n"
            f"- **Task**: {task_description}\n\n"
            "## Artifacts\n\n_Key results saved in `artifacts/`._\n"
        )
        (session_dir / "session.md").write_text(md, encoding="utf-8")

        logger.info(f"Session created: {session_id}")
        return session_id

    def pop_session(self):
        """退出当前 session，恢复到父 session（如果有）"""
        if self._stack:
            self._stack.pop()

    @property
    def _current(self) -> Optional[Dict[str, Any]]:
        return self._stack[-1] if self._stack else None

    def record_round(self, round_idx: int, summary: str):
        cur = self._current
        if not cur:
            return
        (Path(cur["dir"]) / f"round_{round_idx:03d}.md").write_text(summary, encoding="utf-8")
        entry = self._index.get(cur["sid"])
        if entry:
            entry["rounds"] = max(entry["rounds"], round_idx)

    def record_artifact(self, name: str, content: str) -> Optional[str]:
        cur = self._current
        if not cur:
            return None
        safe = re.sub(r"[^\w\u4e00-\u9fff\-]", "_", name)[:60]
        p = Path(cur["dir"]) / "artifacts" / f"{safe}.md"
        p.write_text(content, encoding="utf-8")
        entry = self._index.get(cur["sid"])
        if entry and p.name not in entry["artifacts"]:
            entry["artifacts"].append(p.name)
        logger.info(f"Artifact saved: {p.name} ({len(content)} chars)")
        return str(p)

    def finalize_session(self, summary: str):
        cur = self._current
        if not cur:
            return
        entry = self._index.get(cur["sid"])
        if entry:
            entry["status"] = "completed"
            entry["summary"] = summary[:500]
            entry["ended_at"] = _now_iso()
            self._save_index()
        md_path = Path(cur["dir"]) / "session.md"
        if md_path.exists():
            existing = md_path.read_text(encoding="utf-8")
            md_path.write_text(
                f"{existing}\n## Summary\n\n{summary}\n\n_Session ended at {_now_iso()}_\n",
                encoding="utf-8",
            )
        logger.info(f"Session finalized: {cur['sid']}")
        self.pop_session()  # 自动 pop，恢复到父 session

    @property
    def current_session_id(self) -> str:
        cur = self._current
        return cur["sid"] if cur else ""

    @property
    def artifacts_dir(self) -> Optional[str]:
        cur = self._current
        if cur:
            return str(Path(cur["dir"]) / "artifacts")
        return None

    def get_recent_sessions(self, n: int = 5, user_id: str = "") -> List[Dict]:
        entries = [e for e in self._index.values() if e.get("status") == "completed"]
        # 修复(跨用户泄漏): session_id 没有用户字段，用 entry 里存的 user_id
        # 过滤（写入时记录）；user_id 为空 = 不过滤（V1 兼容）
        if user_id:
            entries = [e for e in entries if e.get("user_id", "") == user_id]
        entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
        return entries[:n]

    def build_context_block(self, n: int = 3, user_id: str = "") -> str:
        """历史会话块（注入 LLM）

        修复(跨用户泄漏): user_id 为空 = 全局索引（旧行为，V1 兼容）；
        传入 user_id 时只列该用户的会话——测试/多用户隔离，防止 A 用户
        的会话摘要被注进 B 用户的上下文（深度测试 dtest_edge 实测泄漏）。
        """
        recent = self.get_recent_sessions(n, user_id=user_id)
        if not recent:
            return ""
        lines = ["\n── 历史会话 ──"]
        for s in recent:
            task = s.get("task", "")[:80]
            summary = s.get("summary", "")[:200]
            n_a = len(s.get("artifacts", []))
            lines.append(f"- [{s['session_id']}] {task} ({n_a} files): {summary}")
        lines.append("──（可直接 read_file 读取 artifact 获取完整信息）──")
        return "\n".join(lines)


def get_session_manager() -> SessionManager:
    return SessionManager.get_instance()
