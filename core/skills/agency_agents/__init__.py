"""Agency Agents 角色匹配模块

将 agency-agents-zh 的 144+ 个专家 Agent 角色集成到 Skill 系统中，
Worker Agent 可根据任务场景自主匹配最合适的专家角色。
"""

from .handler import AgencyAgentMatcher, get_agency_agent_matcher
from .skill import (
    AgencyAgentExecuteSkill,
    AgencyAgentListSkill,
    AgencyAgentMatcherSkill,
)
from .worker_role_matcher import WorkerAgentRoleMatcher, get_worker_role_matcher

__all__ = [
    "AgencyAgentMatcher",
    "get_agency_agent_matcher",
    "AgencyAgentMatcherSkill",
    "AgencyAgentListSkill",
    "AgencyAgentExecuteSkill",
    "WorkerAgentRoleMatcher",
    "get_worker_role_matcher",
]    "AgencyAgentMatcherSkill",
    "AgencyAgentListSkill",
    "AgencyAgentExecuteSkill",
]