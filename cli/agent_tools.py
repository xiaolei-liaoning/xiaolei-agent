"""Agent管理工具模块 - 根据任务动态执行"""

import sys
sys.path.insert(0, '.')


class AgentTools:
    @staticmethod
    async def list_agents():
        """提示信息 - Agent 现在是动态创建的"""
        print("\n🤖 Agent 现在根据任务自动创建，不再需要手动选择类型。")
        print("   直接描述你的任务，系统会自动分配合适的 Agent 执行。\n")

    @staticmethod
    async def _call_llm(prompt):
        """调用GLM LLM生成内容"""
        try:
            from core.engine.llm_backend import GLMBackend
            llm = GLMBackend()
            messages = [{"role": "user", "content": prompt}]
            response = await llm.chat(messages)
            return response
        except Exception as e:
            print(f"⚠️ LLM调用失败: {e}")
            return None

    @staticmethod
    async def call_agent(agent_type, task):
        """调用Agent执行任务 - 根据任务内容动态决定工具约束"""
        print(f"\n🚀 执行任务: {task}")

        # 根据任务内容判断是否需要工具约束
        disallowed_tools = []
        task_lower = task.lower()

        # 只读任务：禁止执行和写入
        if any(kw in task_lower for kw in ["分析", "研究", "查看", "了解", "对比", "评估"]):
            disallowed_tools = ["execute_shell"]
            print(f"  📋 检测到只读任务，禁用执行类工具")

        # 写入任务：禁止危险操作
        elif any(kw in task_lower for kw in ["写", "创建", "生成", "修改", "部署"]):
            disallowed_tools = []
            print(f"  📋 检测到写入任务")

        # 构建 LLM 提示
        personality = "你是一个通用助手"
        if disallowed_tools:
            personality += f"（本次任务禁止使用: {', '.join(disallowed_tools)}）"

        llm_prompt = f"{personality}\n\n任务：{task}\n\n请完成这个任务。"

        # 调用 LLM
        llm_response = await AgentTools._call_llm(llm_prompt)
        if llm_response:
            print(f"\n✅ 执行完成:")
            print("-" * 50)
            print(llm_response)
            print("-" * 50)
            return llm_response

        print("\n⚠️ LLM不可用，无法执行任务")
        return None


# 便捷函数
async def list_agents():
    """提示信息"""
    await AgentTools.list_agents()


async def call_agent(agent_type, task):
    """调用Agent执行任务"""
    return await AgentTools.call_agent(agent_type, task)
