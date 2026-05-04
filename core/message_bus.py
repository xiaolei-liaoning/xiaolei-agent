"""消息总线模块

实现Agent之间的双向通信和消息传递
支持发布-订阅模式和请求-响应模式
"""

import asyncio
import logging
import json
from typing import Dict, Any, Callable, Optional
from collections import defaultdict
import uuid

logger = logging.getLogger(__name__)


class MessageBus:
    """消息总线"""
    
    def __init__(self):
        self._subscribers = {}
        self._request_responses = {}
        # ✅ 优化：按主题分锁，减少锁竞争
        self._topic_locks = defaultdict(asyncio.Lock)
        logger.info("消息总线初始化完成")
    
    async def publish(self, topic: str, message: Dict[str, Any]):
        """发布消息到指定主题
        
        Args:
            topic: 主题名称
            message: 消息内容
        """
        # ✅ 优化：只锁定当前主题，而非全局锁
        async with self._topic_locks[topic]:
            if topic not in self._subscribers:
                return
            
            subscribers = self._subscribers[topic]
            logger.info(f"发布消息到主题 {topic}，{len(subscribers)} 个订阅者")
            
            # 异步通知所有订阅者
            tasks = []
            for callback in subscribers:
                task = asyncio.create_task(self._safe_callback(callback, message))
                tasks.append(task)
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    async def subscribe(self, topic: str, callback: Callable[[Dict[str, Any]], None]):
        """订阅指定主题的消息
        
        Args:
            topic: 主题名称
            callback: 回调函数
        """
        # ✅ 优化：只锁定当前主题
        async with self._topic_locks[topic]:
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            
            if callback not in self._subscribers[topic]:
                self._subscribers[topic].append(callback)
                logger.info(f"订阅主题 {topic} 成功")
    
    async def unsubscribe(self, topic: str, callback: Callable[[Dict[str, Any]], None]):
        """取消订阅
        
        Args:
            topic: 主题名称
            callback: 回调函数
        """
        # ✅ 优化：只锁定当前主题
        async with self._topic_locks[topic]:
            if topic in self._subscribers:
                if callback in self._subscribers[topic]:
                    self._subscribers[topic].remove(callback)
                    logger.info(f"取消订阅主题 {topic} 成功")
    
    async def request_response(self, topic: str, message: Dict[str, Any], timeout: int = 5) -> Dict[str, Any]:
        """请求-响应模式
        
        Args:
            topic: 主题名称
            message: 消息内容
            timeout: 超时时间（秒）
            
        Returns:
            响应消息
        """
        request_id = str(uuid.uuid4())
        message['request_id'] = request_id
        
        # 创建响应事件
        response_event = asyncio.Event()
        response_data = None
        
        # 注册响应回调
        async def response_callback(response: Dict[str, Any]):
            nonlocal response_data
            if response.get('request_id') == request_id:
                response_data = response
                response_event.set()
        
        # 订阅响应主题
        response_topic = f"{topic}_response"
        await self.subscribe(response_topic, response_callback)
        
        try:
            # 发布请求
            await self.publish(topic, message)
            
            # 等待响应
            await asyncio.wait_for(response_event.wait(), timeout=timeout)
            
            if response_data:
                return response_data
            else:
                raise TimeoutError("未收到响应")
        except asyncio.TimeoutError:
            logger.error(f"请求 {request_id} 超时")
            raise
        finally:
            # 取消订阅
            await self.unsubscribe(response_topic, response_callback)
    
    async def _safe_callback(self, callback: Callable[[Dict[str, Any]], None], message: Dict[str, Any]):
        """安全执行回调
        
        Args:
            callback: 回调函数
            message: 消息内容
        """
        try:
            await callback(message)
        except Exception as e:
            logger.error(f"回调执行失败: {e}")
    
    def get_subscriber_count(self, topic: str) -> int:
        """获取主题的订阅者数量
        
        Args:
            topic: 主题名称
            
        Returns:
            订阅者数量
        """
        if topic in self._subscribers:
            return len(self._subscribers[topic])
        return 0
    
    def get_topics(self) -> list:
        """获取所有主题
        
        Returns:
            主题列表
        """
        return list(self._subscribers.keys())


# 全局消息总线实例
message_bus = MessageBus()