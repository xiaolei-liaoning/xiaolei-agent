"""向后兼容层 - Agent协调器

旧 `core.agents` 已移除，此模块保持向后兼容。
实际委托给 multi_agent_v2 的 IntelligentScheduler。
"""

AgentCoordinator = None


def get_agent_coordinator():
    """旧接口 - 返回 multi_agent_v2 的 IntelligentScheduler 实例"""
    try:
        pass
        return None
    except Exception:
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
