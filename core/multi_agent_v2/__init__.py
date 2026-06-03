"""
多Agent系统架构 V2
"""

from .agents.base.base_agent import BaseAgent, AgentFactory
from .agents.base.models import (
    AgentState, AgentType, Capability, Tool, Thought, Reflection,
    AgentMetrics, Task, ActionResult, Message,
    Step, StepStatus, StepType,
)

__version__ = "2.0.0"
__all__ = [
    "BaseAgent", "AgentFactory",
    "AgentState", "AgentType", "Capability", "Tool",
    "Thought", "Reflection", "AgentMetrics", "Mind", "MemorySystem",
    "Task", "ActionResult", "Message",
    "Step", "StepStatus", "StepType",
]
