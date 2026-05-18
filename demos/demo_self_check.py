#!/usr/bin/env python3
"""自我校验系统快速演示脚本

这个脚本演示了自我校验系统的核心功能，无需启动完整服务即可体验。
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from core.self_check_middleware import SelfCheckMiddleware
from core.engine.llm_backend import get_llm_router


def print_separator(title: str):
    """打印分隔线。"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)


async def demo_basic_check():
    """演示基础自检功能。"""
    print_separator("演示1: 基础自我校验")
    
    # 创建中间件
    checker = SelfCheckMiddleware(pass_score=80, max_retry=2)
    llm_router = get_llm_router()
    
    # 定义生成函数
    async def generate(query: str, context=None) -> str:
        return await llm_router.simple_chat(query, temperature=0.7)
    
    # 测试问题
    question = "请简要解释什么是人工智能？"
    print(f"\n用户问题: {question}\n")
    
    # 执行自检
    print("正在执行自我校验...")
    result = await checker.check_and_optimize(
        user_query=question,
        generate_func=generate
    )
    
    # 输出结果
    print(f"\n✅ 校验完成!")
    print(f"   最终得分: {result.score}/100")
    print(f"   是否通过: {'✓ 是' if result.is_passed else '✗ 否'}")
    print(f"   重试次数: {result.retry_count}次")
    print(f"   总耗时: {result.total_time:.2f}秒")
    
    print(f"\n📝 回答摘要:")
    print(f"   {result.answer[:200]}...")
    
    if result.history:
        print(f"\n📊 优化历史:")
        for i, round_info in enumerate(result.history, 1):
            print(f"   第{i}轮: 得分={round_info['score']}, "
                  f"问题={round_info['problems'][:30]}...")


async def demo_scenario_config():
    """演示场景化配置。"""
    print_separator("演示2: 场景化配置")
    
    llm_router = get_llm_router()
    
    # 不同场景的配置
    scenarios = [
        ("日常对话", 80, 2),
        ("代码生成", 85, 3),
        ("数学计算", 90, 3),
    ]
    
    for scenario_name, pass_score, max_retry in scenarios:
        print(f"\n场景: {scenario_name}")
        print(f"配置: 合格线={pass_score}分, 最大重试={max_retry}次")
        
        checker = SelfCheckMiddleware(
            pass_score=pass_score,
            max_retry=max_retry
        )
        
        async def generate(query: str, context=None) -> str:
            return await llm_router.simple_chat(query, temperature=0.7)
        
        # 根据场景选择问题
        if scenario_name == "日常对话":
            question = "今天天气怎么样？"
        elif scenario_name == "代码生成":
            question = "用Python写一个hello world程序"
        else:
            question = "计算1+1等于多少？"
        
        result = await checker.check_and_optimize(
            user_query=question,
            generate_func=generate
        )
        
        status = "✓ 通过" if result.is_passed else "✗ 未通过"
        print(f"结果: {status}, 得分={result.score}, 重试={result.retry_count}次")


async def demo_stats():
    """演示统计信息。"""
    print_separator("演示3: 统计信息")
    
    checker = SelfCheckMiddleware(pass_score=80, max_retry=2)
    llm_router = get_llm_router()
    
    async def generate(query: str, context=None) -> str:
        return await llm_router.simple_chat(query, temperature=0.7)
    
    # 执行多次检查
    questions = [
        "什么是Python?",
        "什么是JavaScript?",
    ]
    
    print(f"\n执行{len(questions)}次检查...\n")
    
    for i, question in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] 处理: {question[:30]}...")
        result = await checker.check_and_optimize(
            user_query=question,
            generate_func=generate
        )
        print(f"       得分: {result.score}, 重试: {result.retry_count}次")
    
    # 显示统计
    stats = checker.get_stats()
    print(f"\n📊 统计信息:")
    print(f"   总检查数: {stats['total_checks']}")
    print(f"   通过数: {stats['passed_checks']}")
    print(f"   未通过数: {stats['failed_checks']}")
    print(f"   通过率: {stats['pass_rate']}%")
    print(f"   平均重试: {stats['avg_retry_count']}次")


async def demo_error_handling():
    """演示错误处理。"""
    print_separator("演示4: 错误处理与降级")
    
    checker = SelfCheckMiddleware(pass_score=80, max_retry=1)
    llm_router = get_llm_router()
    
    async def faulty_generate(query: str, context=None) -> str:
        """模拟可能失败的生成函数。"""
        # 这里正常调用，实际项目中可以模拟异常
        return await llm_router.simple_chat(query, temperature=0.7)
    
    try:
        print("\n尝试执行自检（带错误处理）...")
        result = await checker.check_and_optimize(
            user_query="测试错误处理",
            generate_func=faulty_generate
        )
        
        if result.is_passed:
            print(f"✓ 成功: 得分={result.score}")
        else:
            print(f"⚠ 未通过但已降级: 得分={result.score}")
            print(f"   答案: {result.answer[:100]}...")
            
    except Exception as e:
        print(f"✗ 发生异常: {str(e)}")
        print("   降级策略: 使用普通LLM调用")
        
        # 降级处理
        fallback_answer = await llm_router.simple_chat("测试错误处理")
        print(f"   降级答案: {fallback_answer[:100]}...")


async def main():
    """运行所有演示。"""
    print("\n" + "#"*60)
    print("# 自我校验系统 - 快速演示")
    print("#"*60)
    print("\n本演示将展示自我校验系统的核心功能...")
    print("预计耗时: 30-60秒\n")
    
    try:
        await demo_basic_check()
        await demo_scenario_config()
        await demo_stats()
        await demo_error_handling()
        
        print("\n" + "#"*60)
        print("# 演示完成！")
        print("#"*60)
        print("\n💡 提示:")
        print("   - 查看完整文档: docs/SELF_CHECK_SYSTEM_GUIDE.md")
        print("   - 查看快速参考: docs/SELF_CHECK_QUICK_START.md")
        print("   - 运行完整测试: python tests/test_self_check_middleware.py")
        print("   - 查看集成示例: python examples/self_check_integration_examples.py")
        print("   - 启动API服务: python main.py")
        print()
        
    except KeyboardInterrupt:
        print("\n\n⚠ 演示被用户中断")
    except Exception as e:
        print(f"\n\n❌ 演示出错: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 检查依赖
    try:
        import fastapi
        import uvicorn
    except ImportError as e:
        print(f"❌ 缺少依赖: {e}")
        print("请安装依赖: pip install fastapi uvicorn python-dotenv")
        sys.exit(1)
    
    # 运行演示
    asyncio.run(main())
