#!/usr/bin/env python3
"""沙盒隔离执行演示

展示如何在实际项目中使用沙盒安全执行代码
"""

import asyncio
from tools.tool_manager import ToolManager


async def demo_basic_usage():
    """演示1：基本用法"""
    print("=" * 80)
    print("📌 演示1：基本代码执行")
    print("=" * 80)
    
    tm = ToolManager.get_instance()
    
    # 执行简单的Python代码
    result = await tm.execute_in_sandbox(
        code="""
# 计算斐波那契数列
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

# 打印前10项
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
    
    # 模拟数据处理场景
    data = {
        "users": [
            {"name": "张三", "age": 25, "score": 95},
            {"name": "李四", "age": 28, "score": 87},
            {"name": "王五", "age": 22, "score": 92}
        ]
    }
    
    result = await tm.execute_in_sandbox(
        code="""
# 数据分析
total_score = sum(u['score'] for u in users)
avg_score = total_score / len(users)
max_user = max(users, key=lambda u: u['score'])

print(f"用户总数: {len(users)}")
print(f"平均分数: {avg_score:.2f}")
print(f"最高分用户: {max_user['name']} ({max_user['score']}分)")

# 生成报告
print("\\n--- 用户报告 ---")
for user in users:
    status = "优秀" if user['score'] >= 90 else "良好"
    print(f"{user['name']}: {user['score']}分 - {status}")
""",
        language="python",
        context=data
    )
    
    print(f"\n✅ 执行成功: {result['success']}")
    print(f"\n📤 输出:\n{result['stdout']}")


async def demo_security_protection():
    """演示3：安全防护"""
    print("\n" + "=" * 80)
    print("📌 演示3：安全防护机制")
    print("=" * 80)
    
    tm = ToolManager.get_instance()
    
    # 测试1：禁止导入危险模块
    print("\n🔒 测试1：尝试导入os模块（应被拦截）")
    result = await tm.execute_in_sandbox(
        code="import os; print(os.getcwd())",
        language="python"
    )
    print(f"   结果: {'❌ 被拦截' if not result['success'] else '✅ 执行'}")
    print(f"   原因: {result.get('error', 'N/A')}")
    
    # 测试2：禁止使用eval
    print("\n🔒 测试2：尝试使用eval函数（应被拦截）")
    result = await tm.execute_in_sandbox(
        code="result = eval('1+1'); print(result)",
        language="python"
    )
    print(f"   结果: {'❌ 被拦截' if not result['success'] else '✅ 执行'}")
    print(f"   原因: {result.get('error', 'N/A')}")
    
    # 测试3：超时保护
    print("\n🔒 测试3：超时保护（限制2秒）")
    result = await tm.execute_in_sandbox(
        code="import time; time.sleep(10)",
        language="python",
        timeout=2
    )
    print(f"   结果: {'⏰ 超时终止' if result['status'] == 'timeout' else '其他状态'}")
    print(f"   耗时: {result['execution_time']:.2f}秒")


async def demo_shell_commands():
    """演示4：Shell命令执行"""
    print("\n" + "=" * 80)
    print("📌 演示4：受限的Shell命令执行")
    print("=" * 80)
    
    tm = ToolManager.get_instance()
    
    # 安全的Shell命令
    result = await tm.execute_in_sandbox(
        code="echo '系统信息:' && uname -a && echo '\\n当前目录:' && pwd",
        language="shell",
        timeout=5
    )
    
    print(f"\n✅ 执行成功: {result['success']}")
    print(f"\n📤 输出:\n{result['stdout']}")
    
    # 测试危险命令拦截
    print("\n🔒 测试：尝试执行危险命令 rm -rf（应被拦截）")
    result = await tm.execute_in_sandbox(
        code="rm -rf /tmp/test",
        language="shell"
    )
    print(f"   结果: {'❌ 被拦截' if not result['success'] else '✅ 执行'}")
    print(f"   原因: {result.get('error', 'N/A')}")


async def demo_error_handling():
    """演示5：错误处理"""
    print("\n" + "=" * 80)
    print("📌 演示5：优雅的错误处理")
    print("=" * 80)
    
    tm = ToolManager.get_instance()
    
    # 测试1：语法错误
    print("\n❌ 测试1：代码语法错误")
    result = await tm.execute_in_sandbox(
        code="print('hello'  # 缺少右括号",
        language="python"
    )
    print(f"   成功: {result['success']}")
    print(f"   错误输出: {result['stderr'][:100]}...")
    
    # 测试2：运行时错误
    print("\n❌ 测试2：运行时错误（除零错误）")
    result = await tm.execute_in_sandbox(
        code="result = 1 / 0",
        language="python"
    )
    print(f"   成功: {result['success']}")
    print(f"   错误输出: {result['stderr']}")
    
    # 正确的错误处理方式
    print("\n✅ 正确的错误处理示例")
    result = await tm.execute_in_sandbox(
        code="""
try:
    result = 1 / 0
except ZeroDivisionError as e:
    print(f"捕获到错误: {e}")
    print("程序继续正常运行")
""",
        language="python"
    )
    print(f"   成功: {result['success']}")
    print(f"   输出: {result['stdout']}")


async def demo_real_world_scenario():
    """演示6：真实场景应用"""
    print("\n" + "=" * 80)
    print("📌 演示6：真实应用场景 - AI助手代码执行")
    print("=" * 80)
    
    tm = ToolManager.get_instance()
    
    # 模拟AI生成的代码（用户请求：帮我分析这个销售数据）
    ai_generated_code = """
# AI生成的数据分析代码
sales_data = [
    {"product": "iPhone", "sales": 150, "revenue": 150000},
    {"product": "MacBook", "sales": 80, "revenue": 160000},
    {"product": "iPad", "sales": 120, "revenue": 72000},
]

# 计算总销售额和总收入
total_sales = sum(item['sales'] for item in sales_data)
total_revenue = sum(item['revenue'] for item in sales_data)

print("📊 销售数据分析报告")
print("=" * 40)
print(f"总销售量: {total_sales} 件")
print(f"总收入: ¥{total_revenue:,}")
print(f"平均单价: ¥{total_revenue/total_sales:.2f}")
print()

# 找出最畅销产品
best_seller = max(sales_data, key=lambda x: x['sales'])
print(f"🏆 最畅销产品: {best_seller['product']}")
print(f"   销量: {best_seller['sales']} 件")
print(f"   收入: ¥{best_seller['revenue']:,}")
"""
    
    print("\n🤖 模拟AI生成的代码执行...")
    result = await tm.execute_in_sandbox(
        code=ai_generated_code,
        language="python",
        timeout=10,
        max_memory_mb=256
    )
    
    print(f"\n✅ 执行成功: {result['success']}")
    print(f"⏱️  耗时: {result['execution_time']:.3f}秒")
    print(f"\n📤 AI分析报告:\n{result['stdout']}")


async def main():
    """运行所有演示"""
    print("\n🚀 沙盒隔离执行演示开始...\n")
    
    await demo_basic_usage()
    await demo_context_injection()
    await demo_security_protection()
    await demo_shell_commands()
    await demo_error_handling()
    await demo_real_world_scenario()
    
    print("\n" + "=" * 80)
    print("✨ 所有演示完成！")
    print("=" * 80)
    print("\n💡 提示：")
    print("   - 查看完整文档: SANDBOX_INTEGRATION_GUIDE.md")
    print("   - 快速参考: SANDBOX_QUICK_REF.md")
    print("   - 运行测试: python test_sandbox_integration.py")
    print()


if __name__ == "__main__":
    asyncio.run(main())