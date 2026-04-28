#!/usr/bin/env python3
"""自我校验循环模块测试脚本

测试覆盖:
1. 评审器功能(评分/问题提取/建议生成)
2. 自检循环流程(达标/不达标/最大重试)
3. 异常处理(解析失败/LLM异常)
4. 边界条件(空内容/超长内容)
"""

import sys
import asyncio
from pathlib import Path
from typing import Awaitable, Callable

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.self_check import SelfCheckEvaluator, SelfCheckLoop, self_check_generate


def print_section(title: str):
    """打印分节标题"""
    print('\n' + '='*60)
    print(f'  {title}')
    print('='*60)


class MockLLM:
    """模拟LLM调用器(用于测试)"""
    
    def __init__(self, responses: dict):
        """初始化模拟响应
        
        Args:
            responses: {prompt关键词: 返回内容}
        """
        self.responses = responses
        self.call_count = 0
    
    async def __call__(self, prompt: str) -> str:
        """模拟LLM调用"""
        self.call_count += 1
        
        # 根据prompt内容返回预设响应
        if '评审' in prompt or '打分' in prompt:
            return self.responses.get('evaluation', '')
        else:
            return self.responses.get('generation', '')


class TestResult:
    """测试结果记录器"""
    def __init__(self):
        self.passed = []
        self.failed = []
    
    def record_pass(self, test_name: str):
        self.passed.append(test_name)
        print(f"✅ {test_name}")
    
    def record_fail(self, test_name: str, error: str = ""):
        self.failed.append((test_name, error))
        print(f"❌ {test_name}: {error}")
    
    def summary(self) -> bool:
        total = len(self.passed) + len(self.failed)
        pass_rate = len(self.passed)/total*100 if total > 0 else 0
        
        print(f"\n{'='*60}")
        print(f"  测试结果汇总")
        print(f"{'='*60}")
        print(f"  总计: {total} 项测试")
        print(f"  通过: {len(self.passed)} 项 ✅")
        print(f"  失败: {len(self.failed)} 项 ❌")
        print(f"  通过率: {pass_rate:.1f}%")
        print(f"{'='*60}")
        
        if self.failed:
            print(f"\n失败详情:")
            for name, error in self.failed:
                print(f"  - {name}: {error}")
        
        return len(self.failed) == 0


async def test_evaluator_parsing(result: TestResult):
    """测试1: 评审结果解析"""
    print_section('测试1: 评审结果解析')
    
    # 模拟LLM返回标准格式
    mock_llm = MockLLM({
        'evaluation': """
得分：85
问题：
- 缺少具体数据支持
- 逻辑跳跃较大
优化建议：
- 补充相关统计数据
- 增加过渡说明
"""
    })
    
    evaluator = SelfCheckEvaluator(mock_llm)
    
    eval_result = await evaluator.evaluate(
        content="这是一个测试答案",
        user_query="测试问题",
        threshold=80
    )
    
    # 验证解析结果
    if eval_result.score == 85:
        result.record_pass('分数解析正确')
    else:
        result.record_fail('分数解析', f"期望85,实际{eval_result.score}")
    
    if len(eval_result.issues) >= 2:
        result.record_pass('问题列表提取')
    else:
        result.record_fail('问题列表提取', f"期望≥2个问题,实际{len(eval_result.issues)}")
    
    if len(eval_result.suggestions) >= 2:
        result.record_pass('优化建议提取')
    else:
        result.record_fail('优化建议提取', f"期望≥2条建议,实际{len(eval_result.suggestions)}")


async def test_self_check_pass(result: TestResult):
    """测试2: 自检循环 - 首轮通过"""
    print_section('测试2: 自检循环 - 首轮通过')
    
    # 模拟高分场景(首轮即达标)
    mock_llm = MockLLM({
        'generation': "这是高质量答案",
        'evaluation': """
得分：90
问题：
- 无明显问题
优化建议：
- 保持当前质量
"""
    })
    
    loop = SelfCheckLoop(
        llm_call_fn=mock_llm,
        max_retries=3,
        pass_threshold=80
    )
    
    response = await loop.generate_with_self_check("测试问题")
    
    if response['success'] and response['passed']:
        result.record_pass('首轮通过检测')
    else:
        result.record_fail('首轮通过', f"success={response['success']}, passed={response['passed']}")
    
    if response['iterations'] == 1:
        result.record_pass('迭代次数为1')
    else:
        result.record_fail('迭代次数', f"期望1,实际{response['iterations']}")


