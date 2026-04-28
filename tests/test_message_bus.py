#!/usr/bin/env python3
"""测试消息总线"""

import pytest
import asyncio
from core.message_bus import message_bus


class TestMessageBus:
    """测试消息总线"""
    
    async def test_publish_subscribe(self):
        """测试发布-订阅功能"""
        received_messages = []
        
        # 定义回调函数
        async def callback(message):
            received_messages.append(message)
        
        # 订阅主题
        await message_bus.subscribe("test_topic", callback)
        
        # 发布消息
        test_message = {"key": "value", "number": 42}
        await message_bus.publish("test_topic", test_message)
        
        # 等待消息处理
        await asyncio.sleep(0.1)
        
        # 验证消息是否被接收
        assert len(received_messages) == 1
        assert received_messages[0] == test_message
        
        # 取消订阅
        await message_bus.unsubscribe("test_topic", callback)
        
        # 再次发布消息，应该不会被接收
        received_messages.clear()
        await message_bus.publish("test_topic", test_message)
        await asyncio.sleep(0.1)
        assert len(received_messages) == 0
    
    async def test_request_response(self):
        """测试请求-响应功能"""
        # 定义响应处理函数
        async def response_handler(message):
            return {"response": f"Processed: {message.get('key')}"}
        
        # 订阅响应主题
        await message_bus.subscribe("test_request", response_handler)
        
        # 发送请求并等待响应
        test_message = {"key": "test_value"}
        response = await message_bus.request_response("test_request", test_message, timeout=2)
        
        # 验证响应
        assert response is not None
        assert "response" in response
        assert response["response"] == "Processed: test_value"
        
        # 取消订阅
        await message_bus.unsubscribe("test_request", response_handler)
    
    async def test_request_timeout(self):
        """测试请求超时"""
        # 发送请求到不存在的主题
        test_message = {"key": "test_value"}
        
        # 应该抛出超时异常
        with pytest.raises(TimeoutError):
            await message_bus.request_response("non_existent_topic", test_message, timeout=0.5)
    
    async def test_multiple_subscribers(self):
        """测试多个订阅者"""
        received_messages_1 = []
        received_messages_2 = []
        
        async def callback1(message):
            received_messages_1.append(message)
        
        async def callback2(message):
            received_messages_2.append(message)
        
        # 两个订阅者订阅同一主题
        await message_bus.subscribe("multi_topic", callback1)
        await message_bus.subscribe("multi_topic", callback2)
        
        # 发布消息
        test_message = {"key": "multi_value"}
        await message_bus.publish("multi_topic", test_message)
        
        # 等待消息处理
        await asyncio.sleep(0.1)
        
        # 验证两个订阅者都收到了消息
        assert len(received_messages_1) == 1
        assert len(received_messages_2) == 1
        assert received_messages_1[0] == test_message
        assert received_messages_2[0] == test_message
        
        # 取消订阅
        await message_bus.unsubscribe("multi_topic", callback1)
        await message_bus.unsubscribe("multi_topic", callback2)