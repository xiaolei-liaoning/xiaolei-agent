#!/usr/bin/env python3
"""性能测试"""

import pytest
import asyncio
import time
from core.reasoning_engine import get_reasoning_engine
from core.message_bus import message_bus
from core.task_scheduler import task_scheduler


class TestPerformance:
    """性能测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """设置测试环境"""
        self.engine = get_reasoning_engine()
    
    async def test_concurrent_requests(self):
        """测试并发请求"""
        # 定义测试问题
        test_questions = [
            '你好',
            '2026年最新的AI技术趋势是什么',
            '今天天气怎么样',
            '如何学习Python编程',
            '什么是机器学习'
        ]
        
        # 测试并发处理
        start_time = time.time()
        
        # 并发执行多个请求
        tasks = []
        for question in test_questions:
            task = self.engine.process(question)
            tasks.append(task)
        
        # 等待所有任务完成
        results = await asyncio.gather(*tasks)
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        # 验证所有请求都成功完成
        assert len(results) == len(test_questions)
        for result in results:
            assert result['final_answer'] is not None
        
        # 打印性能指标
        print(f"\n并发测试结果:")
        print(f"总请求数: {len(test_questions)}")
        print(f"总耗时: {elapsed:.2f}秒")
        print(f"平均响应时间: {elapsed/len(test_questions):.2f}秒/请求")
    
    async def test_message_bus_performance(self):
        """测试消息总线性能"""
        # 测试消息发布-订阅性能
        received_count = 0
        
        async def callback(message):
            nonlocal received_count
            received_count += 1
        
        # 订阅主题
        await message_bus.subscribe("performance_test", callback)
        
        # 测试发布100条消息
        start_time = time.time()
        
        for i in range(100):
            await message_bus.publish("performance_test", {"id": i, "message": f"Test message {i}"})
        
        # 等待消息处理
        await asyncio.sleep(0.5)
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        # 验证消息接收
        assert received_count == 100
        
        # 打印性能指标
        print(f"\n消息总线性能测试:")
        print(f"消息数量: 100")
        print(f"总耗时: {elapsed:.2f}秒")
        print(f"吞吐量: {100/elapsed:.2f}消息/秒")
        
        # 取消订阅
        await message_bus.unsubscribe("performance_test", callback)
    
    async def test_task_scheduler_performance(self):
        """测试任务调度器性能"""
        # 测试任务提交性能
        start_time = time.time()
        
        # 提交50个任务
        task_ids = []
        for i in range(50):
            task_id = await task_scheduler.submit_task("test_task", {"id": i})
            task_ids.append(task_id)
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        # 验证任务提交
        assert len(task_ids) == 50
        for task_id in task_ids:
            assert task_scheduler.tasks.get(task_id) is not None
        
        # 打印性能指标
        print(f"\n任务调度器性能测试:")
        print(f"任务数量: 50")
        print(f"总耗时: {elapsed:.2f}秒")
        print(f"吞吐量: {50/elapsed:.2f}任务/秒")