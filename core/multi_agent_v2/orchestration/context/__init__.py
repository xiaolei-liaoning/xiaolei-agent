"""
GlobalContextCenter - 全局上下文与状态中心

这是多Agent协作的核心，负责：
1. 任务状态追踪
2. 共享上下文管理
3. 消息总线
4. 事件系统
5. 状态广播与同步
"""

from core.multi_agent_v2.orchestration.context.global_context_center import (
    GlobalContextCenter,
    TaskState,
    EventType,
    Event,
    Message,
    TaskContext,
    SharedContext,
    MessageBus,
    EventSystem,
)

__all__ = [
    "GlobalContextCenter",
    "TaskState",
    "EventType",
    "Event",
    "Message",
    "TaskContext",
    "SharedContext",
    "MessageBus",
    "EventSystem",
]
