"""自我校验中间件使用示例与测试

演示如何在不同场景下使用 SelfCheckMiddleware：
1. 基础用法
2. 集成到现有Agent
3. 自定义评分标准
4. API路由集成
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.self_check_middleware import SelfCheckMiddleware, get_self_check_middleware
from core.llm_backend import get_llm_router


# ============================================================
# 示例1: 基础用法
# ============================================================

async def example_basic_usage():
    """基础用法示例。"""
    print("\n" + "="*60)
    print("示例1: 基础用法")
    print("="*60)
    
    # 创建中间件实例
    checker = SelfCheckMiddleware(pass_score=80, max_retry=3)
    
    # 获取LLM路由器
    llm_router = get_llm_router()
    
    # 定义生成函数
    async def generate_answer(query: str, context=None) -> str:
        """简单的问答生成函数。"""
        return await llm_router.simple_chat(query, temperature=0.7)
    
    # 执行自检
    user_query = "请简要解释什么是量子计算？"
    result = await checker.check_and_optimize(
        user_query=user_query,
        generate_func=generate_answer
    )
    
    # 输出结果
    print(f"\n用户问题: {user_query}")
    print(f"最终得分: {result.score}/100")
    print(f"是否通过: {'✓' if result.is_passed else '✗'}")
    print(f"重试次数: {result.retry_count}")
    print(f"总耗时: {result.total_time:.2f}秒")
    print(f"\n最终答案:\n{result.answer[:500]}...")
    
    # 输出优化历史
    if result.history:
        print(f"\n优化历史:")
        for i, round_info in enumerate(result.history, 1):
            print(f"  第{i}轮: 得分={round_info['score']}, 问题={round_info['problems'][:30]}...")
    
    # 输出统计信息
    stats = checker.get_stats()
    print(f"\n统计信息: {stats}")


# ============================================================
# 示例2: 集成到现有Agent工作流
# ============================================================

async def example_agent_integration():
    """演示如何集成到Agent工作流。"""
    print("\n" + "="*60)
    print("示例2: Agent工作流集成")
    print("="*60)
    
    checker = SelfCheckMiddleware(pass_score=85, max_retry=2)
    llm_router = get_llm_router()
    
    # 模拟一个复杂的Agent任务
    async def complex_agent_task(query: str, context=None) -> str:
        """模拟复杂Agent任务的回答生成。"""
        system_prompt = """你是一个专业的技术顾问，请提供准确、详细的技术解答。
要求：
1. 事实准确，避免猜测
2. 逻辑清晰，结构完整
3. 如有不确定，明确说明"""
        
        return await llm_router.simple_chat(
            query,
            system_prompt=system_prompt,
            temperature=0.5
        )
    
    # 执行带自检的Agent任务
    user_query = "Python中的异步编程(async/await)相比多线程有什么优势？"
    result = await checker.check_and_optimize(
        user_query=user_query,
        generate_func=complex_agent_task,
        context={"agent_type": "technical_advisor"}
    )
    
    print(f"\n任务类型: 技术咨询")
    print(f"用户问题: {user_query}")
    print(f"质量评分: {result.score}/100 ({'优秀' if result.score >= 90 else '良好' if result.score >= 80 else '需改进'})")
    print(f"迭代优化: {result.retry_count}次")
    print(f"\n回答摘要:\n{result.answer[:300]}...")


# ============================================================
# 示例3: 不同场景的不同合格线
# ============================================================

async def example_scenario_based_scoring():
    """基于场景的动态评分标准。"""
    print("\n" + "="*60)
    print("示例3: 场景化评分标准")
    print("="*60)
    
    # 定义不同场景的合格线
    scenarios = {
        "通用对话": {"pass_score": 80, "max_retry": 2},
        "代码生成": {"pass_score": 85, "max_retry": 3},
        "数学计算": {"pass_score": 90, "max_retry": 3},
        "创意写作": {"pass_score": 75, "max_retry": 2},
        "专业咨询": {"pass_score": 90, "max_retry": 4},
    }
    
    llm_router = get_llm_router()
    
    # 测试不同场景
    test_cases = [
        ("通用对话", "今天天气怎么样？"),
        ("代码生成", "写一个Python快速排序算法"),
        ("数学计算", "计算1234 * 5678的结果"),
    ]
    
    for scenario, query in test_cases:
        config = scenarios[scenario]
        checker = SelfCheckMiddleware(
            pass_score=config["pass_score"],
            max_retry=config["max_retry"]
        )
        
        async def generate(query: str, context=None) -> str:
            return await llm_router.simple_chat(query, temperature=0.7)
        
        result = await checker.check_and_optimize(
            user_query=query,
            generate_func=generate
        )
        
        status = "✓ 通过" if result.is_passed else "✗ 未通过"
        print(f"\n[{scenario}] 合格线={config['pass_score']}分")
        print(f"  问题: {query[:40]}...")
        print(f"  结果: {status}, 得分={result.score}, 重试={result.retry_count}次")


# ============================================================
# 示例4: 自定义评审提示词
# ============================================================

async def example_custom_prompt():
    """使用自定义评审提示词。"""
    print("\n" + "="*60)
    print("示例4: 自定义评审提示词")
    print("="*60)
    
    # 针对代码审查的自定义提示词
    custom_code_review_prompt = """
