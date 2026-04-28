"""测试人物SKILL功能"""

import asyncio
import logging
from .multi_agent_system import agent_scheduler

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_character_skills():
    """测试人物SKILL"""
    logger.info("=== 测试人物SKILL ===")
    
    # 启动所有Agent
    await agent_scheduler.start()
    
    try:
        # 测试各个人物SKILL
        character_tasks = [
            ("bestfriend", {"message": "你好，闺蜜"}),
            ("first_love", {"message": "你好，初恋"}),
            ("goddess", {"message": "你好，女神"}),
            ("john_carmack", {"message": "如何优化游戏性能？"}),
            ("libai", {"message": "你好，李白"})
        ]
        
        results = []
        for character_id, params in character_tasks:
            logger.info(f"测试人物SKILL: {character_id}")
            result = await agent_scheduler.submit_task(character_id, params)
            results.append((character_id, result))
            logger.info(f"人物SKILL提交结果: {result}")
        
        # 等待任务完成
        await asyncio.sleep(2)
        
        # 获取任务状态
        for character_id, result in results:
            task_status = await agent_scheduler.get_task_status(
                result["task_id"],
                result["agent_type"]
            )
            logger.info(f"人物SKILL {character_id} 状态: {task_status.status.value}")
            if task_status.result:
                logger.info(f"人物SKILL {character_id} 结果: {task_status.result}")
        
    finally:
        # 停止所有Agent
        await agent_scheduler.stop()


async def test_character_with_agent_functions():
    """测试人物SKILL调用agent功能"""
    logger.info("\n=== 测试人物SKILL调用agent功能 ===")
    
    # 启动所有Agent
    await agent_scheduler.start()
    
    try:
        # 先执行一个检查任务
        logger.info("执行检查任务...")
        check_result = await agent_scheduler.submit_task(
            "check",
            {"url": "https://example.com"}
        )
        logger.info(f"检查任务提交结果: {check_result}")
        
        # 等待任务完成
        await asyncio.sleep(2)
        
        # 获取任务状态
        check_status = await agent_scheduler.get_task_status(
            check_result["task_id"],
            check_result["agent_type"]
        )
        logger.info(f"检查任务状态: {check_status.status.value}")
        
        # 然后测试人物SKILL
        logger.info("测试人物SKILL...")
        character_result = await agent_scheduler.submit_task(
            "bestfriend",
            {"message": "你好，闺蜜，帮我检查一下网站状态"}
        )
        logger.info(f"人物SKILL提交结果: {character_result}")
        
        # 等待任务完成
        await asyncio.sleep(2)
        
        # 获取任务状态
        character_status = await agent_scheduler.get_task_status(
            character_result["task_id"],
            character_result["agent_type"]
        )
        logger.info(f"人物SKILL状态: {character_status.status.value}")
        if character_status.result:
            logger.info(f"人物SKILL结果: {character_status.result}")
        
    finally:
        # 停止所有Agent
        await agent_scheduler.stop()


async def main():
    """主测试函数"""
    # 测试人物SKILL
    await test_character_skills()
    
    # 测试人物SKILL调用agent功能
    await test_character_with_agent_functions()
    
    logger.info("\n=== 所有测试完成 ===")


if __name__ == "__main__":
    asyncio.run(main())