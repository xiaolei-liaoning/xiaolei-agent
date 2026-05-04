"""
AgentPool - Agent池管理器
复用已创建的Agent，避免频繁创建/销毁
"""

import asyncio
import logging
import uuid
import time
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class PoolStats:
    """池统计信息"""

    def __init__(self):
        self.created: int = 0
        self.reused: int = 0
        self.current_active: int = 0
        self.current_pooled: Dict[str, int] = {}
        self.total_requests: int = 0
        self.wait_time_sum: float = 0.0

    def get_summary(self) -> Dict[str, Any]:
        """获取统计摘要"""
        total_pooled = sum(self.current_pooled.values())
        reuse_rate = (self.reused / self.total_requests * 100) if self.total_requests > 0 else 0
        avg_wait = (self.wait_time_sum / self.total_requests) if self.total_requests > 0 else 0

        return {
            "created": self.created,
            "reused": self.reused,
            "reuse_rate_pct": round(reuse_rate, 2),
            "active": self.current_active,
            "pooled": total_pooled,
            "pooled_by_type": self.current_pooled.copy(),
            "avg_wait_ms": round(avg_wait * 1000, 2)
        }


class AgentPool:
    """Agent池 - 复用已创建的Agent

    核心功能：
    - acquire: 从池中获取Agent
    - release: 归还Agent到池
    - 统计信息追踪
    """

    def __init__(
        self,
        max_pool_size_per_type: int = 5,
        idle_timeout: int = 300,
        max_waiters: int = 20
    ):
        self.max_pool_size_per_type = max_pool_size_per_type
        self.idle_timeout = idle_timeout
        self.max_waiters = max_waiters

        self.pools: Dict[str, List] = {
            "master": [],
            "worker": [],
            "reviewer": [],
            "expert": []
        }

        self.active_agents: Dict[str, Any] = {}

        self.wait_queues: Dict[str, asyncio.Queue] = {
            t: asyncio.Queue(max_waiters)
            for t in self.pools.keys()
        }

        self.stats = PoolStats()
        self._cleanup_task: Optional[asyncio.Task] = None

        logger.info(f"AgentPool initialized (max_size={max_pool_size_per_type})")

    async def start(self):
        """启动池 - 开启清理任务"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_idle_agents())
            logger.info("AgentPool cleanup task started")

    async def stop(self):
        """停止池 - 清理所有资源"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

        for agent_type, agents in self.pools.items():
            for agent in agents:
                await self._shutdown_agent(agent)
            agents.clear()

        for agent in self.active_agents.values():
            await self._shutdown_agent(agent)
        self.active_agents.clear()

        logger.info("AgentPool stopped")

    async def acquire(self, agent_type: str, wait_timeout: float = 5.0) -> Any:
        """获取一个Agent"""
        start_time = time.time()
        self.stats.total_requests += 1

        logger.debug(f"Acquiring {agent_type} agent...")

        agent = await self._try_get_from_pool(agent_type)
        if agent is not None:
            self.stats.reused += 1
            self.stats.current_active += 1
            self.stats.wait_time_sum += time.time() - start_time
            self.active_agents[agent.agent_id] = agent
            logger.debug(f"Reused {agent_type} agent: {agent.agent_id}")
            return agent

        try:
            agent = await self._create_agent(agent_type)
            self.stats.created += 1
            self.stats.current_active += 1
            self.stats.wait_time_sum += time.time() - start_time
            self.active_agents[agent.agent_id] = agent
            logger.debug(f"Created new {agent_type} agent: {agent.agent_id}")
            return agent
        except Exception as e:
            logger.error(f"Failed to create {agent_type} agent: {e}")
            raise

    async def release(self, agent) -> None:
        """归还Agent到池"""
        agent_id = agent.agent_id
        agent_type = agent.agent_type.value if hasattr(agent.agent_type, 'value') else str(agent.agent_type)

        if agent_id not in self.active_agents:
            logger.warning(f"Agent {agent_id} not in active set")
            return

        del self.active_agents[agent_id]
        self.stats.current_active -= 1

        pool = self.pools.get(agent_type, [])
        if len(pool) < self.max_pool_size_per_type:
            await self._reset_agent(agent)
            pool.append(agent)
            self.stats.current_pooled[agent_type] = len(pool)
            logger.debug(f"Released {agent_type} to pool: {agent_id}")
        else:
            await self._shutdown_agent(agent)
            logger.debug(f"Shutdown {agent_type} agent (pool full): {agent_id}")

    async def _try_get_from_pool(self, agent_type: str) -> Optional[Any]:
        """尝试从池中获取Agent"""
        pool = self.pools.get(agent_type, [])
        if pool:
            agent = pool.pop()
            self.stats.current_pooled[agent_type] = len(pool)
            await self._wake_up_agent(agent)
            return agent
        return None

    async def _create_agent(self, agent_type: str) -> Any:
        """创建新的Agent"""
        from core.multi_agent_v2.agents.master.master_agent import MasterAgent
        from core.multi_agent_v2.agents.worker.worker_agent import WorkerAgent
        from core.multi_agent_v2.agents.reviewer.reviewer_agent import ReviewerAgent
        from core.multi_agent_v2.agents.expert.expert_agent import ExpertAgent

        creators = {
            "master": lambda: MasterAgent(
                agent_id=str(uuid.uuid4()),
                name=f"Master-{uuid.uuid4().hex[:8]}"
            ),
            "worker": lambda: WorkerAgent(
                agent_id=str(uuid.uuid4()),
                name=f"Worker-{uuid.uuid4().hex[:8]}",
                specialization="general"
            ),
            "reviewer": lambda: ReviewerAgent(
                agent_id=str(uuid.uuid4()),
                name=f"Reviewer-{uuid.uuid4().hex[:8]}"
            ),
            "expert": lambda: ExpertAgent(
                agent_id=str(uuid.uuid4()),
                name=f"Expert-{uuid.uuid4().hex[:8]}",
                specialization="general"
            )
        }

        if agent_type not in creators:
            raise ValueError(f"Unknown agent type: {agent_type}")

        agent = creators[agent_type]()
        return agent

    async def _reset_agent(self, agent) -> None:
        """重置Agent状态"""
        if hasattr(agent, 'reset_state'):
            agent.reset_state()
        elif hasattr(agent, 'state'):
            from core.multi_agent_v2.agents.base.base_agent import AgentState
            agent.state = AgentState.IDLE
            if hasattr(agent, 'current_task'):
                agent.current_task = None

        if hasattr(agent, 'reset_memory'):
            agent.reset_memory()

    async def _wake_up_agent(self, agent) -> None:
        """唤醒Agent"""
        if hasattr(agent, 'wake_up'):
            await agent.wake_up()
        elif hasattr(agent, 'state'):
            from core.multi_agent_v2.agents.base.base_agent import AgentState
            agent.state = AgentState.IDLE

    async def _shutdown_agent(self, agent) -> None:
        """销毁Agent"""
        if hasattr(agent, 'stop'):
            await agent.stop()
        elif hasattr(agent, 'shutdown'):
            await agent.shutdown()

    async def _cleanup_idle_agents(self) -> None:
        """清理空闲Agent（后台任务）"""
        try:
            while True:
                await asyncio.sleep(60)
                await self._cleanup_once()
        except asyncio.CancelledError:
            logger.info("Cleanup task cancelled")
        except Exception as e:
            logger.error(f"Cleanup task error: {e}")

    async def _cleanup_once(self) -> None:
        """执行一次清理"""
        for agent_type, pool in self.pools.items():
            if len(pool) > self.max_pool_size_per_type:
                excess = pool[self.max_pool_size_per_type:]
                pool[:] = pool[:self.max_pool_size_per_type]
                self.stats.current_pooled[agent_type] = len(pool)

                for agent in excess:
                    await self._shutdown_agent(agent)
                logger.info(f"Cleaned up {len(excess)} {agent_type} agents")

    def get_stats(self) -> Dict[str, Any]:
        """获取完整统计信息"""
        return self.stats.get_summary()


_global_pool: Optional[AgentPool] = None


def get_agent_pool() -> AgentPool:
    """获取全局Agent池"""
    global _global_pool
    if _global_pool is None:
        _global_pool = AgentPool()
    return _global_pool


async def init_agent_pool() -> None:
    """初始化并启动Agent池"""
    pool = get_agent_pool()
    await pool.start()


async def shutdown_agent_pool() -> None:
    """关闭Agent池"""
    global _global_pool
    if _global_pool:
        await _global_pool.stop()
        _global_pool = None
