"""
GlobalContextCenter - 全局上下文与状态中心

这是多Agent协作的核心，负责：
1. 任务状态追踪
2. 共享上下文管理
3. 状态广播与同步
"""

from core.multi_agent_v2.orchestration.context.global_context_center import (
    GlobalContextCenter,
    TaskState,
    TaskContext,
    SharedContext,
)

__all__ = [
    "GlobalContextCenter",
    "TaskState",
    "TaskContext",
    "SharedContext",
]

# NOTE: MessageBus/Message/EventType/Event/EventSystem 已移除
# - Message/MessageBus -> SharedBus
# - EventType/Event/EventSystem -> SharedBus 通知替代
