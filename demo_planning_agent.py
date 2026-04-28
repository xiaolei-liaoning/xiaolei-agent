#!/usr/bin/env python3
"""Planning Agent 演示脚本

展示各种实际应用场景
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from planning_agent import planning_agent


async def demo_daily_routine():
    """演示：日常任务自动化"""
    print("\n" + "="*70)
    print("📅 场景 1: 日常工作自动化")
    print("="*70)
    
    scenarios = [
        "每天早上8点发送天气报告到我的邮箱",
        "打开浏览器查看新闻",
        "下载最新的Python教程PDF"
    ]
    
    for i, task in enumerate(scenarios, 1):
        print(f"\n[{i}/{len(scenarios)}] 执行: {task}")
        result = await planning_agent.execute(task)
        status = "✅" if result["success"] else "❌"
        print(f"   {status} {result['message']}")
        await asyncio.sleep(0.5)


async def demo_data_collection():
    """演示：数据收集和分析"""
    print("\n" + "="*70)
    print("📊 场景 2: 数据收集和分析")
    print("="*70)
    
    scenarios = [
        "爬取微博热搜并分析趋势",
        "抓取知乎热门话题",
        "收集GitHub trending项目"
    ]
    
    for i, task in enumerate(scenarios, 1):
        print(f"\n[{i}/{len(scenarios)}] 执行: {task}")
        result = await planning_agent.execute(task)
        status = "✅" if result["success"] else "❌"
        print(f"   {status} {result['message']}")
        await asyncio.sleep(0.5)


async def demo_communication():
    """演示：通信任务"""
    print("\n" + "="*70)
    print("📧 场景 3: 通信和报告")
    print("="*70)
    
    scenarios = [
        "发送邮件给test@example.com，主题为工作汇报，内容为今日工作已完成",
        "发送周报给team@company.com，包含本周工作总结",
        "通知团队成员会议时间变更"
    ]
    
    for i, task in enumerate(scenarios, 1):
        print(f"\n[{i}/{len(scenarios)}] 执行: {task}")
        result = await planning_agent.execute(task)
        status = "✅" if result["success"] else "❌"
        print(f"   {status} {result['message']}")
        await asyncio.sleep(0.5)


async def demo_complex_workflow():
    """演示：复杂工作流"""
    print("\n" + "="*70)
    print("🔄 场景 4: 复杂工作流协作")
    print("="*70)
    
    task = "帮我爬取微博热搜，分析趋势，然后发送邮件给test@example.com报告结果"
    
    print(f"\n执行复杂任务: {task}")
    print("\n任务分解:")
    print("  1. 爬取微博热搜数据")
    print("  2. 分析热搜趋势")
    print("  3. 生成分析报告")
    print("  4. 发送邮件")
    
    result = await planning_agent.execute(task)
    
    print(f"\n{'='*70}")
    print(f"执行结果: {result['message']}")
    print(f"任务统计: 成功 {result['completed_tasks']}/{result['total_tasks']}")
    
    if result.get("results"):
        print("\n详细执行过程:")
        for i, r in enumerate(result["results"], 1):
            status = "✅" if r["success"] else "❌"
            print(f"  {i}. {status} {r['action']}: {r['message']}")
    
    if result.get("failed_tasks"):
        print("\n⚠️ 失败任务:")
        for task in result["failed_tasks"]:
            print(f"  - {task['task_id']}: {task['action']}")


async def demo_error_handling():
    """演示：错误处理和重试"""
    print("\n" + "="*70)
    print("🛡️ 场景 5: 错误处理和容错")
    print("="*70)
    
    # 模拟可能失败的任务
    task = "执行一个可能失败的任务"
    
    print(f"\n执行: {task}")
    print("系统会自动重试最多3次...")
    
    result = await planning_agent.execute(task)
    
    print(f"\n最终结果: {result['message']}")
    
    if not result["success"]:
        print("\n💡 提示: 某些任务可能需要特定环境或权限")
        print("   请检查日志获取详细信息")


async def main():
    """主函数"""
    print("\n" + "🎬"*35)
    print("Planning Agent 演示开始")
    print("🎬"*35)
    
    demos = [
        ("日常任务自动化", demo_daily_routine),
        ("数据收集和分析", demo_data_collection),
        ("通信和报告", demo_communication),
        ("复杂工作流", demo_complex_workflow),
        ("错误处理", demo_error_handling),
    ]
    
    for name, demo_func in demos:
        try:
            await demo_func()
        except Exception as e:
            print(f"\n❌ {name} 演示异常: {e}")
        
        # 演示之间暂停
        await asyncio.sleep(1)
    
    print("\n" + "="*70)
    print("🎉 演示完成！")
    print("="*70)
    print("\n💡 提示:")
    print("  - 查看完整文档: docs/PLANNING_AGENT_GUIDE.md")
    print("  - 快速参考: docs/PLANNING_AGENT_QUICK_REF.md")
    print("  - 运行测试: python test_planning_agent.py")
    print("="*70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
