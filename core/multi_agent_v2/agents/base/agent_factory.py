"""AgentFactory — 创建 Agent（兼容 V1 代码）

独立文件避免 base_agent.py 和 work_agent.py 之间的循环导入。
"""


class AgentFactory:
    """创建 Agent（兼容 V1 代码和测试）"""

    @staticmethod
    def create_agent(agent_type=None, agent_id=None, name=None, description="", **kwargs):
        from .work_agent import WorkAgent
        return WorkAgent(agent_id=agent_id, name=name or f"agent_{agent_id[:8] if agent_id else '?'}")

    @staticmethod
    def create_agent_from_role(role_type, agent_id=None, name=None, description=""):
        from .work_agent import WorkAgent
        return WorkAgent(agent_id=agent_id, name=name or role_type)

    @staticmethod
    def create_agents_for_task(keywords, min_count=2, max_count=5):
        from .work_agent import WorkAgent
        count = max(min_count, min(max_count, len(keywords) + 1))
        return [WorkAgent(agent_id=f"agent-{i}", name=f"worker_{i}") for i in range(count)]
