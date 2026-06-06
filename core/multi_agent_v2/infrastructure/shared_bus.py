"""
SharedBus — 统一消息总线

职责：
1. 消息通信：publish/subscribe/direct 三种模式
2. Agent 间协调：任务完成通知、结果协商

合并了原有的 GlobalContextCenter（只保留数据）和 communication_center。
"""

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional, Set

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


class SharedBus:
    """共享总线 — 全局单例

    三大能力：
    1. 消息通信（publish/subscribe/direct）
    2. Agent 协调（任务通知）
    3. 共享知识存储（跨 Agent 知识沉淀）
    """

    def __init__(self):
        # 订阅表: topic -> set of callback refs
        self._subscriptions: Dict[str, Set[Callable]] = defaultdict(set)
        # 直接消息队列: receiver_id -> list of Message
        self._direct_queues: Dict[str, asyncio.Queue] = {}
        # 锁
        self._lock = asyncio.Lock()
        # ── 共享知识存储（跨 Agent 知识沉淀）──
        self._knowledge_store: Dict[str, Any] = {}
        self._knowledge_tags: Dict[str, Set[str]] = defaultdict(set)
        self._knowledge_meta: Dict[str, Dict] = {}

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

    # ─── 共享知识存储 ──────────────────────────────────────────

    async def store_knowledge(self, key: str, data: Any,
                              tags: Optional[Set[str]] = None,
                              source: str = "",
                              summary: str = "") -> None:
        """存储共享知识 — 供其他 Agent 查询使用

        Args:
            key: 知识键名（如 "search:百度热搜"、"analysis:数据摘要"）
            data: 知识数据
            tags: 标签集合，用于分类检索（如 {"search", "hot"}）
            source: 来源 Agent ID
            summary: 知识摘要（用于快速预览）
        """
        async with self._lock:
            self._knowledge_store[key] = data
            if tags:
                self._knowledge_tags[key] = tags
            self._knowledge_meta[key] = {
                "source": source,
                "summary": summary or str(data)[:200],
                "timestamp": time.time(),
                "updated_at": time.time(),
            }
        logger.debug(f"SharedBus 知识已存储: {key} (tags={tags or 'none'})")

    async def get_knowledge(self, key: str) -> Optional[Any]:
        """获取指定键名的共享知识"""
        async with self._lock:
            return self._knowledge_store.get(key)

    async def search_knowledge(self, tag: str) -> Dict[str, Any]:
        """按标签搜索共享知识 — 返回所有匹配的知识"""
        result = {}
        async with self._lock:
            for key, tags in self._knowledge_tags.items():
                if tag in tags:
                    result[key] = {
                        "data": self._knowledge_store.get(key),
                        "meta": self._knowledge_meta.get(key, {}),
                    }
        return result

    async def list_knowledge(self) -> Dict[str, Dict]:
        """列出所有共享知识及元信息"""
        async with self._lock:
            return {
                k: {
                    "summary": self._knowledge_meta.get(k, {}).get("summary", ""),
                    "tags": list(self._knowledge_tags.get(k, set())),
                    "source": self._knowledge_meta.get(k, {}).get("source", ""),
                    "updated_at": self._knowledge_meta.get(k, {}).get("updated_at", 0),
                }
                for k in self._knowledge_store
            }

    async def clear_knowledge(self) -> None:
        """清空所有共享知识（任务完成后调用）"""
        async with self._lock:
            self._knowledge_store.clear()
            self._knowledge_tags.clear()
            self._knowledge_meta.clear()
        logger.info("SharedBus 共享知识已清空")

    # 全局单例
_shared_bus: Optional[SharedBus] = None


def get_shared_bus() -> SharedBus:
    """获取全局 SharedBus 实例"""
    global _shared_bus
    if _shared_bus is None:
        _shared_bus = SharedBus()
    return _shared_bus
