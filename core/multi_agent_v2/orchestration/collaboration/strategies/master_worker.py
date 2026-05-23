"""
主从协作策略 - 主Agent分解+聚合，从Agent执行
"""

import asyncio
import logging
import time
from typing import Any, Dict, List

from core.multi_agent_v2.agents.base.base_agent import BaseAgent, Task
from core.multi_agent_v2.orchestration.context.global_context_center import TaskState

from .base import BaseCollaborationStrategy, CollaborationResult

logger = logging.getLogger(__name__)


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
