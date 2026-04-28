"""测试多角色独立智能体系统"""

import asyncio
import logging
from .multi_agent_system import agent_scheduler

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_single_task():
    """测试单个任务"""
    logger.info("=== 测试单个任务 ===")
    
    # 启动所有Agent
    await agent_scheduler.start()
    
    try:
        # 测试检查Agent
        logger.info("测试检查Agent...")
        result = await agent_scheduler.submit_task(
            "check",
            {"url": "https://example.com"}
        )
        logger.info(f"检查任务提交结果: {result}")
        
        # 等待任务完成
        await asyncio.sleep(2)
        
        # 获取任务状态
        task_status = await agent_scheduler.get_task_status(
            result["task_id"],
            result["agent_type"]
        )
        logger.info(f"任务状态: {task_status}")
        
    finally:
        # 停止所有Agent
        await agent_scheduler.stop()


async def test_concurrent_tasks():
    """测试并发任务"""
    logger.info("\n=== 测试并发任务 ===")
    
    # 启动所有Agent
    await agent_scheduler.start()
    
    try:
        # 提交多个任务
        tasks = []
        
        # 提交检查任务
        for i in range(3):
            task = agent_scheduler.submit_task(
                "check",
                {"url": f"https://example.com/{i}"}
            )
            tasks.append(task)
        
        # 提交爬虫任务
        for i in range(3):
            task = agent_scheduler.submit_task(
                "scrape",
                {"url": f"https://example.com/{i}"}
            )
            tasks.append(task)
        
        # 提交漏洞扫描任务
        for i in range(2):
            task = agent_scheduler.submit_task(
                "scan",
                {"target": f"192.168.1.{i}"}
            )
            tasks.append(task)
        
        # 提交总结任务
        for i in range(2):
            task = agent_scheduler.submit_task(
                "summarize",
                {"text": f"这是测试文本 {i}\n" * 10}
            )
            tasks.append(task)
        
        # 等待所有任务提交完成
        results = await asyncio.gather(*tasks)
        logger.info(f"共提交 {len(results)} 个任务")
        
        # 等待所有任务执行完成
        await asyncio.sleep(5)
        
        # 检查任务状态
        for result in results:
            task_status = await agent_scheduler.get_task_status(
                result["task_id"],
                result["agent_type"]
            )
            logger.info(f"任务 {result['task_id']} ({result['agent_type']}) 状态: {task_status.status.value}")
        
    finally:
        # 停止所有Agent
        await agent_scheduler.stop()


async def test_agent_info():
    """测试Agent信息"""
    logger.info("\n=== 测试Agent信息 ===")
    
    # 启动所有Agent
    await agent_scheduler.start()
    
    try:
        # 获取Agent信息
        info = agent_scheduler.get_agent_info()
        logger.info(f"Agent信息: {info}")
        
    finally:
        # 停止所有Agent
        await agent_scheduler.stop()


async def test_error_handling():
    """测试错误处理"""
    logger.info("\n=== 测试错误处理 ===")
    
    # 启动所有Agent
    await agent_scheduler.start()
    
    try:
        # 提交一个未知类型的任务
        try:
            await agent_scheduler.submit_task(
                "unknown",
                {"param": "value"}
            )
        except ValueError as e:
            logger.info(f"预期的错误: {e}")
        
        # 提交一个参数错误的任务
        result = await agent_scheduler.submit_task(
            "check",
            {}
        )
        
        # 等待任务完成
        await asyncio.sleep(2)
        
        # 获取任务状态
        task_status = await agent_scheduler.get_task_status(
            result["task_id"],
            result["agent_type"]
        )
        logger.info(f"参数错误任务状态: {task_status}")
        
    finally:
        # 停止所有Agent
        await agent_scheduler.stop()


async def main():
    """主测试函数"""
    # 测试单个任务
    await test_single_task()
    
    # 测试并发任务
    await test_concurrent_tasks()
    
    # 测试Agent信息
    await test_agent_info()
    
    # 测试错误处理
    await test_error_handling()
    
    logger.info("\n=== 所有测试完成 ===")


if __name__ == "__main__":
    asyncio.run(main())