"""Agent间通信中心 — 支持注册、订阅、直接消息、广播、请求/响应、反问"""

import asyncio
import uuid
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 反问机制：Agent在降级前询问用户
# ──────────────────────────────────────────────

@dataclass
class PendingQuestion:
    """一个待用户回答的问题"""
    question_id: str
    agent_id: str
    agent_name: str
    question: str
    context: str
    created_at: float = field(default_factory=time.time)
    options: list = field(default_factory=lambda: [
        {"label": "继续（降级处理）", "value": "proceed"},
        {"label": "重试", "value": "retry"},
        {"label": "取消", "value": "cancel"},
    ])


class QuestionRegistry:
    """全局待回答问题注册表"""

    def __init__(self):
        self._questions: Dict[str, PendingQuestion] = {}
        self._futures: Dict[str, asyncio.Future] = {}

    def ask(
        self,
        agent_id: str,
        agent_name: str,
        question: str,
        context: str = "",
        timeout: int = 60,
    ) -> asyncio.Future:
        """注册一个问题，返回一个Future等待用户回答"""
        qid = str(uuid.uuid4())
        self._questions[qid] = PendingQuestion(
            question_id=qid,
            agent_id=agent_id,
            agent_name=agent_name,
            question=question,
            context=context,
        )
        future = asyncio.get_event_loop().create_future()
        self._futures[qid] = future

        # 超时自动取消
        asyncio.get_event_loop().call_later(timeout, self._timeout, qid)

        logger.info(f"[反问] Agent {agent_name} 提问: {question}")
        return future

    def _timeout(self, qid: str) -> None:
        future = self._futures.pop(qid, None)
        self._questions.pop(qid, None)
        if future and not future.done():
            future.set_result(None)  # 超时 = None

    def answer(self, qid: str, answer: str) -> bool:
        """用户回答一个问题"""
        future = self._futures.pop(qid, None)
        self._questions.pop(qid, None)
        if future and not future.done():
            future.set_result(answer)
            logger.info(f"[反问] 用户回答 {qid}: {answer}")
            return True
        return False

    def get_pending(self) -> List[PendingQuestion]:
        """获取所有待回答问题"""
        return list(self._questions.values())

    def get_question(self, qid: str) -> Optional[PendingQuestion]:
        return self._questions.get(qid)


# 全局单例
_question_registry: Optional[QuestionRegistry] = None


def get_question_registry() -> QuestionRegistry:
    global _question_registry
    if _question_registry is None:
        _question_registry = QuestionRegistry()
    return _question_registry


