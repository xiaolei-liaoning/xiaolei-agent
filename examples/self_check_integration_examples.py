"""自我校验系统集成示例

演示如何将自我校验中间件集成到现有的Agent系统中。
包含多个实际场景的完整示例代码。
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.results.self_check_middleware import SelfCheckMiddleware, get_self_check_middleware
from core.engine.llm_backend import get_llm_router


# ============================================================
# 示例1: 在聊天Agent中集成
# ============================================================

class ChatAgentWithSelfCheck:
    """带自我校验的聊天Agent。"""
    
    def __init__(self, pass_score: int = 80, max_retry: int = 3):
        self.checker = SelfCheckMiddleware(
            pass_score=pass_score,
            max_retry=max_retry,
            enable_logging=True
        )
        self.llm_router = get_llm_router()
        
        # 统计信息
        self.total_queries = 0
        self.avg_quality_score = 0.0
    
    async def chat(self, user_message: str, context: dict = None) -> dict:
        """处理用户消息，带质量保障。
        
        Args:
            user_message: 用户消息
            context: 对话上下文（可选）
            
        Returns:
            包含回答和质量信息的字典
        """
        self.total_queries += 1
        
        # 定义生成函数
        async def generate_answer(query: str, ctx=None) -> str:
            system_prompt = """你是一个友好、专业的AI助手。
请提供准确、有帮助的回答。
要求：
1. 事实准确，避免猜测
2. 表达清晰，易于理解
3. 如有不确定，诚实说明"""
            
            return await self.llm_router.simple_chat(
                query,
                system_prompt=system_prompt,
                temperature=0.7
            )
        
        # 执行自我校验
        result = await self.checker.check_and_optimize(
            user_query=user_message,
            generate_func=generate_answer,
            context=context
        )
        
        # 更新统计
        if self.total_queries == 1:
            self.avg_quality_score = result.score
        else:
            self.avg_quality_score = (
                self.avg_quality_score * (self.total_queries - 1) + result.score
            ) / self.total_queries
        
        # 返回结构化结果
        return {
            "answer": result.answer,
            "quality": {
                "score": result.score,
                "is_reliable": result.is_passed,
                "retry_count": result.retry_count,
            },
            "metadata": {
                "total_time": result.total_time,
                "avg_quality": self.avg_quality_score,
            }
        }


async def example_chat_agent():
    """演示聊天Agent的使用。"""
    print("\n" + "="*60)
    print("示例1: 聊天Agent集成")
    print("="*60)
    
    agent = ChatAgentWithSelfCheck(pass_score=80, max_retry=2)
    
    # 模拟对话
    questions = [
        "Python中的列表和元组有什么区别？",
        "解释一下RESTful API的设计原则",
    ]
    
    for question in questions:
        print(f"\n用户: {question}")
        response = await agent.chat(question)
        
        print(f"AI: {response['answer'][:200]}...")
        print(f"质量评分: {response['quality']['score']}/100")
        print(f"可靠性: {'✓' if response['quality']['is_reliable'] else '✗'}")


# ============================================================
# 示例2: 在代码生成Agent中集成
# ============================================================

class CodeGenerationAgent:
    """带自我校验的代码生成Agent。"""
    
    def __init__(self):
        # 代码生成要求更高的质量标准
        self.checker = SelfCheckMiddleware(
            pass_score=85,
            max_retry=3,
            enable_logging=True
        )
        self.llm_router = get_llm_router()
    
    async def generate_code(self, requirement: str, language: str = "python") -> dict:
        """生成符合要求的代码。
        
        Args:
            requirement: 代码需求描述
            language: 编程语言
            
        Returns:
            包含代码和质量信息的字典
        """
        # 自定义代码评审提示词
        code_review_prompt = """
你是资深代码审查专家，请对生成的代码进行严格评审。

满分100分，合格线{{pass_score}}分。

