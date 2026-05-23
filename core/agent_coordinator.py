"""向后兼容层 - Agent协调器

旧 `core.agents` 已移除，此模块保持向后兼容。
实际委托给 multi_agent_v2 的 IntelligentScheduler。

DEPRECATED: 请使用 core.multi_agent_v2 的智能调度器。
"""

import logging
import warnings

logger = logging.getLogger(__name__)
warnings.warn(
    "core.agent_coordinator 已废弃，请使用 core.multi_agent_v2 的智能调度器。",
    DeprecationWarning,
    stacklevel=2,
)
logger.warning("DEPRECATED: agent_coordinator 将在未来版本移除，请迁移至 multi_agent_v2")

AgentCoordinator = None


def get_agent_coordinator():
    """旧接口 - 返回 multi_agent_v2 的 IntelligentScheduler 实例"""
    logger.warning("DEPRECATED: get_agent_coordinator() 返回 None，请使用 IntelligentScheduler")
    return None


# 向后兼容别名
GroupCollaborationCoordinator = None
get_group_coordinator = get_agent_coordinator

__all__ = [
    'AgentCoordinator',
    'get_agent_coordinator',
    'GroupCollaborationCoordinator',
    'get_group_coordinator',
]