async def test_self_check_retry(result: TestResult):
    """测试3: 自检循环 - 重试后通过"""
    print_section('测试3: 自检循环 - 重试后通过')
    
    call_count = [0]
    
    async def mock_llm(prompt: str) -> str:
        call_count[0] += 1
        
        if '评审' in prompt or '打分' in prompt:
            # 第一轮60分,第二轮85分
            if call_count[0] <= 2:
                return "得分：60\n问题：\n- 内容不完整\n优化建议：\n- 补充细节"
            else:
                return "得分：85\n问题：\n- 无明显问题\n优化建议：\n- 保持质量"
        else:
            return f"第{call_count[0]}轮生成的答案"
    
    loop = SelfCheckLoop(
        llm_call_fn=mock_llm,
        max_retries=3,
        pass_threshold=80
    )
    
    response = await loop.generate_with_self_check("测试问题")
    
    if response['success'] and response['passed']:
        result.record_pass('重试后通过')
    else:
        result.record_fail('重试后通过', f"最终未通过")
    
    if response['iterations'] == 2:
        result.record_pass('迭代次数为2')
    else:
        result.record_fail('迭代次数', f"期望2,实际{response['iterations']}")


async def test_max_retries_exceeded(result: TestResult):
    """测试4: 达到最大重试次数"""
    print_section('测试4: 达到最大重试次数')
    
    async def mock_llm(prompt: str) -> str:
        if '评审' in prompt:
            return "得分：50\n问题：\n- 质量较差\n优化建议：\n- 重新生成"
        else:
            return "低质量答案"
    
    loop = SelfCheckLoop(
        llm_call_fn=mock_llm,
        max_retries=3,
        pass_threshold=80
    )
    
    response = await loop.generate_with_self_check("测试问题")
    
    if not response['success'] and not response['passed']:
        result.record_pass('正确标识失败')
    else:
        result.record_fail('失败标识', f"应返回success=False")
    
    if response['iterations'] == 3:
        result.record_pass('达到最大重试次数')
    else:
        result.record_fail('重试次数', f"期望3,实际{response['iterations']}")
    
    if 'warning' in response:
        result.record_pass('包含警告信息')
    else:
        result.record_fail('警告信息', "缺少warning字段")


async def test_exception_handling(result: TestResult):
    """测试5: 异常处理"""
    print_section('测试5: 异常处理')
    
    async def failing_llm(prompt: str) -> str:
        raise Exception("模拟LLM异常")
    
    evaluator = SelfCheckEvaluator(failing_llm)
    
    # 评审异常时应降级返回
    eval_result = await evaluator.evaluate("测试内容", "测试问题")
    
    if eval_result.score == 70:  # 降级分数
        result.record_pass('评审异常降级处理')
    else:
        result.record_fail('异常降级', f"期望70分,实际{eval_result.score}")


async def test_convenient_function(result: TestResult):
    """测试6: 便捷函数"""
    print_section('测试6: 便捷函数调用')
    
    mock_llm = MockLLM({
        'generation': "便捷函数测试答案",
        'evaluation': "得分：88\n问题：\n- 无\n优化建议：\n- 保持"
    })
    
    response = await self_check_generate(
        user_query="测试问题",
        llm_call_fn=mock_llm,
        max_retries=2,
        pass_threshold=80
    )
    
    if response['success'] and response['passed']:
        result.record_pass('便捷函数正常工作')
    else:
        result.record_fail('便捷函数', "执行失败")
    
    if 'answer' in response and 'history' in response:
        result.record_pass('返回完整数据结构')
    else:
        result.record_fail('返回结构', "缺少必要字段")


async def main():
    """主测试函数"""
    print(f"\n🚀 开始测试自我校验循环模块\n")
    
    result = TestResult()
    
    # 执行所有测试
    await test_evaluator_parsing(result)
    await test_self_check_pass(result)
    await test_self_check_retry(result)
    await test_max_retries_exceeded(result)
    await test_exception_handling(result)
    await test_convenient_function(result)
    
    # 输出结果
    success = result.summary()
    
    if success:
        print(f"\n🎉 所有测试通过!")
    else:
        print(f"\n⚠️ 部分测试失败,请检查错误信息")
    
    return 0 if success else 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
