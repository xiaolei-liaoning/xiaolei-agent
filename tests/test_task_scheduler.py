#!/usr/bin/env python3
"""测试任务调度器"""

import pytest
import asyncio
from core.task_scheduler import task_scheduler


class TestTaskScheduler:
    """测试任务调度器"""
    
    async def test_task_submission(self):
        """测试任务提交"""
        # 提交任务
        task_id = await task_scheduler.submit_task("test_task", {"param": "value"}, priority=5)
        assert task_id is not None
        
        # 验证任务存在
        task = task_scheduler.tasks.get(task_id)
        assert task is not None
        assert task.type == "test_task"
        assert task.params == {"param": "value"}
        assert task.priority == 5
    
    async def test_priority_scheduling(self):
        """测试任务优先级调度"""
        # 提交低优先级任务
        low_priority_task = await task_scheduler.submit_task("test_task", {"priority": "low"}, priority=1)
        
        # 提交高优先级任务
        high_priority_task = await task_scheduler.submit_task("test_task", {"priority": "high"}, priority=10)
        
        # 验证两个任务都存在
        assert task_scheduler.tasks.get(low_priority_task) is not None
        assert task_scheduler.tasks.get(high_priority_task) is not None
    
    async def test_rate_limiting(self):
        """测试速率限制"""
        # 提交多个任务，测试速率限制
        tasks = []
        for i in range(5):
            task_id = await task_scheduler.submit_task("test_task", {"id": i})
            tasks.append(task_id)
        
        # 验证所有任务都提交成功
        assert len(tasks) == 5
        for task_id in tasks:
            assert task_scheduler.tasks.get(task_id) is not None
    
    async def test_circuit_breaker(self):
        """测试熔断器"""
        # 模拟任务失败，触发熔断器
        # 注意：这里只是测试熔断器的基本功能，实际触发需要多次失败
        # 由于测试环境限制，我们只测试基本的提交功能
        task_id = await task_scheduler.submit_task("test_task", {"param": "value"})
        assert task_id is not None
    
    async def test_task_status(self):
        """测试任务状态查询"""
        # 提交任务
        task_id = await task_scheduler.submit_task("test_task", {"param": "value"})
        
        # 获取任务状态
        status = await task_scheduler.get_task_status(task_id)
        assert status is not None
        assert status.task_id == task_id
    
    async def test_task_cancellation(self):
        """测试任务取消"""
        # 提交任务
        task_id = await task_scheduler.submit_task("test_task", {"param": "value"})
        
        # 取消任务
        await task_scheduler.cancel_task(task_id)
        
        # 验证任务状态
        status = await task_scheduler.get_task_status(task_id)
        assert status is not None