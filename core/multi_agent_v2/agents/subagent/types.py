"""Subagent 系统 — 代理类型 + 会话管理"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


class AgentProfile(str, Enum):
    """代理类型 — 对应不同的工具权限和系统提示"""
    EXPLORE = "explore"
    BUILD = "build"
    GENERAL = "general"
    ANALYZE = "analyze"
    ORCHESTRATOR = "orchestrator"


# 每种 profile 的工具白名单/黑名单配置 + 角色提示词
# V1→V2: 参照 OpenCode (opencode_副本) agent 定义风格重写为专业角色提示
#   - 第一行: 角色定位（一句话）
#   - 优势: 具体工具使用场景
#   - 行为准则: 清晰的可做/不可做
#   - 输出预期: 主代理期望的格式
def _load_profile_hint(profile: AgentProfile) -> str:
    """从 ~/.xiaolei/roles/{profile}.md 加载 system_hint"""
    try:
        from core.multi_agent_v2.agents.role_loader import get
        role = get(profile.value)
        if role:
            parts = [f"<role:{profile.value}>"]
            if role.description:
                parts.append(role.description)
            if role.rules:
                parts.append(f"行为准则：\n{role.rules}")
            if role.output_spec:
                parts.append(f"输出规范：\n{role.output_spec}")
            parts.append(f"</role:{profile.value}>")
            return "\n\n".join(parts)
    except Exception:
        pass
    return ""


PROFILE_PERMISSIONS = {
    AgentProfile.EXPLORE: {
        "allowed": ["read_file", "search_files", "glob", "fetch_url", "web_search", "grep", "bash"],
        "disallowed": ["write_file", "edit_file", "execute_python", "execute_shell", "task", "orchestrate"],
        "system_hint": _load_profile_hint(AgentProfile.EXPLORE),
    },
    AgentProfile.BUILD: {
        "allowed": None,
        "disallowed": None,
        "system_hint": _load_profile_hint(AgentProfile.BUILD),
    },
    AgentProfile.GENERAL: {
        "allowed": None,
        "disallowed": None,
        "system_hint": _load_profile_hint(AgentProfile.GENERAL),
    },
    AgentProfile.ANALYZE: {
        "allowed": None,
        "disallowed": ["write_file", "edit_file", "execute_shell"],
        "system_hint": _load_profile_hint(AgentProfile.ANALYZE),
    },
    AgentProfile.ORCHESTRATOR: {
        "allowed": ["read_file", "write_file", "task", "orchestrate"],
        "disallowed": ["execute_shell", "execute_python", "edit_file"],
        "system_hint": _load_profile_hint(AgentProfile.ORCHESTRATOR),
    },
}


@dataclass
class SubagentSession:
    """子代理会话"""
    session_id: str
    parent_session_id: str
    profile: AgentProfile
    task_description: str
    state: str = "pending"  # pending / running / completed / error
    result: Optional[str] = None
    error: Optional[str] = None
    start_time: float = 0.0
    end_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, parent_id: str, profile: AgentProfile,
               task: str, **meta) -> "SubagentSession":
        return cls(
            session_id=uuid4().hex[:12],
            parent_session_id=parent_id,
            profile=profile,
            task_description=task,
            metadata=meta,
        )


@dataclass
class OrchestrationTask:
    """编排任务定义 — 对应 OpenCode 的 TaskDef"""
    id: str
    description: str
    prompt: str
    agent: Optional[AgentProfile] = None
    depends_on: List[str] = field(default_factory=list)


@dataclass
class OrchestrationResult:
    """编排结果"""
    task_id: str
    success: bool
    output: str = ""
    error: str = ""


class SubagentSessionManager:
    """子代理会话管理器（in-memory + JSON 持久化）"""

    def __init__(self):
        self._sessions: Dict[str, SubagentSession] = {}
        self._parent_index: Dict[str, List[str]] = {}  # parent_id → [session_id]
        self._storage_dir = None

    def _get_storage_dir(self) -> str:
        if self._storage_dir is None:
            import os
            base = os.path.expanduser("~/.xiaolei/subagent_sessions")
            os.makedirs(base, exist_ok=True)
            self._storage_dir = base
        return self._storage_dir

    def _save_session(self, session: SubagentSession):
        """持久化单个会话到 JSON 文件"""
        import json, os
        try:
            path = os.path.join(self._get_storage_dir(), f"{session.session_id}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({
                    "session_id": session.session_id,
                    "parent_session_id": session.parent_session_id,
                    "profile": session.profile.value,
                    "task_description": session.task_description[:500],
                    "state": session.state,
                    "result": (session.result or "")[:5000],
                    "error": session.error,
                    "start_time": session.start_time,
                    "end_time": session.end_time,
                    "metadata": session.metadata,
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_sessions(self):
        """从 JSON 文件恢复所有会话"""
        import json, glob, os
        try:
            dir_path = self._get_storage_dir()
            for path in glob.glob(os.path.join(dir_path, "*.json")):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    session = SubagentSession(
                        session_id=data["session_id"],
                        parent_session_id=data.get("parent_session_id", ""),
                        profile=AgentProfile(data.get("profile", "general")),
                        task_description=data.get("task_description", ""),
                        state=data.get("state", "completed"),
                        result=data.get("result"),
                        error=data.get("error"),
                        start_time=data.get("start_time", 0),
                        end_time=data.get("end_time", 0),
                        metadata=data.get("metadata", {}),
                    )
                    self._sessions[session.session_id] = session
                    if session.parent_session_id not in self._parent_index:
                        self._parent_index[session.parent_session_id] = []
                    self._parent_index[session.parent_session_id].append(session.session_id)
                except Exception:
                    pass
        except Exception:
            pass

    def create(self, parent_id: str, profile: AgentProfile,
               task: str, **meta) -> SubagentSession:
        session = SubagentSession.create(parent_id, profile, task, **meta)
        self._sessions[session.session_id] = session
        if parent_id not in self._parent_index:
            self._parent_index[parent_id] = []
        self._parent_index[parent_id].append(session.session_id)
        self._save_session(session)
        return session

    def update(self, session_id: str, **kwargs):
        if session_id in self._sessions:
            for k, v in kwargs.items():
                setattr(self._sessions[session_id], k, v)
            self._save_session(self._sessions[session_id])

    def get(self, session_id: str) -> Optional[SubagentSession]:
        return self._sessions.get(session_id)

    def get_children(self, parent_id: str) -> List[SubagentSession]:
        child_ids = self._parent_index.get(parent_id, [])
        return [s for s in (self._sessions.get(cid) for cid in child_ids) if s]

    def remove(self, session_id: str):
        if session_id in self._sessions:
            parent_id = self._sessions[session_id].parent_session_id
            del self._sessions[session_id]
            if parent_id in self._parent_index:
                self._parent_index[parent_id] = [
                    cid for cid in self._parent_index[parent_id] if cid != session_id
                ]


# 全局会话管理器单例
_session_manager: Optional[SubagentSessionManager] = None


def get_session_manager() -> SubagentSessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SubagentSessionManager()
        _session_manager._load_sessions()
    return _session_manager
