"""multi_agent_v2 agents package

只有 WorkAgent 一种类型，不预设角色。
"""
from .base.base_agent import BaseAgent, AgentType, AgentState, AgentFactory
from .base.work_agent import WorkAgent

__all__ = [
    "BaseAgent",
    "AgentType",
    "AgentState",
    "AgentFactory",
    "WorkAgent",
]
