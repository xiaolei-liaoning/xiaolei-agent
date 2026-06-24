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

        from core.engine.llm_backend import get_llm_router
        router = get_llm_router()
        is_read_only = False
        if router and router.is_available():
            resp = await router.simple_chat(
                "判断以下请求是'只读分析'还是'写入创建'。只回答'只读'或'写入'。\n请求：" + task[:200],
                temperature=0, max_tokens=10
            )
            is_read_only = '只读' in str(resp or '')

        if is_read_only:
            disallowed_tools = ["execute_shell"]
            print(f"  📋 检测到只读任务，禁用执行类工具")
        else:
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