评分维度：
1. 代码正确性（40分）- 能否正常运行，逻辑是否正确
2. 代码效率（25分）- 时间/空间复杂度是否合理
3. 代码规范（20分）- 命名、注释、风格是否符合Python规范
4. 可维护性（15分）- 结构清晰，易于理解和修改

输出格式：
得分：xx
问题：列出代码存在的问题
优化建议：给出具体的改进方案

用户需求：
{{user_query}}

待审查代码：
{{content}}

请开始评审：
"""
        
        # 定义代码生成函数
        async def generate_code_impl(query: str, context=None) -> str:
            prompt = f"""请用{language}实现以下功能：
{query}

要求：
1. 代码简洁高效
2. 包含必要的注释
3. 遵循最佳实践
4. 处理边界情况

请直接输出代码，不要多余解释："""
            
            return await self.llm_router.simple_chat(
                prompt,
                temperature=0.3  # 代码生成使用低温度
            )
        
        # 执行带自检的代码生成
        result = await self.checker.check_and_optimize(
            user_query=requirement,
            generate_func=generate_code_impl,
            custom_prompt_template=code_review_prompt
        )
        
        return {
            "code": result.answer,
            "quality": {
                "score": result.score,
                "is_production_ready": result.is_passed,
                "retry_count": result.retry_count,
            },
            "history": result.history
        }


async def example_code_agent():
    """演示代码生成Agent的使用。"""
    print("\n" + "="*60)
    print("示例2: 代码生成Agent集成")
    print("="*60)
    
    agent = CodeGenerationAgent()
    
    # 测试代码生成
    requirements = [
        "实现一个线程安全的单例模式",
        "写一个快速排序算法",
    ]
    
    for req in requirements:
        print(f"\n需求: {req}")
        result = await agent.generate_code(req)
        
        print(f"代码预览:\n{result['code'][:300]}...")
        print(f"质量评分: {result['quality']['score']}/100")
        print(f"生产就绪: {'✓' if result['quality']['is_production_ready'] else '✗'}")


# ============================================================
# 示例3: 在数据分析Agent中集成
# ============================================================

class DataAnalysisAgent:
    """带自我校验的数据分析Agent。"""
    
    def __init__(self):
        # 数据分析要求极高的准确性
        self.checker = SelfCheckMiddleware(
            pass_score=90,
            max_retry=4,
            enable_logging=True
        )
        self.llm_router = get_llm_router()
    
    async def analyze_data(self, question: str, data_context: str = "") -> dict:
        """分析数据并回答问题。
        
        Args:
            question: 分析问题
            data_context: 数据上下文（可选）
            
        Returns:
            包含分析结果和质量信息的字典
        """
        # 定义分析函数
        async def analyze(query: str, context=None) -> str:
            system_prompt = """你是专业的数据分析师，请基于提供的数据进行严谨分析。

要求：
1. 所有结论必须有数据支撑
2. 明确指出分析的局限性
3. 避免过度推断
4. 提供可操作的建议

