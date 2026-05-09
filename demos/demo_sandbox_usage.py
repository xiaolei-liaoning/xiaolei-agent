#!/usr/bin/env python3
"""沙盒隔离执行演示

展示如何在实际项目中使用沙盒安全执行代码
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from tools.tool_manager import ToolManager


async def demo_basic_usage():
    """演示1：基本用法"""
    print("=" * 80)
    print("📌 演示1：基本代码执行")
    print("=" * 80)
    
    tm = ToolManager.get_instance()
    
    result = await tm.execute_in_sandbox(
        code="""
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

for i in range(10):
    print(f"F({i}) = {fibonacci(i)}")
""",
        language="python"
    )
    
    print(f"\n✅ 执行成功: {result['success']}")
    print(f"⏱️  耗时: {result['execution_time']:.3f}秒")
    print(f"\n📤 输出:\n{result['stdout']}")


async def demo_context_injection():
    """演示2：上下文变量注入"""
    print("\n" + "=" * 80)
    print("📌 演示2：上下文变量注入")
    print("=" * 80)
    
    tm = ToolManager.get_instance()
    
    data = {
        "users": [
            {"name": "张三", "age": 25, "score": 95},
            {"name": "李四", "age": 28, "score": 87},
            {"name": "王五", "age": 22, "score": 92}
        ]
    }
    
    result = await tm.execute_in_sandbox(
        code="""
total_score = sum(u['score'] for u in users)
avg_score = total_score / len(users)
max_user = max(users, key=lambda u: u['score'])

print(f"用户总数: {len(users)}")
print(f"平均分数: {avg_score:.2f}")
print(f"最高分用户: {max_user['name']} ({max_user['score']}分)")
""",
        language="python",
        context=data
    )
    
    print(f"\n✅ 执行成功: {result['success']}")
    print(f"\n📤 输出:\n{result['stdout']}")


async def main():
    """运行所有演示"""
    print("\n🚀 沙盒隔离执行演示开始...\n")
    
    await demo_basic_usage()
    await demo_context_injection()
    
    print("\n" + "=" * 80)
    print("✨ 所有演示完成！")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())