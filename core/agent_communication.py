"""Agent通信模块 - 实现真正的Agent间主动通信

提供：
1. Agent消息路由
2. 主题订阅/发布
3. 请求-响应模式
4. Agent发现机制
5. 对话上下文管理
"""

import asyncio
import logging
from typing import Dict, Any, Callable, Optional, List
from collections import defaultdict
import uuid

logger = logging.getLogger(__name__)


class AgentMessage:
    """Agent消息结构"""
    
    def __init__(self, sender: str, receiver: str, content: Any, 
                 message_type: str = "inform", context: Dict = None):
        self.id = str(uuid.uuid4())
        self.sender = sender
        self.receiver = receiver
        self.content = content
        self.message_type = message_type  # inform, request, response, broadcast
        self.context = context or {}
        self.timestamp = asyncio.get_event_loop().time()
    
    def to_dict(self):
        return {
            "id": self.id,
            "sender": self.sender,
            "receiver": self.receiver,
            "content": self.content,
            "message_type": self.message_type,
            "context": self.context,
            "timestamp": self.timestamp
        }


class AgentCommunicationCenter:
    """Agent通信中心 - 管理所有Agent间通信"""
    
    def __init__(self):
        # 主题订阅者: topic -> [(agent_id, callback)]
        self._topic_subscribers = defaultdict(list)
        # Agent注册: agent_id -> {name, type, status, callbacks}
        self._registered_agents = {}
        # 对话上下文: conversation_id -> messages
        self._conversations = {}
        # Agent在线状态
        self._agent_status = {}
        
        logger.info("Agent通信中心初始化完成")
    
    async def register_agent(self, agent_id: str, agent_name: str, agent_type: str, 
                           callbacks: Dict[str, Callable] = None):
        """注册Agent"""
        self._registered_agents[agent_id] = {
            "name": agent_name,
            "type": agent_type,
            "callbacks": callbacks or {}
        }
        self._agent_status[agent_id] = "online"
        logger.info(f"Agent已注册: {agent_id} ({agent_name})")
    
    async def unregister_agent(self, agent_id: str):
        """注销Agent"""
        if agent_id in self._registered_agents:
            del self._registered_agents[agent_id]
            del self._agent_status[agent_id]
            logger.info(f"Agent已注销: {agent_id}")
    
    async def subscribe(self, agent_id: str, topic: str, callback: Callable):
        """订阅主题"""
        if agent_id not in self._registered_agents:
            await self.register_agent(agent_id, agent_id, "unknown")
        
        self._topic_subscribers[topic].append((agent_id, callback))
        logger.info(f"Agent {agent_id} 订阅主题: {topic}")
    
    async def unsubscribe(self, agent_id: str, topic: str):
        """取消订阅主题"""
        self._topic_subscribers[topic] = [
            (aid, cb) for aid, cb in self._topic_subscribers[topic] 
            if aid != agent_id
        ]
    
    async def publish(self, topic: str, message: Dict[str, Any], sender: str = None):
        """发布消息到主题"""
        subscribers = self._topic_subscribers.get(topic, [])
        if not subscribers:
            logger.debug(f"主题 {topic} 没有订阅者")
            return
        
        logger.info(f"发布消息到主题 {topic}，{len(subscribers)} 个订阅者")
        
        tasks = []
        for agent_id, callback in subscribers:
            # 跳过发送者自己
            if sender and agent_id == sender:
                continue
            task = asyncio.create_task(self._safe_callback(callback, message, agent_id))
            tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def send_direct(self, sender: str, receiver: str, content: Any, 
                        message_type: str = "inform"):
        """直接发送消息给指定Agent"""
        if receiver not in self._registered_agents:
            logger.warning(f"目标Agent不存在: {receiver}")
            return None
        
        message = AgentMessage(
            sender=sender,
            receiver=receiver,
            content=content,
            message_type=message_type
        )
        
        # 获取接收者的消息回调
        agent_info = self._registered_agents[receiver]
        if "message_received" in agent_info["callbacks"]:
            callback = agent_info["callbacks"]["message_received"]
            await self._safe_callback(callback, message.to_dict(), receiver)
        
        logger.info(f"消息已发送: {sender} -> {receiver}")
        return message.id
    
    async def broadcast(self, sender: str, content: Any):
        """广播消息给所有Agent"""
        message = AgentMessage(
            sender=sender,
            receiver="*",
            content=content,
            message_type="broadcast"
        )
        
        await self.publish("broadcast", message.to_dict(), sender)
    
    async def request(self, sender: str, receiver: str, content: Any, 
                    timeout: int = 30) -> Optional[Dict[str, Any]]:
        """请求-响应模式"""
        request_id = str(uuid.uuid4())
        
        response_event = asyncio.Event()
        response_data = None
        
        async def response_handler(msg):
            nonlocal response_data
            if msg.get("request_id") == request_id:
                response_data = msg
                response_event.set()
        
        # 订阅响应主题
        response_topic = f"response_{request_id}"
        await self.subscribe(sender, response_topic, response_handler)
        
        try:
            # 发送请求消息
            await self.send_direct(sender, receiver, {
                "request_id": request_id,
                "content": content,
                "type": "request"
            }, message_type="request")
            
            # 等待响应
            await asyncio.wait_for(response_event.wait(), timeout=timeout)
            return response_data
            
        except asyncio.TimeoutError:
            logger.error(f"请求超时: {sender} -> {receiver}")
            return None
        finally:
            await self.unsubscribe(sender, response_topic)
    
    async def _safe_callback(self, callback: Callable, message: Dict[str, Any], agent_id: str):
        """安全执行回调"""
        try:
            await callback(message)
        except Exception as e:
            logger.error(f"Agent {agent_id} 回调执行失败: {e}")
    
    def get_online_agents(self) -> List[str]:
        """获取在线Agent列表"""
        return [aid for aid, status in self._agent_status.items() if status == "online"]
    
    def get_agent_info(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取Agent信息"""
        return self._registered_agents.get(agent_id)
    
    def get_topic_subscribers(self, topic: str) -> List[str]:
        """获取主题订阅者"""
        return [aid for aid, _ in self._topic_subscribers.get(topic, [])]


# 全局通信中心实例
communication_center = AgentCommunicationCenter()
