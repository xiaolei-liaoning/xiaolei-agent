#!/usr/bin/env python3
"""
多Agent端到端效果Demo

展示完整流程：
1. 用户输入复杂任务
2. Master Agent 分解任务
3. Worker Agent 执行子任务
4. Reviewer Agent 评审结果
5. Master Agent 聚合返回最终结果

使用真实GLM API进行推理
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.multi_agent_v2.agents.base.base_agent import Task, AgentState, Capability
from core.multi_agent_v2.agents.master.master_agent import MasterAgent
from core.multi_agent_v2.agents.worker.worker_agent import WorkerAgent
from core.multi_agent_v2.agents.reviewer.reviewer_agent import ReviewerAgent
from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus


async def run_e2e_demo():
    """运行端到端Demo"""
    print("=" * 70)
    print("🎯 多Agent端到端协作Demo")
    print("=" * 70)
    print()
    
    # 1. 初始化SharedBus
    print("📡 初始化共享消息总线...")
    bus = get_shared_bus()
    print("✅ SharedBus 就绪")
    print()
    
    # 2. 创建Master Agent（任务分解与聚合）
    print("🤖 创建Master Agent...")
    master = MasterAgent(
        agent_id="master-001",
        name="任务主管",
        description="负责任务分解、子任务分配和结果聚合"
    )
    master.capabilities = [
        Capability(
            name="task_decomposition",
            description="复杂任务分解",
            keywords=["分解", "规划", "任务拆分"],
            expertise_level=0.95
        ),
        Capability(
            name="result_synthesis",
            description="多结果聚合",
            keywords=["聚合", "综合", "总结"],
            expertise_level=0.9
        )
    ]
    await master.register()
    await master.start()
    print(f"✅ Master Agent 就绪: {master.agent_name}")
    print()
    
    # 3. 创建Worker Agent（执行子任务）
    print("👷 创建Worker Agent...")
    workers = []
    worker_capabilities = [
        Capability(
            name="data_analysis",
            description="数据分析处理",
            keywords=["分析", "数据", "统计"],
            expertise_level=0.85
        ),
        Capability(
            name="web_research",
            description="网络搜索调研",
            keywords=["搜索", "调研", "信息收集"],
            expertise_level=0.8
        ),
        Capability(
            name="report_generation",
            description="报告生成",
            keywords=["报告", "文档", "撰写"],
            expertise_level=0.88
        )
    ]
    
    for i in range(3):
        worker = WorkerAgent(
            agent_id=f"worker-{i:03d}",
            name=f"执行器{i+1}",
            description=f"负责执行第{i+1}类子任务"
        )
        worker.capabilities = worker_capabilities
        await worker.register()
        await worker.start()
        workers.append(worker)
        print(f"✅ Worker Agent 就绪: {worker.agent_name}")
    print()
    
    # 4. 创建Reviewer Agent（结果评审）
    print("🔍 创建Reviewer Agent...")
    reviewer = ReviewerAgent(
        agent_id="reviewer-001",
        name="质量评审员",
        description="负责评审任务执行结果的质量"
    )
    reviewer.capabilities = [
        Capability(
            name="quality_review",
            description="质量评审",
            keywords=["评审", "检查", "验证"],
            expertise_level=0.92
        ),
        Capability(
            name="error_detection",
            description="错误检测",
            keywords=["错误", "问题", "缺陷"],
            expertise_level=0.88
        )
    ]
    await reviewer.register()
    await reviewer.start()
    print(f"✅ Reviewer Agent 就绪: {reviewer.agent_name}")
    print()
    
    # 5. 用户输入复杂任务
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
    print(f"   预计步骤: {user_task.estimated_steps}")
    print()
    
    # 6. Master思考并分解任务
    print("💭 Step 1: Master Agent 思考并分解任务...")
    master_thought = await master.think(user_task)
    print(f"   推理过程: {master_thought.reasoning[:200]}...")
    print(f"   置信度: {master_thought.confidence:.2f}")
    print(f"   执行计划:")
    for i, step in enumerate(master_thought.plan, 1):
        print(f"     {i}. {step}")
    print()
    
    # 7. Master分解任务为子任务
    print("🔨 Step 2: Master Agent 分解任务...")
    subtasks = await master._decompose_task(user_task)
    print(f"   分解出 {len(subtasks)} 个子任务:")
    for i, subtask in enumerate(subtasks, 1):
        print(f"     {i}. [{subtask.type}] {subtask.description}")
    print()
    
    # 8. Worker执行子任务
    print("⚙️ Step 3: Worker Agent 执行子任务...")
    worker_results = []
    for i, (subtask, worker) in enumerate(zip(subtasks, workers), 1):
        print(f"   子任务 {i}: Worker {worker.agent_name} 开始执行...")
        
        # Worker思考
        worker_thought = await worker.think(subtask)
        
        # Worker执行
        result = await worker.execute(subtask)
        
        worker_results.append({
            "subtask": subtask,
            "worker": worker.agent_name,
            "result": result
        })
        print(f"     ✅ 完成 (成功: {result.success}, 耗时: {result.execution_time:.2f}s)")
    print()
    
    # 9. Reviewer评审结果
    print("🔍 Step 4: Reviewer Agent 评审结果...")
    review_results = []
    for i, wr in enumerate(worker_results, 1):
        print(f"   评审子任务 {i} 的结果...")
        review = await reviewer.review(wr["subtask"], wr["result"])
        review_results.append(review)
        print(f"     评审状态: {'通过' if review.approved else '需改进'}")
        if review.feedback:
            print(f"     反馈: {review.feedback[:100]}...")
    print()
    
    # 10. Master聚合结果
    print("📊 Step 5: Master Agent 聚合结果...")
    final_result = await master._aggregate_results(subtasks, worker_results)
    print(f"   聚合完成")
    print(f"   总执行时间: {final_result.execution_time:.2f}s")
    print()
    
    # 11. 输出最终结果
    print("🎉 任务完成！")
    print("=" * 70)
    print("📄 最终报告摘要:")
    print("-" * 70)
    if final_result.output:
        print(final_result.output[:500] if len(str(final_result.output)) > 500 else final_result.output)
        if len(str(final_result.output)) > 500:
            print("...（内容过长，已截断）")
    print("=" * 70)
    print()
    
    # 12. 清理
    print("🧹 清理资源...")
    await master.stop()
    for worker in workers:
        await worker.stop()
    await reviewer.stop()
    print("✅ 清理完成")


if __name__ == "__main__":
    print("🚀 启动多Agent端到端Demo...")
    print()
    
    try:
        asyncio.run(run_e2e_demo())
    except Exception as e:
        print(f"❌ Demo执行失败: {e}")
        import traceback
        traceback.print_exc()