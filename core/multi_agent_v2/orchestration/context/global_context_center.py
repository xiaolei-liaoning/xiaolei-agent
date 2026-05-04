"""
全局上下文与状态中心 - 多Agent协作的核心

负责：
1. 任务状态追踪
2. 共享上下文管理
3. 消息总线
4. 事件系统
5. 状态广播与同步
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from collections import defaultdict
import uuid

logger = logging.getLogger(__name__)


class TaskState(Enum):
    """任务状态"""
    PENDING = "pending"           # 待处理
    DECOMPOSED = "decomposed"     # 已分解
    SCHEDULED = "scheduled"       # 已调度
    RUNNING = "running"           # 执行中
    WAITING = "waiting"           # 等待中
    COMPLETED = "completed"       # 已完成
    FAILED = "failed"             # 失败
    CANCELLED = "cancelled"       # 已取消


class EventType(Enum):
    """事件类型"""
    TASK_CREATED = "task_created"
    TASK_ASSIGNED = "task_assigned"
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    CONTEXT_UPDATED = "context_updated"
    AGENT_REGISTERED = "agent_registered"
    AGENT_STATE_CHANGED = "agent_state_changed"
    CONFLICT_DETECTED = "conflict_detected"
    SYNC_REQUEST = "sync_request"


@dataclass
class TaskContext:
    """任务上下文"""
    task_id: str
    original_request: str
    decomposed_subtasks: List[Dict[str, Any]] = field(default_factory=list)
    assigned_agents: Dict[str, str] = field(default_factory=dict)  # subtask_id -> agent_id
    partial_results: Dict[str, Any] = field(default_factory=dict)
    final_result: Optional[Any] = None
    state: TaskState = TaskState.PENDING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SharedContext:
    """共享上下文"""
    task_id: str
    global_data: Dict[str, Any] = field(default_factory=dict)
    agent_views: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    revision: int = 0

    def update(self, agent_id: str, key: str, value: Any) -> None:
        """更新共享数据"""
        self.global_data[key] = value
        self.agent_views[agent_id] = self.agent_views.get(agent_id, {})
        self.agent_views[agent_id][key] = value
        self.revision += 1

    def get_snapshot(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """获取上下文快照"""
        if agent_id:
            view = self.agent_views.get(agent_id, {})
            return {**self.global_data, **view}
        return self.global_data.copy()


@dataclass
class Event:
    """事件"""
    event_id: str
    event_type: EventType
    source_id: str
    target_id: Optional[str]  # None表示广播
    data: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    trace_id: Optional[str] = None


@dataclass
class Message:
    """消息"""
    message_id: str
    from_agent: str
    to_agent: Optional[str]  # None表示广播
    content: Any
    message_type: str
    timestamp: float = field(default_factory=time.time)
    reply_to: Optional[str] = None


class MessageBus:
    """消息总线 - Agent间通信"""

    def __init__(self):
        self.queues: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self.subscriptions: Dict[str, Set[str]] = defaultdict(set)
        self.message_history: List[Message] = []

    async def publish(self, message: Message) -> None:
        """发布消息"""
        self.message_history.append(message)

        if message.to_agent:
            # 点对点消息
            queue = self.queues[message.to_agent]
            await queue.put(message)
        else:
            # 广播消息
            for agent_id in self.subscriptions.get(message.from_agent, set()):
                queue = self.queues[agent_id]
                await queue.put(message)

        logger.debug(f"消息发布: {message.message_type} from {message.from_agent} to {message.to_agent or 'broadcast'}")

    async def subscribe(self, agent_id: str, channels: Set[str]) -> None:
        """订阅频道"""
        for channel in channels:
            self.subscriptions[channel].add(agent_id)

    async def unsubscribe(self, agent_id: str, channels: Set[str]) -> None:
        """取消订阅"""
        for channel in channels:
            self.subscriptions[channel].discard(agent_id)

    async def receive(self, agent_id: str, timeout: Optional[float] = None) -> Optional[Message]:
        """接收消息"""
        queue = self.queues[agent_id]
        try:
            return await asyncio.wait_for(queue.get(), timeout)
        except asyncio.TimeoutError:
            return None

    async def get_history(self, agent_id: Optional[str] = None, limit: int = 100) -> List[Message]:
        """获取消息历史"""
        if agent_id:
            return [m for m in self.message_history[-limit:] if m.from_agent == agent_id or m.to_agent == agent_id]
        return self.message_history[-limit:]


class EventSystem:
    """事件系统 - 发布/订阅模式"""

    def __init__(self):
        self.handlers: Dict[EventType, List[Callable]] = defaultdict(list)
        self.event_history: List[Event] = []

    def subscribe(self, event_type: EventType, handler: Callable) -> None:
        """订阅事件"""
        self.handlers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: Callable) -> None:
        """取消订阅"""
        if handler in self.handlers[event_type]:
            self.handlers[event_type].remove(handler)

    async def publish(self, event: Event) -> None:
        """发布事件"""
        self.event_history.append(event)

        handlers = self.handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"事件处理器执行失败: {e}")

        logger.debug(f"事件发布: {event.event_type.value} from {event.source_id}")

    async def get_history(self, event_type: Optional[EventType] = None, limit: int = 100) -> List[Event]:
        """获取事件历史"""
        if event_type:
            return [e for e in self.event_history[-limit:] if e.event_type == event_type]
        return self.event_history[-limit:]


class GlobalContextCenter:
    """全局上下文与状态中心 - 多Agent协作的核心"""

    def __init__(self):
        # 任务上下文管理
        self.task_contexts: Dict[str, TaskContext] = {}

        # 共享上下文
        self.shared_contexts: Dict[str, SharedContext] = {}

        # 消息总线
        self.message_bus = MessageBus()

        # 事件系统
        self.event_system = EventSystem()

        # Agent注册表
        self.agent_registry: Dict[str, Dict[str, Any]] = {}

        # 追踪ID生成器
        self.trace_id_counter = 0

        # 锁
        self._lock = asyncio.Lock()

        logger.info("全局上下文中心初始化完成")

    def generate_trace_id(self) -> str:
        """生成追踪ID"""
        self.trace_id_counter += 1
        return f"trace_{self.trace_id_counter}_{int(time.time())}"

    async def create_task_context(self, request: str, trace_id: Optional[str] = None) -> str:
        """创建任务上下文"""
        task_id = f"task_{uuid.uuid4().hex[:12]}"

        context = TaskContext(
            task_id=task_id,
            original_request=request
        )

        async with self._lock:
            self.task_contexts[task_id] = context
            self.shared_contexts[task_id] = SharedContext(task_id=task_id)

        # 发布任务创建事件
        await self.event_system.publish(Event(
            event_id=f"evt_{uuid.uuid4().hex[:8]}",
            event_type=EventType.TASK_CREATED,
            source_id="context_center",
            target_id=None,
            data={"task_id": task_id, "request": request},
            trace_id=trace_id
        ))

        logger.info(f"创建任务上下文: {task_id}")
        return task_id

    async def update_task_state(self, task_id: str, state: TaskState, metadata: Optional[Dict] = None) -> None:
        """更新任务状态"""
        async with self._lock:
            if task_id not in self.task_contexts:
                raise ValueError(f"任务 {task_id} 不存在")

            context = self.task_contexts[task_id]
            context.state = state
            context.updated_at = time.time()

            if metadata:
                context.metadata.update(metadata)

        # 发布状态变更事件
        event_type_map = {
            TaskState.SCHEDULED: EventType.TASK_ASSIGNED,
            TaskState.RUNNING: EventType.TASK_STARTED,
            TaskState.COMPLETED: EventType.TASK_COMPLETED,
            TaskState.FAILED: EventType.TASK_FAILED,
        }

        event_type = event_type_map.get(state, EventType.TASK_PROGRESS)

        await self.event_system.publish(Event(
            event_id=f"evt_{uuid.uuid4().hex[:8]}",
            event_type=event_type,
            source_id="context_center",
            target_id=None,
            data={"task_id": task_id, "state": state.value},
            trace_id=context.metadata.get("trace_id")
        ))

        logger.info(f"任务状态更新: {task_id} -> {state.value}")

    async def update_context(self, task_id: str, agent_id: str, key: str, value: Any) -> None:
        """更新共享上下文"""
        async with self._lock:
            if task_id not in self.shared_contexts:
                raise ValueError(f"任务 {task_id} 不存在")

            shared_context = self.shared_contexts[task_id]
            shared_context.update(agent_id, key, value)

        # 发布上下文更新事件
        await self.event_system.publish(Event(
            event_id=f"evt_{uuid.uuid4().hex[:8]}",
            event_type=EventType.CONTEXT_UPDATED,
            source_id=agent_id,
            target_id=None,
            data={"task_id": task_id, "key": key},
            trace_id=self.task_contexts[task_id].metadata.get("trace_id")
        ))

    async def get_context(self, task_id: str, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """获取上下文"""
        if task_id not in self.shared_contexts:
            raise ValueError(f"任务 {task_id} 不存在")

        shared_context = self.shared_contexts[task_id]
        return shared_context.get_snapshot(agent_id)

    async def register_agent(self, agent_id: str, agent_info: Dict[str, Any]) -> None:
        """注册Agent"""
        async with self._lock:
            self.agent_registry[agent_id] = {
                **agent_info,
                "registered_at": time.time(),
                "state": "active"
            }

        # 发布注册事件
        await self.event_system.publish(Event(
            event_id=f"evt_{uuid.uuid4().hex[:8]}",
            event_type=EventType.AGENT_REGISTERED,
            source_id=agent_id,
            target_id=None,
            data={"agent_id": agent_id, "info": agent_info}
        ))

        logger.info(f"Agent注册: {agent_id}")

    async def update_agent_state(self, agent_id: str, state: str) -> None:
        """更新Agent状态"""
        async with self._lock:
            if agent_id in self.agent_registry:
                self.agent_registry[agent_id]["state"] = state
                self.agent_registry[agent_id]["last_update"] = time.time()

        # 发布状态变更事件
        await self.event_system.publish(Event(
            event_id=f"evt_{uuid.uuid4().hex[:8]}",
            event_type=EventType.AGENT_STATE_CHANGED,
            source_id=agent_id,
            target_id=None,
            data={"agent_id": agent_id, "state": state}
        ))

    async def get_agent_info(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取Agent信息"""
        return self.agent_registry.get(agent_id)

    async def get_all_agents(self, state: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取所有Agent"""
        if state:
            return [a for a in self.agent_registry.values() if a.get("state") == state]
        return list(self.agent_registry.values())

    async def publish_message(self, message: Message) -> None:
        """发布消息"""
        await self.message_bus.publish(message)

    async def send_message(self, from_agent: str, to_agent: str, content: Any, message_type: str = "direct") -> None:
        """发送点对点消息"""
        message = Message(
            message_id=f"msg_{uuid.uuid4().hex[:8]}",
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            message_type=message_type
        )
        await self.message_bus.publish(message)

    async def broadcast_message(self, from_agent: str, content: Any, message_type: str = "broadcast") -> None:
        """广播消息"""
        message = Message(
            message_id=f"msg_{uuid.uuid4().hex[:8]}",
            from_agent=from_agent,
            to_agent=None,
            content=content,
            message_type=message_type
        )
        await self.message_bus.publish(message)

    async def subscribe_to_messages(self, agent_id: str) -> None:
        """订阅消息"""
        await self.message_bus.subscribe(agent_id, {agent_id})

    async def receive_message(self, agent_id: str, timeout: Optional[float] = None) -> Optional[Message]:
        """接收消息"""
        return await self.message_bus.receive(agent_id, timeout)

    async def assign_subtask(self, task_id: str, subtask_id: str, agent_id: str) -> None:
        """分配子任务"""
        async with self._lock:
            if task_id not in self.task_contexts:
                raise ValueError(f"任务 {task_id} 不存在")

            context = self.task_contexts[task_id]
            context.assigned_agents[subtask_id] = agent_id

        # 发布任务分配事件
        await self.event_system.publish(Event(
            event_id=f"evt_{uuid.uuid4().hex[:8]}",
            event_type=EventType.TASK_ASSIGNED,
            source_id="context_center",
            target_id=agent_id,
            data={"task_id": task_id, "subtask_id": subtask_id, "agent_id": agent_id}
        ))

        logger.info(f"子任务分配: {subtask_id} -> Agent {agent_id}")

    async def update_partial_result(self, task_id: str, agent_id: str, subtask_id: str, result: Any) -> None:
        """更新部分结果"""
        async with self._lock:
            if task_id not in self.task_contexts:
                raise ValueError(f"任务 {task_id} 不存在")

            context = self.task_contexts[task_id]
            context.partial_results[subtask_id] = {
                "agent_id": agent_id,
                "result": result,
                "timestamp": time.time()
            }
            context.updated_at = time.time()

        logger.info(f"部分结果更新: {task_id}.{subtask_id} by Agent {agent_id}")

    async def get_partial_results(self, task_id: str) -> Dict[str, Any]:
        """获取所有部分结果"""
        if task_id not in self.task_contexts:
            raise ValueError(f"任务 {task_id} 不存在")

        return self.task_contexts[task_id].partial_results.copy()

    async def set_final_result(self, task_id: str, result: Any) -> None:
        """设置最终结果"""
        async with self._lock:
            if task_id not in self.task_contexts:
                raise ValueError(f"任务 {task_id} 不存在")

            context = self.task_contexts[task_id]
            context.final_result = result
            context.state = TaskState.COMPLETED
            context.updated_at = time.time()

        logger.info(f"任务完成: {task_id}")

    async def subscribe(self, agent_id: str, events: List[EventType]) -> None:
        """订阅事件"""
        for event_type in events:
            handler = self._create_event_handler(agent_id)
            self.event_system.subscribe(event_type, handler)

    def _create_event_handler(self, agent_id: str) -> Callable:
        """创建事件处理器"""
        async def handler(event: Event):
            # 这里可以添加消息队列逻辑
            logger.debug(f"Agent {agent_id} 收到事件: {event.event_type.value}")
        return handler

    async def broadcast_state(self, task_id: str) -> None:
        """广播任务状态"""
        if task_id not in self.task_contexts:
            raise ValueError(f"任务 {task_id} 不存在")

        context = self.task_contexts[task_id]

        await self.broadcast_message(
            from_agent="context_center",
            content={
                "task_id": task_id,
                "state": context.state.value,
                "partial_results": context.partial_results
            },
            message_type="state_sync"
        )

    async def get_task_context(self, task_id: str) -> Optional[TaskContext]:
        """获取任务上下文"""
        return self.task_contexts.get(task_id)

    async def cleanup_completed_tasks(self, older_than_hours: int = 24) -> int:
        """清理已完成的任务"""
        cutoff_time = time.time() - (older_than_hours * 3600)
        cleaned = 0

        async with self._lock:
            completed_tasks = [
                task_id for task_id, ctx in self.task_contexts.items()
                if ctx.state in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED]
                and ctx.updated_at < cutoff_time
            ]

            for task_id in completed_tasks:
                del self.task_contexts[task_id]
                if task_id in self.shared_contexts:
                    del self.shared_contexts[task_id]
                cleaned += 1

        if cleaned > 0:
            logger.info(f"清理了 {cleaned} 个已完成任务")

        return cleaned
