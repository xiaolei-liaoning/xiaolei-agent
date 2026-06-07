"""
多Agent系统架构 V2
"""

from .agents.base.base_agent import BaseAgent
from .agents.base.models import AgentType, Task, ActionResult

__version__ = "2.0.0"
__all__ = [
    "BaseAgent",
    "AgentType",
    "Task",
    "ActionResult",
]