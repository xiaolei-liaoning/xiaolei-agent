"""
OnDemandAgentPool — 按需创建 Agent，不预注册

替换 SimpleAgentPool：
- 分配任务时才创建 WorkAgent，每个 Agent 拥有完整能力
- 执行完成后通过 share_memory() 广播记忆，通过 discard() 清理
- 不再维护预注册池 (pools / active_agents)
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from core.multi_agent_v2.agents.base.base_agent import BaseAgent, Task
from core.multi_agent_v2.agents.base.work_agent import WorkAgent

logger = logging.getLogger(__name__)


class OnDemandAgentPool:
    """按需创建 Agent，不预注册"""

    def __init__(self):
        self._all_agents: Dict[str, BaseAgent] = {}
        self._load_history: Dict[str, List[float]] = {}
        self._max_history: int = 100

    async def create_agents(self, task: Task, count: int) -> List[BaseAgent]:
        """为任务创建 N 个全新 WorkAgent，每个拥有完整能力"""
        agents = []
        for i in range(count):
            agent = WorkAgent(
                agent_id=f"{task.task_id}_agent_{i}",
                name=f"agent_{i}_{task.task_id[:8]}",
            )
            # Adapt to task — append ALL capability types, no filtering
            agent.adapt_to_task(task)
            await agent.start()
            self._all_agents[agent.agent_id] = agent
            agents.append(agent)

        logger.info(f"为任务 {task.task_id} 创建了 {len(agents)} 个 Agent")
        return agents

    async def share_memory(self, agents: List[BaseAgent]) -> None:
        """执行完成后，每个 Agent 将执行摘要发布到 SharedBus

        以此实现 Agent 间共享记忆。
        """
        try:
            from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus

            bus = get_shared_bus()
            for agent in agents:
                episodes = []
                if hasattr(agent, 'memory') and hasattr(agent.memory, 'get_recent_episodes'):
                    try:
                        episodes = await agent.memory.get_recent_episodes(limit=20)
                    except Exception:
                        episodes = []

                work_stats = {}
                if hasattr(agent, 'get_work_stats'):
                    try:
                        work_stats = agent.get_work_stats()
                    except Exception:
                        work_stats = {}

                await bus.publish(f"memory:share:{agent.agent_id}", {
                    "agent_id": agent.agent_id,
                    "episodes": episodes,
                    "work_stats": work_stats,
                })
                logger.debug(f"Agent {agent.agent_id} 记忆已共享")
        except Exception as e:
            logger.warning(f"共享记忆失败: {e}")

    async def discard(self, agents: List[BaseAgent]) -> None:
        """清理 Agent，从追踪中移除"""
        for agent in agents:
            self._all_agents.pop(agent.agent_id, None)
            self._load_history.pop(agent.agent_id, None)
        logger.debug(f"已清理 {len(agents)} 个 Agent")

    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """按 ID 获取 Agent"""
        return self._all_agents.get(agent_id)

    async def get_all_agents(self) -> List[BaseAgent]:
        """获取所有活跃 Agent"""
        return list(self._all_agents.values())

    async def get_available_agents(self) -> List[BaseAgent]:
        """获取所有可用 Agent（兼容旧接口）"""
        return list(self._all_agents.values())

    async def find_alternative_agent(self, failed_agent_id: str) -> Optional[BaseAgent]:
        """找到替代失败 Agent 的候选（熔断重路由）"""
        candidates = [
            a for a in self._all_agents.values()
            if a.agent_id != failed_agent_id
        ]
        if not candidates:
            return None
        return candidates[0]

    async def find_low_load_agent(self) -> Optional[BaseAgent]:
        """找到负载最低的 Agent（负载均衡）"""
        if not self._all_agents:
            return None
        return min(
            self._all_agents.values(),
            key=lambda a: getattr(a, 'current_load', 0),
        )

    def update_agent_load(self, agent_id: str, current_load: int, max_load: int) -> None:
        """记录 Agent 负载比率（兼容旧接口）"""
        ratio = current_load / max_load if max_load > 0 else 1.0
        if agent_id not in self._load_history:
            self._load_history[agent_id] = []
        self._load_history[agent_id].append(ratio)
        if len(self._load_history[agent_id]) > self._max_history:
            self._load_history[agent_id] = self._load_history[agent_id][-self._max_history:]

    def get_load_stats(self, agent_id: str) -> Dict[str, float]:
        """获取 Agent 负载统计"""
        history = self._load_history.get(agent_id, [])
        if not history:
            return {"avg": 0.0, "max": 0.0, "current": 0.0}
        return {
            "avg": sum(history) / len(history),
            "max": max(history),
            "current": history[-1],
        }

    async def shutdown(self, timeout: float = 10.0) -> None:
        """优雅关闭所有 Agent"""
        logger.info("OnDemandAgentPool 优雅关闭中...")
        agents = list(self._all_agents.values())
        per_agent_timeout = max(1.0, timeout / max(len(agents), 1))

        for agent in agents:
            if hasattr(agent, 'shutdown') and callable(agent.shutdown):
                try:
                    await asyncio.wait_for(
                        asyncio.ensure_future(agent.shutdown()),
                        timeout=per_agent_timeout,
                    )
                except Exception as e:
                    logger.warning(f"Agent {agent.agent_id} 关闭失败: {e}")

        self._all_agents.clear()
        self._load_history.clear()
        logger.info("OnDemandAgentPool 关闭完成")


# 向后兼容别名
SimpleAgentPool = OnDemandAgentPool
