"""
协作策略 - 实现不同的多Agent协作模式

包含：
1. 流水线模式 - 顺序执行，每个阶段专注特定任务
2. 主从模式 - 主Agent分解+聚合，从Agent执行
3. 评审模式 - 多Agent并行，结果通过评审达成共识
4. 拍卖模式 - 任务发布后，最适合的Agent"竞标"执行
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import uuid

from core.multi_agent_v2.agents.base.base_agent import (
    BaseAgent, Task, ActionResult
)
from core.multi_agent_v2.orchestration.context.global_context_center import (
    GlobalContextCenter, TaskState
)

logger = logging.getLogger(__name__)


@dataclass
class CollaborationResult:
    """协作结果"""
    task_id: str
    success: bool
    final_result: Any
    partial_results: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    agent_results: Dict[str, ActionResult] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


class BaseCollaborationStrategy(ABC):
    """协作策略基类"""

    def __init__(self, context_center: GlobalContextCenter):
        self.context_center = context_center

    @abstractmethod
    async def execute(
        self,
        task: Task,
        agents: List[BaseAgent],
        execution_plan: List[Dict[str, Any]]
    ) -> CollaborationResult:
        """执行协作"""
        pass

    async def _execute_agent_task(
        self,
        agent: BaseAgent,
        subtask_id: str,
        task_data: Dict[str, Any]
    ) -> Tuple[str, ActionResult]:
        """执行单个Agent任务"""
        start_time = time.time()

        try:
            # 创建子任务
            subtask = Task(
                task_id=subtask_id,
                type=task_data.get("type", "subtask"),
                description=task_data.get("description", ""),
                keywords=task_data.get("keywords", []),
                complexity=task_data.get("complexity", 0.5)
            )

            # Agent思考
            thought = await agent.think(subtask)

            # Agent执行
            result = await agent.act(thought.plan)

            # Agent反思
            await agent.reflect(result)

            # 记录成功
            execution_time = time.time() - start_time
            await self.context_center.context_center.update_agent_state(
                agent.agent_id, "idle"
            )

            return subtask_id, result

        except Exception as e:
            logger.error(f"Agent {agent.agent_id} 执行任务 {subtask_id} 失败: {e}")

            return subtask_id, ActionResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time
            )


class PipelineStrategy(BaseCollaborationStrategy):
    """流水线协作策略 - 顺序执行，每个阶段专注特定任务"""

    async def execute(
        self,
        task: Task,
        agents: List[BaseAgent],
        execution_plan: List[Dict[str, Any]]
    ) -> CollaborationResult:
        """流水线执行

        流程：
        1. 将任务分解为多个阶段
        2. 每个阶段分配给专门的Agent
        3. 每个Agent只完成特定阶段的工作
        4. 阶段之间通过上下文传递结果
        """
        start_time = time.time()
        partial_results = {}
        agent_results = {}

        logger.info(f"开始流水线执行: {task.task_id}, 计划: {len(execution_plan)} 个步骤")

        # 更新任务状态
        await self.context_center.update_task_state(task.task_id, TaskState.RUNNING)

        # 按步骤顺序执行
        for i, step in enumerate(execution_plan):
            step_name = step.get("subtask_id")
            agent_id = step.get("agent_id")

            # 获取Agent
            agent = next((a for a in agents if a.agent_id == agent_id), None)
            if not agent:
                logger.error(f"未找到Agent: {agent_id}")
                continue

            logger.info(f"流水线步骤 {i+1}/{len(execution_plan)}: {step_name} -> Agent {agent_id}")

            # 更新上下文，传递之前的结果
            context_data = {
                "step": i,
                "previous_results": partial_results,
                "total_steps": len(execution_plan)
            }

            # 执行步骤
            subtask_id, result = await self._execute_agent_task(
                agent,
                step_name,
                {
                    "type": f"pipeline_step_{i}",
                    "description": f"执行流水线第 {i+1} 步",
                    "keywords": task.keywords,
                    "complexity": task.complexity / len(execution_plan),
                    "context": context_data
                }
            )

            # 记录结果
            agent_results[agent_id] = result

            if result.success:
                partial_results[step_name] = result.output
                # 更新全局上下文，传递结果给下一个阶段
                await self.context_center.update_context(
                    task.task_id, agent_id, f"step_{i}_result", result.output
                )
            else:
                logger.error(f"步骤 {step_name} 执行失败: {result.error}")
                partial_results[step_name] = None

                # 流水线模式中，步骤失败会导致整个流程失败
                break

        # 计算最终结果
        final_result = self._aggregate_pipeline_results(partial_results)

        # 更新任务状态
        if all(r is not None for r in partial_results.values()):
            await self.context_center.update_task_state(task.task_id, TaskState.COMPLETED)
        else:
            await self.context_center.update_task_state(task.task_id, TaskState.FAILED)

        execution_time = time.time() - start_time

        return CollaborationResult(
            task_id=task.task_id,
            success=all(r is not None for r in partial_results.values()),
            final_result=final_result,
            partial_results=partial_results,
            execution_time=execution_time,
            agent_results=agent_results
        )

    def _aggregate_pipeline_results(self, partial_results: Dict[str, Any]) -> Any:
        """聚合流水线结果"""
        # 简单实现：返回最后一个成功的结果
        successful_results = [r for r in partial_results.values() if r is not None]
        return successful_results[-1] if successful_results else None


class MasterSlaveStrategy(BaseCollaborationStrategy):
    """主从协作策略 - 主Agent分解+聚合，从Agent执行"""

    async def execute(
        self,
        task: Task,
        agents: List[BaseAgent],
        execution_plan: List[Dict[str, Any]]
    ) -> CollaborationResult:
        """主从执行

        流程：
        1. 主Agent理解任务，分解为子任务
        2. 主Agent将子任务分配给从Agent
        3. 从Agent并行执行子任务
        4. 主Agent收集结果，进行聚合和校验
        """
        start_time = time.time()
        partial_results = {}
        agent_results = {}

        # 分离Master和Slave
        master_agent = None
        slave_agents = []

        for plan in execution_plan:
            agent_id = plan.get("agent_id")
            role = plan.get("role", "worker")
            agent = next((a for a in agents if a.agent_id == agent_id), None)

            if not agent:
                continue

            if role == "master" or plan.get("agent_type") == "master":
                master_agent = agent
            else:
                slave_agents.append(agent)

        if not master_agent:
            logger.error("未找到Master Agent")
            return CollaborationResult(
                task_id=task.task_id,
                success=False,
                final_result=None,
                errors=["未找到Master Agent"]
            )

        logger.info(f"开始主从执行: {task.task_id}, Master: {master_agent.agent_id}, Slaves: {len(slave_agents)}")

        # 更新任务状态
        await self.context_center.update_task_state(task.task_id, TaskState.RUNNING)

        # Master分析任务并分解
        master_task = Task(
            task_id=f"{task.task_id}_decompose",
            type="task_decomposition",
            description=f"分解任务: {task.description}",
            keywords=task.keywords,
            complexity=task.complexity * 0.3
        )

        master_thought = await master_agent.think(master_task)

        # Master创建执行计划
        decomposition_plan = await self._create_decomposition_plan(task, len(slave_agents))

        logger.info(f"Master分解任务为 {len(decomposition_plan)} 个子任务")

        # 并行执行子任务
        subtasks = []
        for i, (subtask_data, slave) in enumerate(zip(decomposition_plan, slave_agents)):
            subtask_id = f"{task.task_id}_subtask_{i}"

            subtasks.append(
                self._execute_agent_task(
                    slave,
                    subtask_id,
                    {
                        "type": "worker",
                        "description": subtask_data["description"],
                        "keywords": task.keywords,
                        "complexity": subtask_data["complexity"],
                        "context": {"master_plan": decomposition_plan}
                    }
                )
            )

        # 等待所有子任务完成
        results = await asyncio.gather(*subtasks, return_exceptions=True)

        # 收集结果
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"子任务执行异常: {result}")
                continue

            subtask_id, action_result = result
            agent_results[subtask_id] = action_result

            if action_result.success:
                partial_results[subtask_id] = action_result.output

        # Master聚合结果
        aggregated_result = await self._aggregate_slave_results(master_agent, partial_results)

        # Master进行校验
        validation_result = await self._validate_results(master_agent, aggregated_result)

        # 更新任务状态
        if validation_result["valid"]:
            await self.context_center.update_task_state(task.task_id, TaskState.COMPLETED)
        else:
            # 尝试修复
            await self._attempt_recovery(master_agent, partial_results, validation_result)

        execution_time = time.time() - start_time

        return CollaborationResult(
            task_id=task.task_id,
            success=validation_result["valid"],
            final_result=aggregated_result,
            partial_results=partial_results,
            execution_time=execution_time,
            agent_results=agent_results,
            errors=validation_result.get("errors", [])
        )

    async def _create_decomposition_plan(self, task: Task, num_slaves: int) -> List[Dict[str, Any]]:
        """创建分解计划"""
        # 简化实现：平均分解
        step_complexity = task.complexity / num_slaves

        return [
            {
                "description": f"执行任务部分 {i+1}/{num_slaves}",
                "complexity": step_complexity,
                "keywords": task.keywords
            }
            for i in range(num_slaves)
        ]

    async def _aggregate_slave_results(self, master: BaseAgent, partial_results: Dict[str, Any]) -> Any:
        """聚合从Agent结果"""
        # 简单实现：合并所有结果
        successful_results = [r for r in partial_results.values() if r is not None]

        if not successful_results:
            return None

        # 如果是字典，合并
        if isinstance(successful_results[0], dict):
            return {"aggregated": successful_results}

        # 否则返回列表
        return successful_results

    async def _validate_results(self, master: BaseAgent, result: Any) -> Dict[str, Any]:
        """验证结果"""
        # 简单实现：检查结果是否存在
        if result is None:
            return {"valid": False, "errors": ["结果为空"]}

        return {"valid": True, "errors": []}

    async def _attempt_recovery(self, master: BaseAgent, partial_results: Dict, validation: Dict) -> None:
        """尝试恢复"""
        logger.warning("结果验证失败，尝试恢复")


class ReviewStrategy(BaseCollaborationStrategy):
    """评审协作策略 - 多Agent并行，结果通过评审达成共识"""

    async def execute(
        self,
        task: Task,
        agents: List[BaseAgent],
        execution_plan: List[Dict[str, Any]]
    ) -> CollaborationResult:
        """评审执行

        流程：
        1. 多个Worker Agent并行执行任务
        2. 各Worker提交结果
        3. 评审Agent对结果进行评审
        4. 如有分歧，进行多轮评审和讨论
        5. 达成共识后输出最终结果
        """
        start_time = time.time()
        worker_results = {}
        agent_results = {}

        # 分离Worker和Reviewer
        workers = []
        reviewers = []

        for plan in execution_plan:
            agent_id = plan.get("agent_id")
            role = plan.get("role", "worker")
            agent = next((a for a in agents if a.agent_id == agent_id), None)

            if not agent:
                continue

            if role == "reviewer" or plan.get("agent_type") == "reviewer":
                reviewers.append(agent)
            else:
                workers.append(agent)

        if not reviewers:
            logger.warning("未找到Reviewer，使用默认评审")
            reviewers = workers[:1] if workers else []
            workers = workers[1:] if len(workers) > 1 else workers

        logger.info(f"开始评审执行: {task.task_id}, Workers: {len(workers)}, Reviewers: {len(reviewers)}")

        # 更新任务状态
        await self.context_center.update_task_state(task.task_id, TaskState.RUNNING)

        # 第一轮：Worker并行执行
        subtasks = []
        for i, worker in enumerate(workers):
            subtask_id = f"{task.task_id}_work_{i}"

            subtasks.append(
                self._execute_agent_task(
                    worker,
                    subtask_id,
                    {
                        "type": "worker",
                        "description": f"执行评审任务 {i+1}",
                        "keywords": task.keywords,
                        "complexity": task.complexity
                    }
                )
            )

        # 等待Worker完成
        worker_task_results = await asyncio.gather(*subtasks, return_exceptions=True)

        # 收集Worker结果
        for result in worker_task_results:
            if isinstance(result, Exception):
                logger.error(f"Worker执行异常: {result}")
                continue

            subtask_id, action_result = result
            agent_results[subtask_id] = action_result

            if action_result.success:
                worker_results[subtask_id] = action_result.output

        logger.info(f"Worker执行完成，{len(worker_results)} 个成功")

        # 第二轮：评审
        review_results = await self._perform_review(reviewers, worker_results)

        # 第三轮：共识达成
        final_result = await self._reach_consensus(reviewers, worker_results, review_results)

        # 更新任务状态
        if final_result:
            await self.context_center.update_task_state(task.task_id, TaskState.COMPLETED)
        else:
            await self.context_center.update_task_state(task.task_id, TaskState.FAILED)

        execution_time = time.time() - start_time

        return CollaborationResult(
            task_id=task.task_id,
            success=final_result is not None,
            final_result=final_result,
            partial_results=worker_results,
            execution_time=execution_time,
            agent_results=agent_results
        )

    async def _perform_review(self, reviewers: List[BaseAgent], worker_results: Dict[str, Any]) -> Dict[str, Any]:
        """执行评审"""
        review_results = {}

        for i, reviewer in enumerate(reviewers):
            review_task = Task(
                task_id=f"review_{i}",
                type="review",
                description="评审执行结果",
                keywords=task.keywords if 'task' in locals() else [],
                complexity=0.5
            )

            thought = await reviewer.think(review_task)

            # 评审逻辑（简化）
            review_result = {
                "approved": len(worker_results) > 0,
                "comments": f"评审 {i+1} 完成",
                "suggestions": []
            }

            review_results[f"reviewer_{i}"] = review_result

        return review_results

    async def _reach_consensus(
        self,
        reviewers: List[BaseAgent],
        worker_results: Dict[str, Any],
        review_results: Dict[str, Any]
    ) -> Any:
        """达成共识"""
        # 简单实现：多数评审通过即成功
        approved_count = sum(1 for r in review_results.values() if r.get("approved"))

        if approved_count >= len(reviewers) / 2:
            # 返回所有worker结果的综合
            successful = [r for r in worker_results.values() if r is not None]
            return {"consensus": True, "results": successful}

        return None


class AuctionStrategy(BaseCollaborationStrategy):
    """拍卖协作策略 - 任务发布后，最适合的Agent竞标执行"""

    async def execute(
        self,
        task: Task,
        agents: List[BaseAgent],
        execution_plan: List[Dict[str, Any]]
    ) -> CollaborationResult:
        """拍卖执行

        流程：
        1. 任务发布到Agent池
        2. 各Agent根据自身能力评估任务
        3. 符合条件的Agent提交投标（Bid）
        4. 调度器选择最优的Agent执行
        5. 执行过程中其他Agent待命
        """
        start_time = time.time()
        agent_results = {}

        logger.info(f"开始拍卖执行: {task.task_id}")

        # 更新任务状态
        await self.context_center.update_task_state(task.task_id, TaskState.RUNNING)

        # 获取中标Agent
        if not execution_plan:
            return CollaborationResult(
                task_id=task.task_id,
                success=False,
                final_result=None,
                errors=["没有Agent参与拍卖"]
            )

        winner_plan = execution_plan[0]  # 简化：直接取第一个
        winner_id = winner_plan.get("agent_id")

        winner = next((a for a in agents if a.agent_id == winner_id), None)

        if not winner:
            return CollaborationResult(
                task_id=task.task_id,
                success=False,
                final_result=None,
                errors=[f"中标Agent {winner_id} 不存在"]
            )

        logger.info(f"拍卖结果: Agent {winner_id} 中标")

        # 执行任务
        subtask_id, result = await self._execute_agent_task(
            winner,
            task.task_id,
            {
                "type": "auction",
                "description": task.description,
                "keywords": task.keywords,
                "complexity": task.complexity
            }
        )

        agent_results[winner_id] = result

        # 更新任务状态
        if result.success:
            await self.context_center.update_task_state(task.task_id, TaskState.COMPLETED)
        else:
            await self.context_center.update_task_state(task.task_id, TaskState.FAILED)

        execution_time = time.time() - start_time

        return CollaborationResult(
            task_id=task.task_id,
            success=result.success,
            final_result=result.output,
            execution_time=execution_time,
            agent_results=agent_results,
            errors=[result.error] if result.error else []
        )


class HybridStrategy(BaseCollaborationStrategy):
    """混合协作策略 - 根据任务特征动态组合多种模式"""

    async def execute(
        self,
        task: Task,
        agents: List[BaseAgent],
        execution_plan: List[Dict[str, Any]]
    ) -> CollaborationResult:
        """混合执行 - 根据任务特征选择最合适的策略"""

        # 根据任务复杂度选择策略
        if task.complexity < 0.3:
            # 简单任务：直接执行
            return await self._execute_simple_task(task, agents)
        elif task.complexity < 0.6:
            # 中等复杂度：主从模式
            strategy = MasterSlaveStrategy(self.context_center)
            return await strategy.execute(task, agents, execution_plan)
        else:
            # 复杂任务：评审模式
            strategy = ReviewStrategy(self.context_center)
            return await strategy.execute(task, agents, execution_plan)

    async def _execute_simple_task(self, task: Task, agents: List[BaseAgent]) -> CollaborationResult:
        """执行简单任务"""
        start_time = time.time()

        # 直接选择第一个可用Agent
        agent = agents[0] if agents else None

        if not agent:
            return CollaborationResult(
                task_id=task.task_id,
                success=False,
                final_result=None,
                errors=["没有可用Agent"]
            )

        subtask_id, result = await self._execute_agent_task(
            agent,
            task.task_id,
            {
                "type": "simple",
                "description": task.description,
                "keywords": task.keywords,
                "complexity": task.complexity
            }
        )

        await self.context_center.update_task_state(
            task.task_id,
            TaskState.COMPLETED if result.success else TaskState.FAILED
        )

        return CollaborationResult(
            task_id=task.task_id,
            success=result.success,
            final_result=result.output,
            execution_time=time.time() - start_time,
            agent_results={agent.agent_id: result}
        )
