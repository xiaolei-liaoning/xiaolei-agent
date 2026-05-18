#!/usr/bin/env python3
"""
多Agent端到端效果Demo（真实LLM调用）

展示完整流程：
1. 用户输入复杂任务
2. Master Agent 使用LLM分解任务
3. Worker Agent 使用LLM执行子任务
4. Reviewer Agent 使用LLM评审结果
5. Master Agent 使用LLM聚合返回最终结果

使用真实GLM API进行推理
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.engine.llm_backend import get_llm_router


async def run_real_llm_demo():
    """运行真实LLM调用的Demo"""
    print("=" * 70)
    print("🎯 多Agent端到端协作Demo（真实LLM调用）")
    print("=" * 70)
    print()
    
    # 1. 获取LLM Router
    print("📡 获取LLM Router...")
    router = get_llm_router()
    print(f"✅ LLM Router就绪")
    print(f"   可用方法: chat, simple_chat, chat_stream")
    print()
    
    # 2. 用户任务
    user_task = """分析2024年人工智能领域的发展趋势，包括大语言模型、多模态AI、AI Agent等方向，撰写一份详细的分析报告摘要"""
    
    print("📝 用户任务:")
    print(f"   {user_task}")
    print()
    
    # 3. Master分解任务（使用LLM）
    print("🤖 Step 1: Master Agent 分解任务")
    print("-" * 50)
    
    decompose_prompt = f"""
你是一个任务分解专家，请将以下任务分解为3-5个独立的子任务：

任务: {user_task}

请以JSON格式输出，包含task_id和description字段：
{{
  "subtasks": [
    {{"task_id": "subtask-001", "description": "子任务1描述"}},
    ...
  ]
}}
"""
    
    try:
        messages = [{"role": "user", "content": decompose_prompt}]
        result = await router.chat(messages, model="glm-4.7-flash")
        print(f"LLM响应: {result[:200]}...")
        
        import json
        subtasks = json.loads(result)["subtasks"]
        print(f"\n分解结果: {len(subtasks)} 个子任务")
        for i, st in enumerate(subtasks, 1):
            print(f"   {i}. [{st['task_id']}] {st['description']}")
    except Exception as e:
        print(f"⚠️ 分解失败，使用预设子任务: {e}")
        subtasks = [
            {"task_id": "subtask-001", "description": "分析2024年大语言模型发展趋势"},
            {"task_id": "subtask-002", "description": "调研多模态AI技术最新进展"},
            {"task_id": "subtask-003", "description": "分析AI Agent系统发展现状"}
        ]
        for i, st in enumerate(subtasks, 1):
            print(f"   {i}. [{st['task_id']}] {st['description']}")
    print()
    
    # 4. Worker执行子任务（使用LLM）
    print("👷 Step 2: Worker Agents 执行子任务")
    print("-" * 50)
    
    worker_results = []
    for i, subtask in enumerate(subtasks, 1):
        print(f"Worker {i}: 执行 '{subtask['description']}'")
        
        worker_prompt = f"""
请针对以下主题撰写一份详细的分析报告：

主题: {subtask['description']}

要求：
1. 涵盖主要发展动态
2. 包含关键技术突破
3. 列举典型应用案例
4. 语言简洁明了
"""
        
        try:
            messages = [{"role": "user", "content": worker_prompt}]
            result = await router.chat(messages, model="glm-4.7-flash")
            worker_results.append({
                "task_id": subtask["task_id"],
                "description": subtask["description"],
                "result": result[:300] + "..." if len(result) > 300 else result
            })
            print(f"   ✅ 完成")
        except Exception as e:
            print(f"   ⚠️ 执行失败: {e}")
            worker_results.append({
                "task_id": subtask["task_id"],
                "description": subtask["description"],
                "result": f"执行失败: {e}"
            })
    print()
    
    # 5. Reviewer评审（使用LLM）
    print("🔍 Step 3: Reviewer Agent 评审结果")
    print("-" * 50)
    
    for i, wr in enumerate(worker_results, 1):
        print(f"评审子任务 {i} 的结果...")
        
        review_prompt = f"""
请评审以下分析报告的质量：

报告主题: {wr['description']}
报告内容: {wr['result']}

请从以下维度进行评审：
1. 内容完整性（0-10分）
2. 准确性（0-10分）
3. 建议改进点

请以JSON格式输出：
{{
  "score": 分数,
  "approved": true/false,
  "feedback": "反馈意见"
}}
"""
        
        try:
            messages = [{"role": "user", "content": review_prompt}]
            result = await router.chat(messages, model="glm-4.7-flash")
            import json
            review = json.loads(result)
            status = "✅ 通过" if review["approved"] else "⚠️ 需改进"
            print(f"   {status} (评分: {review['score']}/10)")
            print(f"   反馈: {review['feedback'][:50]}...")
        except Exception as e:
            print(f"   ⚠️ 评审失败: {e}")
    print()
    
    # 6. Master聚合结果（使用LLM）
    print("📊 Step 4: Master Agent 聚合结果")
    print("-" * 50)
    
    all_results = "\n\n".join([f"{wr['description']}:\n{wr['result']}" for wr in worker_results])
    
    aggregate_prompt = f"""
请将以下多个子任务的分析结果整合成一份完整的报告摘要：

子任务结果:
{all_results}

要求：
1. 保持各部分逻辑清晰
2. 去除重复内容
3. 使用Markdown格式
4. 不超过500字
"""
    
    try:
        messages = [{"role": "user", "content": aggregate_prompt}]
        final_report = await router.chat(messages, model="glm-4.7-flash")
        print("✅ 聚合完成")
        print()
        
        # 输出最终结果
        print("🎉 任务完成！")
        print("=" * 70)
        print("📄 最终报告摘要:")
        print("-" * 70)
        print(final_report)
        print("=" * 70)
    except Exception as e:
        print(f"⚠️ 聚合失败: {e}")
    print()


if __name__ == "__main__":
    print("🚀 启动多Agent协作Demo（真实LLM调用）...")
    print()
    asyncio.run(run_real_llm_demo())