"""
AgentPool - 轻量级Agent池

职责：
1. 管理Agent实例的生命周期
2. 提供acquire/release接口获取Agent
3. 支持按类型查找Agent
"""

import asyncio
import logging
from typing import Dict, List, Optional
from collections import defaultdict

from core.multi_agent_v2.agents.base.base_agent import BaseAgent, AgentType

logger = logging.getLogger(__name__)


class AgentPool:
    """Agent池 - 管理Agent实例"""

    def __init__(self):
        # pools: agent_type -> list of agents
        self.pools: Dict[str, List[BaseAgent]] = defaultdict(list)
        # active_agents: agent_id -> agent (正在使用的)
        self.active_agents: Dict[str, BaseAgent] = {}
        # 锁
        self._lock = asyncio.Lock()
        
        logger.info("AgentPool 初始化完成")

    async def register(self, agent: BaseAgent) -> None:
        """注册Agent到池中"""
        async with self._lock:
            agent_type_str = agent.agent_type.value if hasattr(agent.agent_type, 'value') else str(agent.agent_type)
            self.pools[agent_type_str].append(agent)
            logger.info(f"Agent注册到Pool: {agent.agent_id} ({agent_type_str})")
    
    def register_sync(self, agent: BaseAgent) -> None:
        """同步注册Agent到池中（无需事件循环，直接操作pools字典）

        启动阶段无并发竞争，直接追加到列表即可。
        避免使用 run_until_complete() 导致 "This event loop is already running" 错误。
        """
        agent_type_str = agent.agent_type.value if hasattr(agent.agent_type, 'value') else str(agent.agent_type)
        self.pools[agent_type_str].append(agent)
        logger.info(f"Agent同步注册到Pool: {agent.agent_id} ({agent_type_str})")

    async def acquire(self, agent_type: str) -> Optional[BaseAgent]:
        """从池中获取一个Agent"""
        async with self._lock:
            agents = self.pools.get(agent_type, [])
            if not agents:
                logger.warning(f"Pool中无可用Agent: {agent_type}")
                return None
            
            # 取第一个可用的
            agent = agents.pop(0)
            self.active_agents[agent.agent_id] = agent
            logger.info(f"Agent被获取: {agent.agent_id} (剩余: {len(agents)})")
            return agent

    async def release(self, agent: BaseAgent) -> None:
        """释放Agent回池中"""
        async with self._lock:
            if agent.agent_id in self.active_agents:
                del self.active_agents[agent.agent_id]
            
            agent_type_str = agent.agent_type.value if hasattr(agent.agent_type, 'value') else str(agent.agent_type)
            self.pools[agent_type_str].append(agent)
            logger.info(f"Agent释放回Pool: {agent.agent_id}")

    async def get_available_agents(self) -> List[BaseAgent]:
        """获取所有可用Agent"""
        async with self._lock:
            all_agents = []
            for agents in self.pools.values():
                all_agents.extend(agents)
            return all_agents
    
    async def get_all_agents(self) -> List[BaseAgent]:
        """获取所有Agent（包括已激活的）"""
        async with self._lock:
            all_agents = []
            for agents in self.pools.values():
                all_agents.extend(agents)
            all_agents.extend(list(self.active_agents.values()))
            # 去重
            unique_agents = {}
            for agent in all_agents:
                unique_agents[agent.agent_id] = agent
            return list(unique_agents.values())
    
    async def assign_task(self, agent_id: str, subtask_id: str) -> None:
        """将子任务分配给指定Agent"""
        async with self._lock:
            agent = self.active_agents.get(agent_id)
            if agent:
                logger.info(f"任务分配: {subtask_id} -> Agent {agent.name}")
            else:
                # 检查pools中是否有这个agent
                for agents in self.pools.values():
                    for a in agents:
                        if a.agent_id == agent_id:
                            logger.info(f"任务分配: {subtask_id} -> Agent {a.name}")
                            return
                logger.warning(f"Agent {agent_id} 不存在，无法分配任务 {subtask_id}")

    async def find_alternative_agent(self, exclude_agent_id: str) -> Optional[BaseAgent]:
        """查找替代Agent（排除指定Agent）"""
        async with self._lock:
            for agents in self.pools.values():
                for agent in agents:
                    if agent.agent_id != exclude_agent_id:
                        return agent
            return None

    async def find_low_load_agent(self) -> Optional[BaseAgent]:
        """查找负载最低的Agent"""
        async with self._lock:
            min_load = float('inf')
            best_agent = None
            
            for agents in self.pools.values():
                for agent in agents:
                    if agent.current_load < min_load:
                        min_load = agent.current_load
                        best_agent = agent
            
            return best_agent

    @property
    def stats(self):
        """获取池统计信息"""
        class Stats:
            def __init__(self, pool):
                self.total = sum(len(agents) for agents in pool.pools.values())
                self.active = len(pool.active_agents)
                self.current_active = self.active
        return Stats(self)


# 全局单例
_agent_pool: Optional[AgentPool] = None


def get_agent_pool() -> AgentPool:
    """获取全局AgentPool实例"""
    global _agent_pool
    if _agent_pool is None:
        _agent_pool = AgentPool()
    return _agent_pool
