"""性能优化工具使用示例

本文件展示如何使用项目中新增加的性能优化工具：
1. 超时重试装饰器
2. 资源监控
3. 延迟加载
4. 进度追踪

运行前请确保：
- 已安装可选依赖：pip install psutil
- 已配置环境变量（见.env.example）
"""
import asyncio
import logging
from typing import Dict, Any

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def example_1_basic_usage():
    """示例 1: 基本使用 - 导入和获取工具实例"""
    logger.info("=" * 60)
    logger.info("示例 1: 基本使用")
    logger.info("=" * 60)
    
    try:
        from core.performance_utils import (
            get_resource_monitor,
            get_lazy_loader,
            get_progress_tracker,
            async_retry,
            async_with_timeout,
            RetryConfig
        )
        
        # 获取工具实例
        resource_monitor = get_resource_monitor()
        lazy_loader = get_lazy_loader()
        progress_tracker = get_progress_tracker()
        
        logger.info("✅ 所有工具导入成功!")
        logger.info(f"   Resource Monitor: {resource_monitor}")
        logger.info(f"   Lazy Loader: {lazy_loader}")
        logger.info(f"   Progress Tracker: {progress_tracker}")
        
    except Exception as e:
        logger.error(f"❌ 导入失败: {e}")

async def example_2_resource_monitor():
    """示例 2: 资源监控"""
    logger.info("\n" + "=" * 60)
    logger.info("示例 2: 资源监控")
    logger.info("=" * 60)
    
    try:
        from core.performance_utils import get_resource_monitor
        
        monitor = get_resource_monitor()
        
        # 检查资源状态
        status = monitor.check_resources()
        logger.info(f"📊 资源状态: {status}")
        
        if status.get("status") == "warning":
            logger.warning("⚠️  检测到资源告警!")
        
    except ImportError:
        logger.warning("⚠️  未安装psutil，请运行: pip install psutil")
    except Exception as e:
        logger.error(f"❌ 资源监控示例失败: {e}")

async def example_3_progress_tracker():
    """示例 3: 进度追踪器"""
    logger.info("\n" + "=" * 60)
    logger.info("示例 3: 进度追踪器")
    logger.info("=" * 60)
    
    try:
        from core.performance_utils import get_progress_tracker
        
        tracker = get_progress_tracker()
        
        # 定义一个进度回调函数
        progress_logs = []
        
        def simple_callback(phase: str, message: str, current: int, total: int):
            progress_str = f"[{current}/{total}] {phase}: {message}"
            progress_logs.append(progress_str)
            logger.info(f"   📈 {progress_str}")
        
        # 添加回调
        tracker.add_callback(simple_callback)
        
        # 模拟进度更新
        logger.info("正在模拟深度思考过程...")
        await tracker.update_progress("initializing", "正在初始化", 0, 5)
        await asyncio.sleep(0.5)
        await tracker.update_progress("understanding", "正在理解问题", 1, 5)
        await asyncio.sleep(0.5)
        await tracker.update_progress("searching", "正在搜索信息", 2, 5)
        await asyncio.sleep(0.5)
        await tracker.update_progress("thinking", "正在深度思考", 3, 5)
        await asyncio.sleep(0.5)
        await tracker.update_progress("validating", "正在验证结果", 4, 5)
        await asyncio.sleep(0.5)
        await tracker.update_progress("complete", "思考完成", 5, 5)
        
        logger.info("✅ 进度追踪示例完成!")
        
    except Exception as e:
        logger.error(f"❌ 进度追踪示例失败: {e}")

async def example_4_deep_thinking_integration():
    """示例 4: 深度思考技能集成（进度回调）"""
    logger.info("\n" + "=" * 60)
    logger.info("示例 4: 深度思考技能集成")
    logger.info("=" * 60)
    
    try:
        from skills.deep_thinking.handler import get_deep_thinking_handler
        
        handler = get_deep_thinking_handler()
        
        # 定义进度回调
        async def progress_callback(phase: str, message: str, current: int, total: int):
            logger.info(f"   📊 [{current}/{total}] {phase}: {message}")
        
        # 执行一个简单的查询，带进度回调
        logger.info("正在执行深度思考查询...")
        
        result = await handler.execute(
            "什么是Python编程语言？",
            user_id=1,
            depth="quick",
            show_thinking=True,
            progress_callback=progress_callback
        )
        
        logger.info(f"\n✅ 深度思考执行成功!")
        logger.info(f"   Success: {result.get('success')}")
        if result.get('resource_status'):
            logger.info(f"   Resource Status: {result.get('resource_status')}")
        
    except Exception as e:
        logger.error(f"❌ 深度思考集成示例失败: {e}")

async def example_5_error_code_usage():
    """示例 5: 使用统一错误码"""
    logger.info("\n" + "=" * 60)
    logger.info("示例 5: 错误码使用")
    logger.info("=" * 60)
    
    try:
        from core.errors import ErrorCode, create_error_response
        
        # 生成各种错误响应
        logger.info("生成错误响应示例:")
        
        # 1. 成功响应
        logger.info("\n1️⃣  成功响应:")
        logger.info("   (ErrorCode.SUCCESS 主要用于表示操作成功)")
        
        # 2. 参数错误
        logger.info("\n2️⃣  参数错误:")
        param_error = create_error_response(ErrorCode.INVALID_PARAMETER, "查询不能为空")
        logger.info(f"   {param_error}")
        
        # 3. 未授权
        logger.info("\n3️⃣  未授权:")
        auth_error = create_error_response(ErrorCode.UNAUTHORIZED, "需要登录")
        logger.info(f"   {auth_error}")
        
        # 4. LLM调用失败
        logger.info("\n4️⃣  LLM调用失败:")
        llm_error = create_error_response(ErrorCode.LLM_CALL_FAILED, "API超时")
        logger.info(f"   {llm_error}")
        
        # 5. 带额外信息的错误
        logger.info("\n5️⃣  带额外信息的错误:")
        rich_error = create_error_response(
            ErrorCode.USER_NOT_FOUND,
            "用户不存在",
            {"user_id": 999, "suggestion": "请先注册"}
        )
        logger.info(f"   {rich_error}")
        
        logger.info("\n✅ 错误码使用示例完成!")
        
    except Exception as e:
        logger.error(f"❌ 错误码示例失败: {e}")

async def main():
    """运行所有示例"""
    logger.info("\n" + "=" * 60)
    logger.info("性能优化工具使用示例")
    logger.info("=" * 60)
    
    await example_1_basic_usage()
    await example_2_resource_monitor()
    await example_3_progress_tracker()
    await example_4_deep_thinking_integration()
    await example_5_error_code_usage()
    
    logger.info("\n" + "=" * 60)
    logger.info("所有示例运行完成!")
    logger.info("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
