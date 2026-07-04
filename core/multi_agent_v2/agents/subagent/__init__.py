"""Subagent 系统 — OpenCode 风格子代理生成与编排

核心能力：
- spawn_subagent: 创建并执行单个子代理
- orchestrate_subagents: DAG 并行编排多个子代理
- task: OpenCode 兼容的 task 工具接口
- orchestrate: OpenCode 兼容的 orchestrate 工具接口
"""

from .types import (
    AgentProfile, PROFILE_PERMISSIONS,
    SubagentSession, OrchestrationTask, OrchestrationResult,
    SubagentSessionManager, get_session_manager,
)
from .spawn import (
    spawn_subagent, spawn_background,
    orchestrate_subagents,
    task, orchestrate,
)

__all__ = [
    "AgentProfile", "PROFILE_PERMISSIONS",
    "SubagentSession", "OrchestrationTask", "OrchestrationResult",
    "SubagentSessionManager", "get_session_manager",
    "spawn_subagent", "spawn_background",
    "orchestrate_subagents",
    "task", "orchestrate",
]
