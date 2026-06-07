"""multi_agent_v2 agents package"""
from .base.base_agent import BaseAgent
from .base.models import AgentType, Task
from .base.work_agent import WorkAgent

__all__ = ["BaseAgent", "AgentType", "WorkAgent", "Task"]