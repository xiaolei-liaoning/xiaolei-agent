"""
SharedBus — 统一消息总线 + 共享内存

职责：
1. 消息通信：publish/subscribe/direct 三种模式
2. 共享内存（只读）：任务上下文、最终结果
3. Agent 间协调：任务完成通知、结果协商

合并了原有的 GlobalContextCenter（只保留数据）和 communication_center。
"""

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """消息类型"""
    TASK_ASSIGNED = "task_assigned"
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    AGENT_MESSAGE = "agent_message"
    AGENT_BROADCAST = "agent_broadcast"
    RESULT_PROPOSAL = "result_proposal"  # Agent发起结果协商
    REFLECTION_RESULT = "reflection_result"


@dataclass
class Message:
    """总线消息"""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: MessageType = MessageType.AGENT_MESSAGE
    sender: str = ""
    receiver: str = ""  # 空字符串表示广播
    topic: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class TaskSnapshot:
    """任务快照 — 持久化用"""
    task_id: str
    original_request: str
    status: str = "pending"
    collaboration_mode: str = ""
    assigned_agents: Dict[str, str] = field(default_factory=dict)
    partial_results: Dict[str, Any] = field(default_factory=dict)
    final_result: Optional[Any] = None
    decision_log: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class SharedBus:
    """共享总线 — 全局单例"""

    def __init__(self):
        # 订阅表: topic -> set of callback refs
        self._subscriptions: Dict[str, Set[Callable]] = defaultdict(set)
        # 直接消息队列: receiver_id -> list of Message
        self._direct_queues: Dict[str, asyncio.Queue] = {}
        # 共享内存（只读）
        self._shared_context: Dict[str, Any] = {}
        # 任务快照
        self._task_snapshots: Dict[str, TaskSnapshot] = {}
        # 锁
        self._lock = asyncio.Lock()

    # ─── 消息通信 ───────────────────────────────────────────

    async def publish(self, topic: str, message: Message) -> None:
        """发布消息到主题 — 所有订阅者收到（支持通配符订阅）"""
        async with self._lock:
            # 获取精确匹配的订阅者
            callbacks = self._subscriptions.get(topic, set()).copy()
            
            # 查找通配符匹配的订阅者（支持 * 通配符）
            for subscribed_topic in self._subscriptions:
                if subscribed_topic != topic and self._matches_wildcard(subscribed_topic, topic):
                    callbacks.update(self._subscriptions[subscribed_topic])
        
        for cb in callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(message)
                else:
                    cb(message)
            except Exception as e:
                logger.warning(f"SharedBus 订阅者回调失败: {e}")
    
    def _matches_wildcard(self, pattern: str, topic: str) -> bool:
        """检查主题是否匹配通配符模式

        支持的通配符:
        - * 匹配任意字符序列（含 :）

        示例:
        - agent:*:reflect 匹配 agent:abc123:reflect
        - *:reflect 匹配 agent:abc:reflect, task:123:reflect
        """
        import re
        regex = re.escape(pattern).replace(r'\*', '.*')
        return bool(re.fullmatch(regex, topic))

    async def subscribe(self, topic: str, callback: Callable) -> None:
        """订阅主题"""
        async with self._lock:
            self._subscriptions[topic].add(callback)

    async def unsubscribe(self, topic: str, callback: Callable) -> None:
        """取消订阅"""
        async with self._lock:
            self._subscriptions[topic].discard(callback)

    async def send_direct(self, receiver: str, message: Message) -> None:
        """发送直接消息 — 接收者从自己的队列消费"""
        async with self._lock:
            if receiver not in self._direct_queues:
                self._direct_queues[receiver] = asyncio.Queue()
            queue = self._direct_queues[receiver]
        await queue.put(message)

    async def receive_direct(self, agent_id: str, timeout: float = 5.0) -> Optional[Message]:
        """消费直接消息（非阻塞）"""
        async with self._lock:
            queue = self._direct_queues.get(agent_id)
        if queue is None:
            return None
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    # ─── 共享内存（只读） ──────────────────────────────────

    async def update_context(self, key: str, value: Any) -> None:
        """更新共享上下文"""
        async with self._lock:
            self._shared_context[key] = value

    async def get_context(self, key: str, default: Any = None) -> Any:
        """读取共享上下文"""
        return self._shared_context.get(key, default)

    async def get_all_context(self) -> Dict[str, Any]:
        """读取全部共享上下文"""
        return dict(self._shared_context)

    # ─── 任务快照 ──────────────────────────────────────────

    async def save_snapshot(self, snapshot: TaskSnapshot) -> None:
        """保存任务快照"""
        snapshot.updated_at = time.time()
        async with self._lock:
            self._task_snapshots[snapshot.task_id] = snapshot

    async def get_snapshot(self, task_id: str) -> Optional[TaskSnapshot]:
        """获取任务快照"""
        return self._task_snapshots.get(task_id)

    async def append_decision(self, task_id: str, decision: Dict[str, Any]) -> None:
        """追加决策日志"""
        async with self._lock:
            snap = self._task_snapshots.get(task_id)
            if snap:
                snap.decision_log.append({**decision, "timestamp": time.time()})
                snap.updated_at = time.time()

    async def list_active_tasks(self) -> List[str]:
        """列出活跃任务ID"""
        return [
            tid for tid, snap in self._task_snapshots.items()
            if snap.status in ("running", "scheduled")
        ]


# 全局单例
_shared_bus: Optional[SharedBus] = None


def get_shared_bus() -> SharedBus:
    """获取全局 SharedBus 实例"""
    global _shared_bus
    if _shared_bus is None:
        _shared_bus = SharedBus()
    return _shared_bus