class CommunicationCenter:
    """Agent间通信中心 — 支持消息通信 + 知识共享"""

    def __init__(self):
        self._agents: Dict[str, dict] = {}           # agent_id → info
        self._callbacks: Dict[str, dict] = {}         # agent_id → {event: callback}
        self._topics: Dict[str, list] = {}            # topic → [(agent_id, callback)]
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._message_queues: Dict[str, asyncio.Queue] = {}  # agent_id → 消息队列
        self._lock = asyncio.Lock()
        # 知识存储（与 SharedBus 同步）
        self._knowledge_store: Dict[str, Any] = {}
        self._knowledge_tags: Dict[str, set] = {}
        self._knowledge_meta: Dict[str, dict] = {}

    def _safe_create_task(self, coro) -> Optional[asyncio.Task]:
        """安全创建异步任务，避免异常被静默吞没"""
        if coro is None:
            return None
        if not asyncio.iscoroutine(coro):
            # 如果不是协程，直接调用
            try:
                coro()
            except Exception as e:
                logger.error("同步回调执行失败: %s", e)
            return None
        task = asyncio.create_task(coro)

        def _log_exception(fut: asyncio.Future) -> None:
            if not fut.cancelled() and fut.exception() is not None:
                logger.error(
                    "异步任务异常: %s", fut.exception(), exc_info=fut.exception()
                )

        task.add_done_callback(_log_exception)
        return task

    async def register_agent(
        self,
        agent_id: str,
        agent_name: str,
        agent_type: str,
        callbacks: Optional[Dict[str, Callable]] = None
    ) -> None:
        """注册Agent到通信中心"""
        async with self._lock:
            self._agents[agent_id] = {
                "agent_id": agent_id,
                "agent_name": agent_name,
                "agent_type": agent_type,
                "registered_at": time.time(),
                "online": True,
            }
            if callbacks:
                self._callbacks[agent_id] = callbacks
            # 创建消息队列
            if agent_id not in self._message_queues:
                self._message_queues[agent_id] = asyncio.Queue()
        logger.info(f"Agent注册: {agent_id} ({agent_type})")

    async def unregister_agent(self, agent_id: str) -> None:
        """注销Agent"""
        async with self._lock:
            if agent_id in self._agents:
                self._agents[agent_id]["online"] = False
            self._callbacks.pop(agent_id, None)
            self._message_queues.pop(agent_id, None)
        logger.info(f"Agent注销: {agent_id}")

    async def subscribe(self, agent_id: str, topic: str, callback: Callable) -> None:
        """订阅主题"""
        if topic not in self._topics:
            self._topics[topic] = []
        self._topics[topic].append((agent_id, callback))
        logger.debug(f"Agent {agent_id} 订阅主题: {topic}")

    async def send_direct(
        self,
        sender: str,
        receiver: str,
        content: Any,
        message_type: str = "inform"
    ) -> str:
        """发送直接消息到指定Agent（同时投递到回调和队列）"""
        message_id = str(uuid.uuid4())
        message = {
            "id": message_id,
            "sender": sender,
            "receiver": receiver,
            "content": content,
            "message_type": message_type,
            "timestamp": time.time()
        }
        # 1. 投递到接收方的回调
        cb = self._callbacks.get(receiver, {})
        handler = cb.get("message_received")
        if handler:
            self._safe_create_task(handler(message))
        
        # 2. 投递到接收方的消息队列
        queue = self._message_queues.get(receiver)
        if queue:
            await queue.put(message)
        
        logger.debug(f"消息投递: {sender} → {receiver} ({message_type})")
        return message_id

    async def receive_message(self, agent_id: str, timeout: float = 5.0) -> Optional[dict]:
        """从消息队列接收消息（非阻塞）"""
        queue = self._message_queues.get(agent_id)
        if queue is None:
            return None
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def receive_all_messages(self, agent_id: str) -> List[dict]:
        """接收所有待处理消息"""
        queue = self._message_queues.get(agent_id)
        if queue is None:
            return []
        messages = []
        while not queue.empty():
            try:
                messages.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return messages

    async def publish(self, topic: str, message: dict, sender: str) -> None:
        """发布消息到主题"""
        subscribers = self._topics.get(topic, [])
        if not subscribers:
            logger.debug(f"主题 {topic} 无订阅者")
            return
        for agent_id, callback in subscribers:
            if agent_id != sender:  # 不发给自己
                self._safe_create_task(callback(message))

    async def broadcast(self, sender: str, content: Any) -> None:
        """广播消息给所有Agent"""
        message = {
            "sender": sender,
            "content": content,
            "timestamp": time.time()
        }
        for agent_id, cb in self._callbacks.items():
            if agent_id != sender:
                handler = cb.get("message_received")
                if handler:
                    self._safe_create_task(handler(message))

    async def request(
        self,
        sender: str,
        receiver: str,
        content: Any,
        timeout: int = 30
    ) -> Optional[Dict[str, Any]]:
        """请求-响应模式"""
        request_id = str(uuid.uuid4())
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        message = {
            "id": request_id,
            "sender": sender,
            "receiver": receiver,
            "content": content,
            "message_type": "request",
            "timestamp": time.time()
        }

        cb = self._callbacks.get(receiver, {})
        handler = cb.get("message_received")
        if not handler:
            self._pending_requests.pop(request_id, None)
            return None

        self._safe_create_task(self._deliver_and_wait(handler, message, request_id, timeout))
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            return None

    async def _deliver_and_wait(
        self, handler: Callable, message: dict, request_id: str, timeout: int
    ) -> None:
        """投递请求并等待响应"""
        try:
            await handler(message)
        except Exception as e:
            future = self._pending_requests.get(request_id)
            if future and not future.done():
                future.set_exception(e)

    def resolve_request(self, request_id: str, result: Any) -> None:
        """完成一个待处理的请求"""
        future = self._pending_requests.pop(request_id, None)
        if future and not future.done():
            future.set_result(result)

    def get_online_agents(self) -> List[str]:
        """获取已注册的Agent列表"""
        return list(self._agents.keys())

    def get_agent_info(self, agent_id: str) -> Optional[dict]:
        """获取Agent信息"""
        return self._agents.get(agent_id)

    async def send(self, message) -> bool:
        """兼容旧接口：发送消息"""
        if hasattr(message, "sender") and hasattr(message, "receiver"):
            await self.send_direct(
                sender=message.sender,
                receiver=message.receiver,
                content=message.content,
                message_type=getattr(message, "msg_type", "text")
            )
            return True
        return False

    async def receive(self, timeout: float = 5.0) -> Optional[Any]:
        """兼容旧接口：接收消息（简化版，返回None）"""
        await asyncio.sleep(0)
        return None

    # ─── 知识存储（与 SharedBus 同步）──────────────────────────

    async def store_knowledge(self, key: str, data: Any,
                              tags: Optional[set] = None,
                              source: str = "",
                              summary: str = "") -> None:
        """存储共享知识 — 供其他 Agent 查询使用"""
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
        logger.debug(f"知识已存储: {key} (tags={tags or 'none'})")

    async def get_knowledge(self, key: str) -> Optional[Any]:
        """获取指定键名的共享知识"""
        async with self._lock:
            return self._knowledge_store.get(key)

    async def search_knowledge(self, tag: str) -> Dict[str, Any]:
        """按标签搜索共享知识"""
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
        """列出所有共享知识"""
        async with self._lock:
            return {
                k: {
                    "summary": self._knowledge_meta.get(k, {}).get("summary", ""),
                    "tags": list(self._knowledge_tags.get(k, set())),
                    "source": self._knowledge_meta.get(k, {}).get("source", ""),
                }
                for k in self._knowledge_store
            }

    async def clear_knowledge(self) -> None:
        """清空所有共享知识"""
        async with self._lock:
            self._knowledge_store.clear()
            self._knowledge_tags.clear()
            self._knowledge_meta.clear()
        logger.info("共享知识已清空")

    def get_online_agents(self) -> List[str]:
        """获取已注册的Agent列表"""
        return [aid for aid, info in self._agents.items() if info.get("online", False)]


# 全局单例
_center: Optional[CommunicationCenter] = None


def get_communication_center() -> CommunicationCenter:
    global _center
    if _center is None:
        _center = CommunicationCenter()
    return _center


communication_center = get_communication_center()
