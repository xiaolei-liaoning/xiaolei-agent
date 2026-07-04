"""V1 架构融入 V2 单 Agent — 统一模块

包含：
- prompts: 提示词模板 + LLM 工具函数
- context_memory: 任务级上下文记忆
- skill_router: 4层 Skill 路由
- worker: LLMAgent（队员）
- leader: LeaderAgent（队长）+ V1LeaderPool
"""

from .prompts import SYSTEM_PROMPT_TEMPLATE, OUTPUT_FORMATS, llm_json, get_llm_router_safe
from .context_memory import ContextMemory
from .skill_router import V1SkillRouter
from .worker import LLMAgent, AgentRole, AgentMessage
from .leader import LeaderAgent, V1LeaderPool

__all__ = [
    "SYSTEM_PROMPT_TEMPLATE", "OUTPUT_FORMATS",
    "llm_json", "get_llm_router_safe",
    "ContextMemory",
    "V1SkillRouter",
    "LLMAgent", "AgentRole", "AgentMessage",
    "LeaderAgent", "V1LeaderPool",
]
