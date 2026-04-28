#!/usr/bin/env python3
"""
测试新的Agent类型和监控功能
"""

import pytest
import asyncio
import logging
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.multi_agent_system import agent_scheduler
from core.monitoring import monitoring_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
async def setup_agents():
    """设置Agent环境"""
    # 启动所有Agent
    await agent_scheduler.start()
    logger.info("所有Agent已启动")
    
    # 等待Agent启动完成
    await asyncio.sleep(1)
    
    yield
    
    # 停止所有Agent
    await agent_scheduler.stop()
    logger.info("所有Agent已停止")


@pytest.fixture(scope="module")
async def setup_monitoring():
    """设置监控环境"""
    # 启动监控
    monitoring_manager.start()
    logger.info("监控已启动")
    
    yield
    
    # 停止监控
    monitoring_manager.stop()
    logger.info("监控已停止")


@pytest.mark.asyncio
async def test_data_analysis_agent():
    """测试数据分析Agent"""
    logger.info("测试数据分析Agent...")
    
    # 启动所有Agent
    await agent_scheduler.start()
    
    try:
        # 测试数据分析任务
        analyze_result = await agent_scheduler.submit_task(
            task_type="analyze",
            params={"data": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]}
        )
        assert analyze_result["success"] is True
        assert "task_id" in analyze_result["data"]
        assert analyze_result["data"]["agent_type"] == "data_analysis"
        logger.info(f"数据分析任务提交成功: {analyze_result}")
        
        # 测试数据可视化任务
        visualize_result = await agent_scheduler.submit_task(
            task_type="visualize",
            params={"data": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]}
        )
        assert visualize_result["success"] is True
        assert "task_id" in visualize_result["data"]
        assert visualize_result["data"]["agent_type"] == "data_analysis"
        logger.info(f"数据可视化任务提交成功: {visualize_result}")
        
        # 等待任务执行完成
        await asyncio.sleep(3)
    finally:
        # 停止所有Agent
        await agent_scheduler.stop()


@pytest.mark.asyncio
async def test_nlp_agent():
    """测试自然语言处理Agent"""
    logger.info("测试自然语言处理Agent...")
    
    # 启动所有Agent
    await agent_scheduler.start()
    
    try:
        # 测试情感分析任务
        sentiment_result = await agent_scheduler.submit_task(
            task_type="sentiment",
            params={"text": "我很高兴今天天气很好，心情非常愉快！"}
        )
        assert sentiment_result["success"] is True
        assert "task_id" in sentiment_result["data"]
        assert sentiment_result["data"]["agent_type"] == "nlp"
        logger.info(f"情感分析任务提交成功: {sentiment_result}")
        
        # 测试命名实体识别任务
        ner_result = await agent_scheduler.submit_task(
            task_type="ner",
            params={"text": "张三在北京工作，李四在上海生活。"}
        )
        assert ner_result["success"] is True
        assert "task_id" in ner_result["data"]
        assert ner_result["data"]["agent_type"] == "nlp"
        logger.info(f"命名实体识别任务提交成功: {ner_result}")
        
        # 测试翻译任务
        translation_result = await agent_scheduler.submit_task(
            task_type="translation",
            params={"text": "我爱我的祖国", "target_language": "en"}
        )
        assert translation_result["success"] is True
        assert "task_id" in translation_result["data"]
        assert translation_result["data"]["agent_type"] == "nlp"
        logger.info(f"翻译任务提交成功: {translation_result}")
        
        # 等待任务执行完成
        await asyncio.sleep(3)
    finally:
        # 停止所有Agent
        await agent_scheduler.stop()


@pytest.mark.asyncio
async def test_monitoring():
    """测试监控功能"""
    logger.info("测试监控功能...")
    
    # 启动监控
    monitoring_manager.start()
    
    try:
        # 等待一段时间，让监控收集数据
        await asyncio.sleep(2)
        
        # 获取监控摘要
        summary = monitoring_manager.get_summary()
        assert isinstance(summary, dict)
        assert "cpu" in summary
        assert "memory" in summary
        assert "disk" in summary
        logger.info(f"监控摘要获取成功: {summary}")
        
        # 保存监控数据
        monitoring_manager.save_metrics()
        logger.info("监控数据保存成功")
    finally:
        # 停止监控
        monitoring_manager.stop()


@pytest.mark.asyncio
async def test_agent_info():
    """测试获取Agent信息"""
    logger.info("测试获取Agent信息...")
    
    # 启动所有Agent
    await agent_scheduler.start()
    
    try:
        # 获取所有Agent信息
        agent_info = agent_scheduler.get_agent_info()
        assert isinstance(agent_info, dict)
        assert "checker" in agent_info
        assert "scraper" in agent_info
        assert "vulnerability" in agent_info
        assert "summarizer" in agent_info
        assert "data_analysis" in agent_info
        assert "nlp" in agent_info
        logger.info(f"Agent信息获取成功: {agent_info}")
    finally:
        # 停止所有Agent
        await agent_scheduler.stop()


@pytest.mark.asyncio
async def test_all_tasks():
    """测试获取所有任务"""
    logger.info("测试获取所有任务...")
    
    # 启动所有Agent
    await agent_scheduler.start()
    
    try:
        # 获取所有任务
        all_tasks = agent_scheduler.get_all_tasks()
        assert isinstance(all_tasks, dict)
        assert "checker" in all_tasks
        assert "scraper" in all_tasks
        assert "vulnerability" in all_tasks
        assert "summarizer" in all_tasks
        assert "data_analysis" in all_tasks
        assert "nlp" in all_tasks
        logger.info(f"所有任务获取成功: {all_tasks}")
    finally:
        # 停止所有Agent
        await agent_scheduler.stop()


if __name__ == "__main__":
    asyncio.run(test_data_analysis_agent())
    asyncio.run(test_nlp_agent())
    asyncio.run(test_monitoring())
    asyncio.run(test_agent_info())
    asyncio.run(test_all_tasks())