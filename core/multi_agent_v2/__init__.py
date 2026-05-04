"""
多Agent系统架构V2.0

真正的多Agent系统，每个Agent都有独立的心智、记忆、决策能力
"""

from .agents.base.base_agent import (
    BaseAgent,
    AgentState,
    AgentType,
    Capability,
    Tool,
    Thought,
    Reflection,
    AgentMetrics,
    Mind,
    MemorySystem,
    Task,
    ActionResult,
    Message
)

__version__ = "2.0.0"
__all__ = [
    "BaseAgent",
    "AgentState",
    "AgentType",
    "Capability",
    "Tool",
    "Thought",
    "Reflection",
    "AgentMetrics",
    "Mind",
    "MemorySystem",
    "Task",
    "ActionResult",
    "Message"
]
