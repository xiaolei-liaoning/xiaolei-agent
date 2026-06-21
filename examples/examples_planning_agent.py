#!/usr/bin/env python3
"""Planning Agent 使用示例

展示如何在实际项目中集成和使用 Planning Agent
"""

import asyncio
from planning_agent import planning_agent


async def example_1_simple_task():
    """示例 1: 简单任务"""
    print("\n" + "="*60)
    print("示例 1: 简单任务 - 打开浏览器")
    print("="*60)
    
    result = await planning_agent.execute("打开浏览器")
    
    if result["success"]:
        print(f"✅ {result['message']}")
    else:
        print(f"❌ 任务失败: {result['message']}")


async def example_2_email_task():
    """示例 2: 邮件任务"""
    print("\n" + "="*60)
    print("示例 2: 发送邮件")
    print("="*60)
    
    task = "发送邮件给test@example.com，主题为工作汇报，内容为今日工作已完成"
    result = await planning_agent.execute(task)
    
    if result["success"]:
        print(f"✅ {result['message']}")
        print(f"📊 完成 {result['completed_tasks']}/{result['total_tasks']} 个任务")
    else:
        print(f"❌ 任务失败")


async def example_3_crawl_task():
    """示例 3: 数据爬取"""
    print("\n" + "="*60)
    print("示例 3: 爬取微博热搜")
    print("="*60)
    
    result = await planning_agent.execute("爬取微博热搜并分析趋势")
    
    if result["success"]:
        print(f"✅ {result['message']}")
        for r in result["results"]:
            print(f"   - {r['action']}: {'成功' if r['success'] else '失败'}")
    else:
        print(f"❌ 任务失败")


async def example_4_complex_workflow():
    """示例 4: 复杂工作流"""
    print("\n" + "="*60)
    print("示例 4: 复杂工作流 - 爬取、分析、报告")
    print("="*60)
    
    task = "帮我爬取微博热搜，分析趋势，然后发送邮件给test@example.com报告结果"
    
    print(f"\n任务描述: {task}")
    print("\n预期步骤:")
    print("  1. 爬取微博热搜数据")
    print("  2. 分析热搜趋势")
    print("  3. 生成分析报告")
    print("  4. 发送邮件")
    
    result = await planning_agent.execute(task)
    
    print(f"\n{'='*60}")
    print(f"执行结果: {result['message']}")
    print(f"任务统计: 成功 {result['completed_tasks']}/{result['total_tasks']}")
    
    if result.get("results"):
        print("\n详细过程:")
        for i, r in enumerate(result["results"], 1):
            status = "✅" if r["success"] else "❌"
            print(f"  {i}. {status} {r['action']}")
    
    if result.get("failed_tasks"):
        print("\n⚠️ 失败的任务:")
        for task in result["failed_tasks"]:
            print(f"  - {task['task_id']}: {task['action']}")


async def example_5_error_handling():
    """示例 5: 错误处理"""
    print("\n" + "="*60)
    print("示例 5: 错误处理")
    print("="*60)
    
    try:
        # 可能失败的任务
        result = await planning_agent.execute("执行一个不存在的任务")
        
        if not result["success"]:
            print(f"⚠️ 任务部分失败: {result['message']}")
            print("💡 建议: 检查任务描述是否清晰，或查看日志获取详细信息")
            
    except Exception as e:
        print(f"❌ 发生异常: {e}")
        print("💡 建议: 使用 try-except 捕获异常")


async def example_6_batch_tasks():
    """示例 6: 批量任务"""
    print("\n" + "="*60)
    print("示例 6: 批量执行多个任务")
    print("="*60)
    
    tasks = [
        "打开浏览器",
        "发送邮件给test@example.com",
        "爬取微博热搜"
    ]
    
    results = []
    
    for i, task in enumerate(tasks, 1):
        print(f"\n[{i}/{len(tasks)}] 执行: {task}")
        result = await planning_agent.execute(task)
        results.append({
            "task": task,
            "success": result["success"]
        })
        status = "✅" if result["success"] else "❌"
        print(f"   {status} {result['message']}")
    
    # 统计结果
    print(f"\n{'='*60}")
    print("批量任务统计:")
    success_count = sum(1 for r in results if r["success"])
    print(f"  总任务数: {len(tasks)}")
    print(f"  成功: {success_count}")
    print(f"  失败: {len(tasks) - success_count}")
    print(f"  成功率: {success_count/len(tasks)*100:.1f}%")


async def main():
    """运行所有示例"""
    print("\n" + "🎯"*30)
    print("Planning Agent 使用示例")
    print("🎯"*30)
    
    examples = [
        ("简单任务", example_1_simple_task),
        ("邮件任务", example_2_email_task),
        ("数据爬取", example_3_crawl_task),
        ("复杂工作流", example_4_complex_workflow),
        ("错误处理", example_5_error_handling),
        ("批量任务", example_6_batch_tasks),
    ]
    
    for name, example_func in examples:
        try:
            await example_func()
        except Exception as e:
            print(f"\n❌ {name} 示例异常: {e}")
        
        # 示例之间暂停
        await asyncio.sleep(0.5)
    
    print("\n" + "="*60)
    print("🎉 所有示例运行完成！")
    print("="*60)
    print("\n💡 下一步:")
    print("  - 查看完整文档: docs/PLANNING_AGENT_GUIDE.md")
    print("  - 运行测试: python test_planning_agent.py")
    print("  - 查看演示: python demo_planning_agent.py")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
