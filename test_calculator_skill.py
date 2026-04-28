#!/usr/bin/env python3
"""计算器技能测试脚本"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from skills.calculator.handler import get_calculator_handler


def print_section(title: str):
    """打印分节标题"""
    print('\n' + '='*60)
    print(f'  {title}')
    print('='*60)


class TestResult:
    """测试结果记录器"""
    def __init__(self):
        self.passed = []
        self.failed = []
    
    def record_pass(self, test_name):
        self.passed.append(test_name)
        print(f"✅ {test_name}")
    
    def record_fail(self, test_name, error=""):
        self.failed.append((test_name, error))
        print(f"❌ {test_name}: {error}")
    
    def summary(self):
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
        
        return len(self.failed) == 0


def test_basic_calculation(result: TestResult):
    """测试1: 基础计算"""
    print_section('测试1: 基础计算')
    
    handler = get_calculator_handler()
    
    # 测试加法
    response = handler.execute('calculate', expression='2 + 3')
    if response['success'] and response['result'] == 5:
        result.record_pass('基础计算 - 加法')
    else:
        result.record_fail('基础计算 - 加法', f"期望5,实际{response.get('result')}")
    
    # 测试乘法优先级
    response = handler.execute('calculate', expression='2 + 3 * 4')
    if response['success'] and response['result'] == 14:
        result.record_pass('基础计算 - 运算符优先级')
    else:
        result.record_fail('基础计算 - 运算符优先级', f"期望14,实际{response.get('result')}")
    
    # 测试括号
    response = handler.execute('calculate', expression='(2 + 3) * 4')
    if response['success'] and response['result'] == 20:
        result.record_pass('基础计算 - 括号优先级')
    else:
        result.record_fail('基础计算 - 括号优先级', f"期望20,实际{response.get('result')}")


def test_invalid_expression(result: TestResult):
    """测试2: 非法表达式"""
    print_section('测试2: 非法表达式检测')
    
    handler = get_calculator_handler()
    
    # 测试包含字母的表达式
    response = handler.execute('calculate', expression='2 + abc')
    if not response['success']:
        result.record_pass('非法表达式检测 - 拒绝字母')
    else:
        result.record_fail('非法表达式检测 - 拒绝字母', '应该拒绝包含字母的表达式')
    
    # 测试除零错误
    response = handler.execute('calculate', expression='1 / 0')
    if not response['success']:
        result.record_pass('非法表达式检测 - 除零保护')
    else:
        result.record_fail('非法表达式检测 - 除零保护', '应该捕获除零错误')


def test_history(result: TestResult):
    """测试3: 历史记录"""
    print_section('测试3: 历史记录功能')
    
    handler = get_calculator_handler()
    
    response = handler.execute('history')
    if response['success']:
        result.record_pass('历史记录查询')
    else:
        result.record_fail('历史记录查询', response.get('error', ''))
    
    response = handler.execute('clear')
    if response['success']:
        result.record_pass('清空历史记录')
    else:
        result.record_fail('清空历史记录', response.get('error', ''))


def main():
    """主测试函数"""
    print(f"\n🚀 开始测试计算器技能\n")
    
    result = TestResult()
    
    # 执行所有测试
    test_basic_calculation(result)
    test_invalid_expression(result)
    test_history(result)
    
    # 输出结果
    success = result.summary()
    
    if success:
        print(f"\n🎉 所有测试通过!")
    else:
        print(f"\n⚠️ 部分测试失败,请检查错误信息")
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
