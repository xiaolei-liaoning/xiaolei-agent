"""
SimpleAgentPool — 轻量级 Agent 池

就是一个能存 Agent、能按 ID 取的 dict。
没有健康检查、没有持久化，Agent 用完即弃。
"""

import logging
from typing import Any, Dict, List, Optional

from core.multi_agent_v2.agents.base.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class SimpleAgentPool:
    """轻量 Agent 池 — 只存不管理"""

    def __init__(self):
        self.pools: Dict[str, List[BaseAgent]] = {}
        self.active_agents: Dict[str, BaseAgent] = {}

    def add_agent(self, agent: BaseAgent, pool_type: str = "default") -> None:
        """注册一个 Agent 到池中"""
        if pool_type not in self.pools:
            self.pools[pool_type] = []
        self.pools[pool_type].append(agent)
        self.active_agents[agent.agent_id] = agent
        logger.info(f"Agent 注册: {agent.agent_name} ({agent.agent_type.value}) -> {pool_type}")

    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """按 ID 获取 Agent"""
        return self.active_agents.get(agent_id)

    async def acquire(self, pool_type: str = "default") -> Optional[BaseAgent]:
        """从池中取一个可用 Agent"""
        agents = self.pools.get(pool_type, [])
        for agent in agents:
            if agent.agent_id in self.active_agents:
                return agent
        return None

    async def get_available_agents(self) -> List[BaseAgent]:
        """获取所有可用 Agent"""
        return list(self.active_agents.values())

    async def assign_task(self, agent_id: str, subtask_id: str) -> None:
        """将子任务分配给指定 Agent"""
        agent = self.get_agent(agent_id)
        if agent:
            logger.info(f"任务分配: {subtask_id} -> Agent {agent.agent_name}")
        else:
            logger.warning(f"Agent {agent_id} 不存在，无法分配任务 {subtask_id}")

    def remove_agent(self, agent_id: str) -> None:
        """移除 Agent"""
        self.active_agents.pop(agent_id, None)
        for pool_type, agents in self.pools.items():
            self.pools[pool_type] = [a for a in agents if a.agent_id != agent_id]