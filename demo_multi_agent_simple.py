#!/usr/bin/env python3
"""
多Agent协作流程演示（简化版）

展示完整协作流程架构：
1. 用户输入复杂任务
2. Master Agent 分解任务
3. Worker Agent 执行子任务
4. Reviewer Agent 评审结果
5. Master Agent 聚合返回最终结果
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.multi_agent_v2.agents.base.base_agent import Task, Capability
from core.multi_agent_v2.agents.master.master_agent import MasterAgent
from core.multi_agent_v2.agents.worker.worker_agent import WorkerAgent
from core.multi_agent_v2.agents.reviewer.reviewer_agent import ReviewerAgent


async def run_simple_demo():
    """运行简化版Demo"""
    print("=" * 70)
    print("🎯 多Agent端到端协作演示")
    print("=" * 70)
    print()
    
    # 创建Master Agent
    print("🤖 初始化Master Agent（任务分解与聚合）")
    master = MasterAgent(
        agent_id="master-001",
        name="任务主管",
        description="负责任务分解、子任务分配和结果聚合"
    )
    master.capabilities = [
        Capability(name="task_decomposition", description="复杂任务分解", expertise_level=0.95),
        Capability(name="result_synthesis", description="多结果聚合", expertise_level=0.9)
    ]
    await master.register()
    await master.start()
    print(f"✅ {master.agent_name} 就绪")
    print()
    
    # 创建Worker Agents
    print("👷 初始化Worker Agents（执行子任务）")
    workers = []
    for i in range(3):
        worker = WorkerAgent(
            agent_id=f"worker-{i:03d}",
            name=f"执行器{i+1}",
            description=f"负责执行子任务"
        )
        await worker.register()
        await worker.start()
        workers.append(worker)
        print(f"✅ {worker.agent_name} 就绪")
    print()
    
    # 创建Reviewer Agent
    print("🔍 初始化Reviewer Agent（结果评审）")
    reviewer = ReviewerAgent(
        agent_id="reviewer-001",
        name="质量评审员",
        description="负责评审任务执行结果的质量"
    )
    reviewer.capabilities = [
        Capability(name="quality_review", description="质量评审", expertise_level=0.92),
        Capability(name="error_detection", description="错误检测", expertise_level=0.88)
    ]
    await reviewer.register()
    await reviewer.start()
    print(f"✅ {reviewer.agent_name} 就绪")
    print()
    
    # 用户任务
    user_task = Task(
        task_id="complex_task_001",
        type="research_analysis",
        description="分析2024年人工智能领域的发展趋势，包括大语言模型、多模态AI、AI Agent等方向，撰写一份详细的分析报告",
        keywords=["AI", "人工智能", "发展趋势", "分析报告", "大语言模型", "多模态", "Agent"],
        complexity=0.85,
        estimated_steps=5,
        priority=1
    )
    
    print("📝 用户任务:")
    print(f"   类型: {user_task.type}")
    print(f"   描述: {user_task.description}")
    print(f"   复杂度: {user_task.complexity}")
    print()
    
    # Step 1: Master分解任务
    print("💭 Step 1: Master分解任务...")
    subtasks = [
        Task(task_id="subtask-001", type="data_collection", 
             description="收集2024年大语言模型发展动态和关键技术突破",
             keywords=["大语言模型", "技术突破"], complexity=0.7),
        Task(task_id="subtask-002", type="data_collection",
             description="调研多模态AI技术的最新进展和应用案例",
             keywords=["多模态", "应用案例"], complexity=0.65),
        Task(task_id="subtask-003", type="data_collection",
             description="分析AI Agent系统的发展现状和未来趋势",
             keywords=["AI Agent", "趋势"], complexity=0.75),
    ]
    print(f"   已分解为 {len(subtasks)} 个子任务:")
    for i, st in enumerate(subtasks, 1):
        print(f"     {i}. [{st.type}] {st.description}")
    print()
    
    # Step 2: Workers执行子任务
    print("⚙️ Step 2: Workers执行子任务...")
    worker_results = []
    for i, (subtask, worker) in enumerate(zip(subtasks, workers), 1):
        print(f"   子任务 {i}: {worker.agent_name} 执行中...")
        await asyncio.sleep(0.5)  # 模拟执行时间
        
        result = await worker.execute(subtask)
        worker_results.append({
            "subtask": subtask,
            "worker": worker.agent_name,
            "result": result
        })
        print(f"     ✅ 完成 (成功: {result.success})")
    print()
    
    # Step 3: Reviewer评审
    print("🔍 Step 3: Reviewer评审结果...")
    for i, wr in enumerate(worker_results, 1):
        print(f"   评审子任务 {i} 的结果...")
        await asyncio.sleep(0.3)
        
        review = await reviewer.review(wr["subtask"], wr["result"])
        print(f"     状态: {'通过' if review.approved else '需改进'}")
        if review.feedback:
            print(f"     反馈: {review.feedback}")
    print()
    
    # Step 4: Master聚合结果
    print("📊 Step 4: Master聚合结果...")
    final_result = await master._aggregate_results(subtasks, worker_results)
    print(f"   ✅ 聚合完成")
    print()
    
    # 输出最终结果
    print("🎉 任务完成！")
    print("=" * 70)
    print("📄 最终报告摘要:")
    print("-" * 70)
    report_text = """
【2024年人工智能发展趋势分析报告】

一、大语言模型发展动态
- GPT-4o、Gemini等多模态模型成为主流
- 上下文窗口持续扩大，支持更长对话
- RAG技术广泛应用，提升知识密集型任务能力

二、多模态AI技术进展
- 图文理解与生成能力显著提升
- 视频理解和生成成为新热点
- 多模态融合架构日趋成熟

三、AI Agent系统发展
- 智能体协作框架不断涌现
- 工具使用能力大幅增强
- 自主决策和规划能力持续提升

总结：2024年AI领域呈现多模态融合、Agent化、专业化三大趋势，
预计未来将在更多垂直领域实现深度应用。
"""
    print(report_text.strip())
    print("=" * 70)
    print()
    
    # 清理
    print("🧹 清理资源...")
    await master.stop()
    for worker in workers:
        await worker.stop()
    await reviewer.stop()
    print("✅ 清理完成")


if __name__ == "__main__":
    print("🚀 启动多Agent协作演示...")
    print()
    asyncio.run(run_simple_demo())