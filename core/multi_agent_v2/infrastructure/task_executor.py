"""
TaskExecutor - 任务执行器

职责：
1. 接收 ScheduleResult，将执行委托给选中的 CollaborationStrategy
2. 超时控制、状态更新、异常兜底（不再是直接调 agent.act()）
3. 更新 SharedBus 任务快照状态

消除双路执行混乱：TaskExecutor 不再直接执行 agent.act()，
而是委托给 schedule_result 中选定的协作策略。
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from core.multi_agent_v2.agents.base.base_agent import BaseAgent, Task, ActionResult
from core.multi_agent_v2.orchestration.scheduler.intelligent_scheduler import (
    ScheduleResult, CollaborationMode as SchedulerMode
)
from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus, TaskSnapshot
from core.multi_agent_v2.infrastructure.persistence import get_snapshot_store
from core.multi_agent_v2.orchestration.scheduler.result_aggregator import ResultAggregator
from core.multi_agent_v2.orchestration.context.global_context_center import (
    GlobalContextCenter
)

logger = logging.getLogger(__name__)


class TaskExecutor:
    """任务执行器 - 连接 Scheduler 和 CollaborationStrategy 的桥梁"""

    def __init__(self, agent_pool: Optional[Any] = None):
        self.agent_pool = agent_pool
        self._bus = get_shared_bus()
        self._aggregator = ResultAggregator()
        self._snapshot_store = get_snapshot_store()

    async def execute(
        self,
        schedule_result: ScheduleResult,
        original_task: Task,
        timeout: float = 300.0
    ) -> Dict[str, Any]:
        """执行调度结果

        TaskExecutor 不再直接调 agent.act()，而是委托给选中的 CollaborationStrategy。

        Args:
            schedule_result: 调度结果（含选中的协作模式）
            original_task: 原始任务
            timeout: 超时时间（秒），默认5分钟

        Returns:
            执行结果字典
        """
        start_time = time.time()
        task_id = schedule_result.task_id

        logger.info(
            f"开始执行任务: {task_id}, "
            f"模式: {schedule_result.collaboration_mode.value}"
        )

        # 更新任务状态为 running
        await self._update_snapshot_status(task_id, "running")

        # Persist initial snapshot
        await self._snapshot_store.save(schedule_result.task_id, {
            "task_id": schedule_result.task_id,
            "status": "running",
            "original_request": original_task.description,
            "collaboration_mode": schedule_result.collaboration_mode.value,
            "assigned_agents": dict(schedule_result.assigned_agents),
            "execution_plan": schedule_result.execution_plan,
        })

        try:
            # 从 AgentPool 获取所有被分配的 Agent
            agents = await self._resolve_assigned_agents(schedule_result)
            if not agents:
                raise RuntimeError("没有可用的 Agent 执行任务")

            # 选择并实例化协作策略
            strategy = self._select_strategy(schedule_result.collaboration_mode)
            if not strategy:
                raise RuntimeError(
                    f"不支持的协作模式: {schedule_result.collaboration_mode}"
                )

            # 委托给策略执行（带超时保护）
            collaboration_result = await asyncio.wait_for(
                strategy.execute(
                    task=original_task,
                    agents=agents,
                    execution_plan=schedule_result.execution_plan
                ),
                timeout=timeout
            )

            execution_time = time.time() - start_time

            # Aggregate results through ResultAggregator
            extracted_results = self._extract_results(collaboration_result)
            aggregated = self._aggregate_results(extracted_results, original_task.description)

            # 更新最终状态
            final_status = "completed" if collaboration_result.success else "failed"
            await self._update_snapshot_status(task_id, final_status)

            # Persist final snapshot with aggregated results
            await self._snapshot_store.update_status(
                schedule_result.task_id,
                final_status,
                {
                    "final_result": {
                        "success": collaboration_result.success,
                        "results": extracted_results,
                        "aggregated": aggregated,
                        "execution_time": execution_time,
                    }
                }
            )

            logger.info(
                f"任务执行完成: {task_id}, "
                f"耗时: {execution_time:.2f}s, "
                f"成功: {collaboration_result.success}"
            )

            # 共享记忆 + 清理 Agent
            if self.agent_pool:
                if hasattr(self.agent_pool, 'share_memory'):
                    await self.agent_pool.share_memory(agents)
                if hasattr(self.agent_pool, 'discard'):
                    await self.agent_pool.discard(agents)

            return {
                "success": collaboration_result.success,
                "results": extracted_results,
                "aggregated": aggregated,
                "execution_time": execution_time,
                "task_id": task_id,
                "executed_by": f"strategy:{schedule_result.collaboration_mode.value}",
            }

        except asyncio.TimeoutError:
            logger.error(f"任务执行超时: {task_id}")
            await self._update_snapshot_status(task_id, "timeout")
            return {
                "success": False,
                "error": f"任务执行超时 ({timeout}s)",
                "execution_time": time.time() - start_time,
                "task_id": task_id,
            }
        except Exception as e:
            logger.error(f"任务执行异常: {task_id}, 错误: {e}")
            await self._update_snapshot_status(task_id, "failed")
            return {
                "success": False,
                "error": str(e),
                "execution_time": time.time() - start_time,
                "task_id": task_id,
            }

    # ── 策略工厂 ──────────────────────────────────────────────────────

    _STRATEGY_REGISTRY = {}  # 延迟加载

    @classmethod
    def _get_strategy_registry(cls):
        """延迟加载策略映射"""
        if cls._STRATEGY_REGISTRY:
            return cls._STRATEGY_REGISTRY

        from core.multi_agent_v2.orchestration.context.global_context_center import (
            GlobalContextCenter
        )
        context = GlobalContextCenter()

        from core.multi_agent_v2.orchestration.collaboration.strategies.pipeline import (
            PipelineStrategy
        )
        from core.multi_agent_v2.orchestration.collaboration.strategies.master_worker import (
            MasterSlaveStrategy
        )
        from core.multi_agent_v2.orchestration.collaboration.strategies.review import (
            ReviewStrategy
        )
        from core.multi_agent_v2.orchestration.collaboration.strategies.auction import (
            AuctionStrategy
        )
        from core.multi_agent_v2.orchestration.collaboration.strategies.base import (
            HybridStrategy
        )

        cls._STRATEGY_REGISTRY = {
            SchedulerMode.PIPELINE: PipelineStrategy(context),
            SchedulerMode.MASTER_SLAVE: MasterSlaveStrategy(context),
            SchedulerMode.REVIEW: ReviewStrategy(context),
            SchedulerMode.AUCTION: AuctionStrategy(context),
        }
        return cls._STRATEGY_REGISTRY

    def _select_strategy(self, mode: SchedulerMode):
        """根据协作模式选择对应的策略实例"""
        registry = self._get_strategy_registry()
        strategy = registry.get(mode)
        if strategy:
            return strategy

        # 兜底：未知模式走混合策略
        from core.multi_agent_v2.orchestration.collaboration.strategies.base import (
            HybridStrategy
        )
        logger.warning(f"未知协作模式 {mode}，使用 HybridStrategy 兜底")
        return HybridStrategy(GlobalContextCenter())

    # ── Agent 解析 ────────────────────────────────────────────────────

    async def _resolve_assigned_agents(
        self, schedule_result: ScheduleResult
    ) -> List[BaseAgent]:
        """从 AgentPool 解析所有被分配的 Agent 实例"""
        agents = []
        seen_ids = set()

        for subtask_id, agent_id in schedule_result.assigned_agents.items():
            agent = await self._get_agent_by_type_or_any(agent_id)
            if agent and agent.agent_id not in seen_ids:
                agents.append(agent)
                seen_ids.add(agent.agent_id)

        if not agents:
            logger.warning("未能从池中获取任何 Agent")
            return []

        logger.info(f"已解析 {len(agents)} 个 Agent 用于执行")
        return agents

    async def _get_agent_by_type_or_any(self, preferred_agent_id: str = None):
        """从 AgentPool 获取可用Agent"""
        if not self.agent_pool:
            logger.warning("AgentPool 未配置")
            return None

        # 尝试从 active_agents 获取
        if preferred_agent_id and hasattr(self.agent_pool, 'active_agents'):
            if preferred_agent_id in self.agent_pool.active_agents:
                return self.agent_pool.active_agents[preferred_agent_id]

        # 从 pools 中 acquire
        if hasattr(self.agent_pool, 'pools'):
            for pool_type in self.agent_pool.pools.keys():
                agent = await self.agent_pool.acquire(pool_type)
                if agent:
                    return agent

        logger.warning("Pool中无可用Agent")
        return None

    # ── 结果处理 ──────────────────────────────────────────────────────

    def _aggregate_results(
        self,
        raw_results: List[Dict[str, Any]],
        task_description: str,
    ) -> Dict[str, Any]:
        """将原始执行结果通过 ResultAggregator 去重、冲突解决、质量评分"""
        return self._aggregator.aggregate(raw_results, task_description)

    def _log(self, level: str, message: str, task_id: str = "", **extra) -> None:
        """结构化日志，携带额外上下文"""
        log_fn = getattr(logger, level, logger.info)
        extra_str = " ".join(f"{k}={v}" for k, v in extra.items())
        log_fn(f"[task={task_id}] {message} {extra_str}")

    def _extract_results(self, collaboration_result) -> List[Dict[str, Any]]:
        """从 CollaborationResult 提取统一格式的执行结果"""
        results = []

        # 从 agent_results 提取
        for agent_id, action_result in collaboration_result.agent_results.items():
            results.append({
                "agent_id": agent_id,
                "success": action_result.success if hasattr(action_result, 'success') else True,
                "output": action_result.output if hasattr(action_result, 'output') else str(action_result),
                "execution_time": action_result.execution_time if hasattr(action_result, 'execution_time') else 0,
            })

        # 如果没有细粒度结果，添加整体结果
        if not results:
            results.append({
                "agent_id": "strategy",
                "success": collaboration_result.success,
                "output": collaboration_result.final_result,
                "execution_time": collaboration_result.execution_time,
            })

        return results

    # ── 状态同步 ──────────────────────────────────────────────────────

    async def _update_snapshot_status(self, task_id: str, status: str) -> None:
        """更新 SharedBus 中的任务快照状态"""
        try:
            snapshot = await self._bus.get_snapshot(task_id)
            if snapshot:
                snapshot.status = status
                await self._bus.save_snapshot(snapshot)
        except Exception as e:
            logger.debug(f"更新任务快照失败: {e}")

    # ── 向后兼容方法 ──────────────────────────────────────────────────

    async def _get_agent(self, agent_id: str):
        """从 AgentPool 获取 Agent（保留旧接口兼容）"""
        return await self._get_agent_by_type_or_any(agent_id)
