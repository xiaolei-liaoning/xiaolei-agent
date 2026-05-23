"""
执行规划器 - 智能任务分配与执行计划编排

根据协作模式创建Agent分配和执行计划：
1. 流水线模式 - 每个步骤分配专门Agent
2. 主从模式 - Master分解任务，Worker执行
3. 评审模式 - 多Worker并行 + Reviewer
4. 拍卖模式 - 选择最优Agent
5. 混合模式 - 兜底模式
"""

import logging
from typing import Any, Dict, List, Optional

from core.multi_agent_v2.agents.base.base_agent import (
    BaseAgent, Task
)
from core.multi_agent_v2.orchestration.context.global_context_center import (
    GlobalContextCenter
)

from .capability_matcher import CapabilityMatcher
from .mode_selector import CollaborationMode

logger = logging.getLogger(__name__)


class ExecutionPlanner:
    """执行规划器 - 分配Agent并创建执行计划

    根据协作模式（流水线/主从/评审/拍卖/混合）生成对应的Agent分配方案
    和执行计划。
    """

    def __init__(self, context_center: GlobalContextCenter, matcher: CapabilityMatcher):
        self.context_center = context_center
        self.matcher = matcher
        logger.info("执行规划器初始化完成")

    async def create_plan(
        self,
        task: Task,
        agents: List[BaseAgent],
        mode: CollaborationMode,
        agent_pool: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """创建执行计划

        流程：
        1. 根据协作模式生成Agent分配（assignments）
        2. 注册分配到ContextCenter
        3. 生成带状态的执行计划

        Args:
            task: 待调度的任务
            agents: 可用Agent列表
            mode: 协作模式
            agent_pool: 保留兼容参数，不再使用

        Returns:
            执行计划列表，每项包含 subtask_id, agent_id, status 等
        """
        logger.info(f"创建执行计划: mode={mode.value}, agents_count={len(agents)}")

        # 1. 根据模式生成分配
        assignments = await self._create_assignments(task, agents, mode)

        # 2. 构建执行计划（注册到ContextCenter）
        plan = await self._build_execution_plan(assignments, task)

        logger.info(f"执行计划创建完成: {len(plan)} 个子任务")
        return plan

    async def _create_assignments(
        self,
        task: Task,
        agents: List[BaseAgent],
        mode: CollaborationMode,
    ) -> List[Dict[str, Any]]:
        """根据协作模式生成Agent分配

        每种模式有不同的分配策略：
        - PIPELINE: 每个步骤分配最匹配的Agent
        - MASTER_SLAVE: 1个Master + 多个Worker
        - REVIEW: 多个Worker + Reviewer
        - AUCTION: 最匹配的Agent
        - HYBRID: 最匹配的Agent（兜底）
        """
        if mode == CollaborationMode.PIPELINE:
            return await self._create_pipeline_assignments(task, agents)
        elif mode == CollaborationMode.MASTER_SLAVE:
            return await self._create_master_slave_assignments(task, agents)
        elif mode == CollaborationMode.REVIEW:
            return self._create_review_assignments(task, agents)
        elif mode == CollaborationMode.AUCTION:
            return await self._create_auction_assignments(task, agents)
        else:  # HYBRID
            return await self._create_hybrid_assignments(task, agents)

    async def _create_pipeline_assignments(
        self, task: Task, agents: List[BaseAgent]
    ) -> List[Dict[str, Any]]:
        """流水线模式：为每个步骤分配专门的Agent"""
        assignments = []

        for step in range(task.estimated_steps):
            subtask_id = f"{task.task_id}_step_{step}"

            step_task = Task(
                task_id=subtask_id,
                type=f"{task.type}_step_{step}",
                description=f"步骤 {step}: {task.description}",
                keywords=task.keywords,
                complexity=task.complexity / task.estimated_steps,
                estimated_steps=1
            )

            matched_agents = await self.matcher.match(step_task, agents)

            if matched_agents:
                agent, score = matched_agents[0]
                agent_type = agent.agent_type.value if hasattr(agent.agent_type, 'value') else str(agent.agent_type)
                assignments.append({
                    "subtask_id": subtask_id,
                    "agent_id": agent.agent_id,
                    "agent_type": agent_type,
                    "score": score,
                    "step": step
                })
            elif agents:
                agent = agents[step % len(agents)]
                agent_type = agent.agent_type.value if hasattr(agent.agent_type, 'value') else str(agent.agent_type)
                assignments.append({
                    "subtask_id": subtask_id,
                    "agent_id": agent.agent_id,
                    "agent_type": agent_type,
                    "score": 1.0,
                    "step": step
                })

        return assignments

    async def _create_master_slave_assignments(
        self, task: Task, agents: List[BaseAgent]
    ) -> List[Dict[str, Any]]:
        """主从模式：分配一个Master和多个Worker"""
        assignments = []

        master_task = Task(
            task_id=f"{task.task_id}_master",
            type="master",
            description="主Agent协调任务",
            keywords=task.keywords,
            complexity=task.complexity * 0.3
        )

        matched_agents = await self.matcher.match(master_task, agents)

        if matched_agents:
            master, _ = matched_agents[0]
        elif agents:
            master = agents[0]
        else:
            master = None

        if master:
            assignments.append({
                "subtask_id": f"{task.task_id}_master",
                "agent_id": master.agent_id,
                "agent_type": "master",
                "role": "master"
            })

            # 为每个子任务分配Worker
            slave_tasks = task.estimated_steps
            slave_agents = [a for a in agents if a.agent_id != master.agent_id]

            for i in range(slave_tasks):
                subtask_id = f"{task.task_id}_slave_{i}"
                slave_task = Task(
                    task_id=subtask_id,
                    type="worker",
                    description=f"执行任务 {i}",
                    keywords=task.keywords,
                    complexity=task.complexity * 0.7 / slave_tasks
                )

                matched_slaves = await self.matcher.match(slave_task, slave_agents)

                if matched_slaves:
                    slave, _ = matched_slaves[0]
                elif slave_agents:
                    slave = slave_agents[i % len(slave_agents)]
                else:
                    slave = None

                if slave:
                    assignments.append({
                        "subtask_id": subtask_id,
                        "agent_id": slave.agent_id,
                        "agent_type": "worker",
                        "role": "slave",
                        "step": i
                    })

        return assignments

    def _create_review_assignments(
        self, task: Task, agents: List[BaseAgent]
    ) -> List[Dict[str, Any]]:
        """评审模式：分配多个Worker和Reviewer

        所有 Agent 均为统一 WorkAgent（AgentType.WORKER），
        前 N-1 个作为 Worker，最后一个作为 Reviewer。
        """
        assignments = []

        # 所有 Agent 都是统一的 WorkAgent，前 N-1 个为 Worker
        for i, agent in enumerate(agents[:-1]):
            assignments.append({
                "subtask_id": f"{task.task_id}_work_{i}",
                "agent_id": agent.agent_id,
                "agent_type": "worker",
                "role": "worker"
            })

        # 最后一个为 Reviewer
        if agents:
            reviewer = agents[-1]
            assignments.append({
                "subtask_id": f"{task.task_id}_review",
                "agent_id": reviewer.agent_id,
                "agent_type": "reviewer",
                "role": "reviewer"
            })

        return assignments

    async def _create_auction_assignments(
        self, task: Task, agents: List[BaseAgent]
    ) -> List[Dict[str, Any]]:
        """拍卖模式：选择最匹配的Agent"""
        assignments = []

        matched_agents = await self.matcher.match(task, agents)

        if matched_agents:
            agent, score = matched_agents[0]
            agent_type = agent.agent_type.value if hasattr(agent.agent_type, 'value') else str(agent.agent_type)
            assignments.append({
                "subtask_id": task.task_id,
                "agent_id": agent.agent_id,
                "agent_type": agent_type,
                "score": score,
                "role": "winner"
            })

        return assignments

    async def _create_hybrid_assignments(
        self, task: Task, agents: List[BaseAgent]
    ) -> List[Dict[str, Any]]:
        """混合模式：选择最匹配的Agent（兜底）"""
        assignments = []

        matched_agents = await self.matcher.match(task, agents)

        if matched_agents:
            agent, score = matched_agents[0]
            agent_type = agent.agent_type.value if hasattr(agent.agent_type, 'value') else str(agent.agent_type)
            assignments.append({
                "subtask_id": task.task_id,
                "agent_id": agent.agent_id,
                "agent_type": agent_type,
                "score": score
            })

        return assignments

    async def _build_execution_plan(
        self,
        assignments: List[Dict[str, Any]],
        task: Task,
    ) -> List[Dict[str, Any]]:
        """构建执行计划

        将分配注册到 ContextCenter，生成带状态信息的完整执行计划。

        Args:
            assignments: Agent分配列表
            task: 原始任务

        Returns:
            执行计划列表（带 status 字段）
        """
        plan = []

        for assignment in assignments:
            subtask_id = assignment["subtask_id"]
            agent_id = assignment["agent_id"]

            # 更新上下文中的分配
            await self.context_center.assign_subtask(task.task_id, subtask_id, agent_id)

            # 添加到执行计划
            plan.append({
                **assignment,
                "task_id": task.task_id,
                "status": "pending"
            })

        return plan
