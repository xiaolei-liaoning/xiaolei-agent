"""
LazyAgent - 懒加载Agent包装器
只在真正需要时才初始化实际的Agent
"""

import asyncio
import logging
import uuid
import time
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class LazyLoadStage(Enum):
    """懒加载阶段"""
    CREATED = "created"
    INITIALIZING = "initializing"
    READY = "ready"
    ERROR = "error"


class LazyAgent:
    """懒加载Agent - 包装器"""

    def __init__(
        self,
        agent_type: str,
        agent_creator: Optional[Callable] = None,
        lazy: bool = True
    ):
        self.agent_type = agent_type
        self.agent_id = str(uuid.uuid4())
        self.agent_creator = agent_creator

        self.load_stage = LazyLoadStage.CREATED
        self.actual_agent: Optional[Any] = None
        self.init_error: Optional[Exception] = None

        self._lightweight_state = {
            "state": "idle",
            "created_at": time.time(),
            "last_activity": time.time()
        }

        if not lazy:
            asyncio.create_task(self.ensure_initialized())

        logger.debug(f"LazyAgent created: {self.agent_type} (lazy={lazy})")

    async def ensure_initialized(self, force: bool = False) -> Any:
        """确保Agent已初始化"""
        if self.load_stage == LazyLoadStage.READY and not force:
            return self.actual_agent

        if self.load_stage == LazyLoadStage.INITIALIZING:
            logger.debug(f"Waiting for {self.agent_type} to initialize...")
            await asyncio.sleep(0.1)
            return await self.ensure_initialized()

        self.load_stage = LazyLoadStage.INITIALIZING
        logger.info(f"Lazy initializing {self.agent_type}...")

        try:
            start_time = time.time()
            self.actual_agent = await self._create_actual_agent()
            self.load_stage = LazyLoadStage.READY
            elapsed = time.time() - start_time
            logger.info(f"{self.agent_type} initialized in {elapsed:.2f}s")
            return self.actual_agent
        except Exception as e:
            self.load_stage = LazyLoadStage.ERROR
            self.init_error = e
            logger.error(f"Failed to initialize {self.agent_type}: {e}")
            raise

    async def _create_actual_agent(self) -> Any:
        """创建实际的Agent"""
        if self.agent_creator:
            return self.agent_creator()

        from core.multi_agent_v2.agents.master.master_agent import MasterAgent
        from core.multi_agent_v2.agents.worker.worker_agent import WorkerAgent
        from core.multi_agent_v2.agents.reviewer.reviewer_agent import ReviewerAgent
        from core.multi_agent_v2.agents.expert.expert_agent import ExpertAgent

        creators = {
            "master": lambda: MasterAgent(
                agent_id=self.agent_id,
                name=f"LazyMaster-{uuid.uuid4().hex[:6]}"
            ),
            "worker": lambda: WorkerAgent(
                agent_id=self.agent_id,
                name=f"LazyWorker-{uuid.uuid4().hex[:6]}",
                specialization="general"
            ),
            "reviewer": lambda: ReviewerAgent(
                agent_id=self.agent_id,
                name=f"LazyReviewer-{uuid.uuid4().hex[:6]}"
            ),
            "expert": lambda: ExpertAgent(
                agent_id=self.agent_id,
                name=f"LazyExpert-{uuid.uuid4().hex[:6]}",
                specialization="general"
            )
        }

        if self.agent_type not in creators:
            raise ValueError(f"Unknown agent type: {self.agent_type}")

        return creators[self.agent_type]()

    async def execute(self, task: Any) -> Any:
        """执行任务（代理方法）"""
        agent = await self.ensure_initialized()
        self._lightweight_state["last_activity"] = time.time()
        return await agent.execute(task)

    def reset_state(self) -> None:
        """重置状态"""
        if self.actual_agent and hasattr(self.actual_agent, 'reset_state'):
            self.actual_agent.reset_state()
        self._lightweight_state["state"] = "idle"

    def get_lightweight_state(self) -> Dict[str, Any]:
        """获取轻量级状态（不初始化）"""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "load_stage": self.load_stage.value,
            **self._lightweight_state
        }

    def is_ready(self) -> bool:
        """是否已就绪"""
        return self.load_stage == LazyLoadStage.READY

    def memory_estimate(self) -> int:
        """估算内存占用"""
        if self.load_stage == LazyLoadStage.READY and self.actual_agent:
            import sys
            try:
                return sys.getsizeof(self.actual_agent)
            except:
                pass
        return 500

    async def unload(self) -> None:
        """卸载（释放真实Agent，但保留包装器）"""
        if self.actual_agent:
            if hasattr(self.actual_agent, 'stop'):
                await self.actual_agent.stop()
            self.actual_agent = None
            self.load_stage = LazyLoadStage.CREATED
            logger.info(f"{self.agent_type} unloaded")

    def __getattr__(self, name):
        """动态代理到实际Agent"""
        if self.actual_agent:
            return getattr(self.actual_agent, name)
        raise AttributeError(
            f"LazyAgent not initialized. Call ensure_initialized() first. "
            f"(Attribute: {name})"
        )


class LazyAgentFactory:
    """懒加载Agent工厂"""

    def __init__(self):
        self.lazy_agents: Dict[str, LazyAgent] = {}
        self.preloaded_types = set()

    def create_lazy_agent(
        self,
        agent_type: str,
        agent_creator: Optional[Callable] = None
    ) -> LazyAgent:
        """创建一个懒加载Agent"""
        lazy_agent = LazyAgent(agent_type, agent_creator, lazy=True)
        self.lazy_agents[lazy_agent.agent_id] = lazy_agent
        return lazy_agent

    async def preload(self, agent_types: list) -> None:
        """预加载某些类型的Agent（后台）"""
        for agent_type in agent_types:
            if agent_type not in self.preloaded_types:
                logger.info(f"Preloading {agent_type}...")
                lazy_agent = self.create_lazy_agent(agent_type)
                asyncio.create_task(lazy_agent.ensure_initialized())
                self.preloaded_types.add(agent_type)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计"""
        stats = {
            "total": len(self.lazy_agents),
            "by_type": {},
            "by_stage": {
                stage.value: 0 for stage in LazyLoadStage
            },
            "total_memory_estimate": 0
        }

        for agent in self.lazy_agents.values():
            stats["by_type"][agent.agent_type] = \
                stats["by_type"].get(agent.agent_type, 0) + 1

            stats["by_stage"][agent.load_stage.value] += 1

            stats["total_memory_estimate"] += agent.memory_estimate()

        total_mb = stats["total_memory_estimate"] / (1024 * 1024)
        stats["total_memory_mb"] = round(total_mb, 2)

        return stats

    async def cleanup_unused(self, idle_threshold: float = 300) -> None:
        """清理长时间未使用的Agent"""
        now = time.time()

        for agent_id, agent in self.lazy_agents.items():
            state = agent.get_lightweight_state()
            idle_time = now - state["last_activity"]

            if idle_time > idle_threshold and agent.is_ready():
                await agent.unload()
                logger.info(f"Unloaded idle agent: {agent.agent_type}")


_global_lazy_factory: Optional[LazyAgentFactory] = None


def get_lazy_factory() -> LazyAgentFactory:
    """获取全局懒加载工厂"""
    global _global_lazy_factory
    if _global_lazy_factory is None:
        _global_lazy_factory = LazyAgentFactory()
    return _global_lazy_factory