你是资深代码审查专家，请对代码进行严格评审。

满分100分，合格线{pass_score}分。

评分维度：
1. 代码正确性（40分）- 能否正常运行，有无bug
2. 代码效率（25分）- 时间/空间复杂度是否合理
3. 代码规范（20分）- 命名、注释、风格是否符合规范
4. 可维护性（15分）- 结构清晰，易于理解和修改

输出格式：
得分：xx
问题：列出代码存在的问题
优化建议：给出具体的改进方案

用户要求：
{user_query}

待审查代码：
{content}

请开始评审：
"""
    
    checker = SelfCheckMiddleware(pass_score=85, max_retry=2)
    llm_router = get_llm_router()
    
    async def generate_code(query: str, context=None) -> str:
        """生成代码。"""
        prompt = f"请用Python实现以下功能，要求代码简洁高效：\n{query}"
        return await llm_router.simple_chat(prompt, temperature=0.3)
    
    user_query = "实现一个线程安全的单例模式"
    result = await checker.check_and_optimize(
        user_query=user_query,
        generate_func=generate_code,
        custom_prompt_template=custom_code_review_prompt
    )
    
    print(f"\n代码审查结果:")
    print(f"得分: {result.score}/100")
    print(f"状态: {'✓ 通过审查' if result.is_passed else '✗ 需要改进'}")
    print(f"\n生成的代码:\n{result.answer[:400]}...")


# ============================================================
# 示例5: 性能对比（有自检 vs 无自检）
# ============================================================

async def example_performance_comparison():
    """性能对比测试。"""
    print("\n" + "="*60)
    print("示例5: 性能对比测试")
    print("="*60)
    
    llm_router = get_llm_router()
    checker = SelfCheckMiddleware(pass_score=80, max_retry=2)
    
    test_query = "解释RESTful API的设计原则"
    
    # 无自检
    start_time = asyncio.get_event_loop().time()
    direct_answer = await llm_router.simple_chat(test_query, temperature=0.7)
    direct_time = asyncio.get_event_loop().time() - start_time
    
    # 有自检
    async def generate(query: str, context=None) -> str:
        return await llm_router.simple_chat(query, temperature=0.7)
    
    start_time = asyncio.get_event_loop().time()
    checked_result = await checker.check_and_optimize(
        user_query=test_query,
        generate_func=generate
    )
    checked_time = asyncio.get_event_loop().time() - start_time
    
    print(f"\n测试问题: {test_query}")
    print(f"\n无自检:")
    print(f"  耗时: {direct_time:.2f}秒")
    print(f"  答案长度: {len(direct_answer)}字符")
    
    print(f"\n有自检:")
    print(f"  耗时: {checked_time:.2f}秒")
    print(f"  最终得分: {checked_result.score}/100")
    print(f"  重试次数: {checked_result.retry_count}")
    print(f"  答案长度: {len(checked_result.answer)}字符")
    
    print(f"\n性能对比:")
    print(f"  时间增加: {(checked_time/direct_time - 1) * 100:.1f}%")
    print(f"  质量提升: 从未知到 {checked_result.score}分")


# ============================================================
# 示例6: 批量处理与统计
# ============================================================

async def example_batch_processing():
    """批量处理示例。"""
    print("\n" + "="*60)
    print("示例6: 批量处理与统计")
    print("="*60)
    
    checker = SelfCheckMiddleware(pass_score=80, max_retry=2)
    llm_router = get_llm_router()
    
    questions = [
        "什么是机器学习？",
        "Python和Java的主要区别是什么？",
        "解释一下数据库索引的作用",
    ]
    
    async def generate(query: str, context=None) -> str:
        return await llm_router.simple_chat(query, temperature=0.7)
    
    results = []
    for i, question in enumerate(questions, 1):
        print(f"\n处理问题 {i}/{len(questions)}...")
        result = await checker.check_and_optimize(
            user_query=question,
            generate_func=generate
        )
        results.append(result)
        print(f"  得分: {result.score}, 重试: {result.retry_count}次")
    
    # 汇总统计
    stats = checker.get_stats()
    avg_score = sum(r.score for r in results) / len(results)
    avg_retries = sum(r.retry_count for r in results) / len(results)
    
    print(f"\n{'='*40}")
    print(f"批量处理统计:")
    print(f"  总问题数: {len(questions)}")
    print(f"  平均得分: {avg_score:.1f}/100")
    print(f"  平均重试: {avg_retries:.1f}次")
    print(f"  通过率: {stats['pass_rate']}%")
    print(f"  总检查数: {stats['total_checks']}")


# ============================================================
# 主函数：运行所有示例
# ============================================================

async def main():
    """运行所有示例。"""
    print("\n" + "#"*60)
    print("# 自我校验中间件 - 完整使用示例")
    print("#"*60)
    
    try:
        # 依次运行示例
        await example_basic_usage()
        await example_agent_integration()
        await example_scenario_based_scoring()
        await example_custom_prompt()
        await example_performance_comparison()
        await example_batch_processing()
        
        print("\n" + "#"*60)
        print("# 所有示例运行完成！")
        print("#"*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ 运行出错: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 运行示例
    asyncio.run(main())