数据上下文：
""" + (data_context if data_context else "无额外数据")
            
            return await self.llm_router.simple_chat(
                query,
                system_prompt=system_prompt,
                temperature=0.5
            )
        
        # 执行自检
        result = await self.checker.check_and_optimize(
            user_query=question,
            generate_func=analyze
        )
        
        return {
            "analysis": result.answer,
            "confidence": {
                "score": result.score,
                "is_reliable": result.is_passed,
                "level": "高" if result.score >= 90 else "中" if result.score >= 80 else "低"
            },
            "iterations": result.retry_count
        }


async def example_data_agent():
    """演示数据分析Agent的使用。"""
    print("\n" + "="*60)
    print("示例3: 数据分析Agent集成")
    print("="*60)
    
    agent = DataAnalysisAgent()
    
    # 测试数据分析
    question = "根据以下销售数据，分析Q1季度的趋势和问题：\n1月: 100万, 2月: 120万, 3月: 95万"
    
    print(f"问题: {question[:50]}...")
    result = await agent.analyze_data(question)
    
    print(f"\n分析结果:\n{result['analysis'][:300]}...")
    print(f"置信度: {result['confidence']['level']} ({result['confidence']['score']}分)")
    print(f"迭代次数: {result['iterations']}")


# ============================================================
# 示例4: 在工作流中集成
# ============================================================

async def example_workflow_integration():
    """演示在工作流中集成自我校验。"""
    print("\n" + "="*60)
    print("示例4: 工作流集成")
    print("="*60)
    
    checker = SelfCheckMiddleware(pass_score=85, max_retry=2)
    llm_router = get_llm_router()
    
    # 模拟多步骤工作流
    workflow_steps = [
        ("需求理解", "用户想要实现一个用户注册系统，需要哪些功能？"),
        ("技术方案", "基于上述需求，推荐合适的技术栈和架构"),
        ("代码实现", "生成用户注册的核心代码"),
    ]
    
    results = []
    
    for step_name, question in workflow_steps:
        print(f"\n步骤: {step_name}")
        print(f"问题: {question[:50]}...")
        
        async def generate(query: str, context=None) -> str:
            return await llm_router.simple_chat(query, temperature=0.7)
        
        result = await checker.check_and_optimize(
            user_query=question,
            generate_func=generate
        )
        
        results.append({
            "step": step_name,
            "score": result.score,
            "passed": result.is_passed,
        })
        
        print(f"质量: {result.score}分 ({'✓' if result.is_passed else '✗'})")
    
    # 工作流汇总
    print(f"\n{'='*40}")
    print("工作流质量汇总:")
    avg_score = sum(r["score"] for r in results) / len(results)
    all_passed = all(r["passed"] for r in results)
    
    print(f"平均得分: {avg_score:.1f}/100")
    print(f"全部通过: {'✓' if all_passed else '✗'}")
    print(f"步骤数: {len(results)}")


# ============================================================
# 示例5: 动态调整配置
# ============================================================

async def example_dynamic_configuration():
    """演示动态调整自检配置。"""
    print("\n" + "="*60)
    print("示例5: 动态配置调整")
    print("="*60)
    
    llm_router = get_llm_router()
    
    # 根据问题类型动态选择配置
    def get_config_for_question(question: str) -> dict:
        """根据问题内容判断合适的配置。"""
        question_lower = question.lower()
        
        if any(keyword in question_lower for keyword in ["代码", "编程", "algorithm"]):
            return {"pass_score": 85, "max_retry": 3}
        elif any(keyword in question_lower for keyword in ["计算", "数学", "math"]):
            return {"pass_score": 90, "max_retry": 3}
        elif any(keyword in question_lower for keyword in ["法律", "医疗", "专业"]):
            return {"pass_score": 90, "max_retry": 4}
        else:
            return {"pass_score": 80, "max_retry": 2}
    
    # 测试不同问题
    test_questions = [
        "今天天气怎么样？",
        "用Python实现二分查找",
        "计算圆的面积公式是什么？",
    ]
    
    for question in test_questions:
        config = get_config_for_question(question)
        checker = SelfCheckMiddleware(**config)
        
        async def generate(query: str, context=None) -> str:
            return await llm_router.simple_chat(query, temperature=0.7)
        
        result = await checker.check_and_optimize(
            user_query=question,
            generate_func=generate
        )
        
        print(f"\n问题: {question[:40]}...")
        print(f"配置: 合格线={config['pass_score']}, 重试={config['max_retry']}")
        print(f"结果: {result.score}分, 重试{result.retry_count}次")


# ============================================================
# 主函数
# ============================================================

async def main():
    """运行所有集成示例。"""
    print("\n" + "#"*60)
    print("# 自我校验系统集成示例")
    print("#"*60)
    
    try:
        await example_chat_agent()
        await example_code_agent()
        await example_data_agent()
        await example_workflow_integration()
        await example_dynamic_configuration()
        
        print("\n" + "#"*60)
        print("# 所有示例运行完成！")
        print("#"*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ 运行出错: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
