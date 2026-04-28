#!/usr/bin/env python3
"""测试配置文件"""

import pytest
import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message_bus import message_bus
from core.task_scheduler import task_scheduler
from core.reasoning_engine import get_reasoning_engine


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def setup_test_environment():
    """设置测试环境"""
    # 启动消息总线
    await message_bus.start()
    # 启动任务调度器
    await task_scheduler.start()
    
    yield
    
    # 清理测试环境
    await task_scheduler.stop()
    await message_bus.stop()


@pytest.fixture(scope="session")
async def reasoning_engine():
    """获取深度思考引擎实例"""
    return get_reasoning_engine()


@pytest.fixture(scope="session")
async def agent_coordinator():
    """获取Agent协调器实例"""
    from core.agent_coordinator import get_agent_coordinator
    coordinator = get_agent_coordinator()
    await coordinator.start()
    yield coordinator
    await coordinator.stop()