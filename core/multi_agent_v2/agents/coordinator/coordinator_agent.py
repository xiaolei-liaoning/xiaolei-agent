"""
CoordinatorAgent - 协调Agent

协调多个Agent的工作流程
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from ..base.base_agent import (
    BaseAgent,
    AgentType,
    Capability,
    Task,
    ActionResult,
    Thought
)

logger = logging.getLogger(__name__)


@dataclass
class CoordinationStep:
    """协调步骤"""
    step_id: str
    agent_id: str
    task: Task
    status: str = "pending"
    result: Optional[ActionResult] = None


@dataclass
class CoordinationPlan:
    """协调计划"""
    plan_id: str
    steps: List[CoordinationStep]
    dependencies: Dict[str, List[str]] = field(default_factory=dict)


class CoordinatorAgent(BaseAgent):
    """CoordinatorAgent - 管理多Agent协作"""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        description: str = "协调Agent，管理多Agent协作"
    ):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.COORDINATOR,
            name=name,
            description=description
        )

        # 注册的Agent
        self.registered_agents: Dict[str, BaseAgent] = {}

        # 协调历史
        self.coordination_history: List[CoordinationPlan] = []

        # 定义CoordinatorAgent的能力
        self.capabilities = [
            Capability(
                name="workflow_coordination",
                description="工作流协调能力",
                keywords=["协调", "工作流", "调度", "编排"],
                expertise_level=0.9,
                max_concurrent_tasks=2,
                avg_execution_time=10.0,
                success_rate=0.92
            ),
            Capability(
                name="dependency_management",
                description="依赖管理能力",
                keywords=["依赖", "顺序", "流程", "前置"],
                expertise_level=0.85,
                max_concurrent_tasks=5,
                avg_execution_time=3.0,
                success_rate=0.95
            ),
            Capability(
                name="resource_allocation",
                description="资源分配能力",
                keywords=["分配", "资源", "负载", "均衡"],
                expertise_level=0.8,
                max_concurrent_tasks=3,
                avg_execution_time=4.0,
                success_rate=0.88
            )
        ]

        logger.info(f"CoordinatorAgent初始化完成: {self.agent_id}")

    async def execute(self, task: Task) -> ActionResult:
        """执行协调任务"""
        logger.info(f"CoordinatorAgent开始执行任务: {task.task_id}")

        try:
            # 1. 思考
            thought = await self.think(task)
            logger.info(f"思考完成: {thought.reasoning}")

            # 2. 协调
            result = await self._coordinate(task)

            # 3. 反思
            reflection = await self.reflect(
                ActionResult(
                    success=result.get("success", True),
                    output=result
                )
            )

            # ★ 激活：从反思学习优化协调策略
            self._learn_from_coordination(reflection, result)

            return ActionResult(
                success=result.get("success", True),
                output=result,
                execution_time=result.get("execution_time", 10.0)
            )

        except Exception as e:
            logger.error(f"CoordinatorAgent执行失败: {e}")
            return ActionResult(
                success=False,
                error=str(e)
            )

    async def _coordinate(self, task: Task) -> Dict[str, Any]:
        """协调多Agent执行任务"""
        logger.info(f"开始协调任务: {task.description}")

        # 1. 制定协调计划
        plan = await self._create_coordination_plan(task)
        if not plan:
            return {
                "success": False,
                "error": "无法创建协调计划",
                "status": "failed"
            }

        # 2. 执行协调计划
        results = await self._execute_coordination_plan(plan)

        # 3. 记录协调历史
        self.coordination_history.append(plan)

        return {
            "type": "coordination",
            "plan_id": plan.plan_id,
            "results": results,
            "status": "success"
        }

    async def _create_coordination_plan(self, task: Task) -> Optional[CoordinationPlan]:
        """创建协调计划"""
        from datetime import datetime
        import uuid

        plan_id = f"coord-{uuid.uuid4().hex[:8]}"

        # 简单的协调计划：如果有WorkerAgent就分配
        if not self.registered_agents:
            return None

        # 选择合适的Agent
        selected_agents = self._select_agents_for_task(task)

        steps = []
        for i, (agent_id, agent) in enumerate(selected_agents.items()):
            step = CoordinationStep(
                step_id=f"step-{i}",
                agent_id=agent_id,
                task=task
            )
            steps.append(step)

        return CoordinationPlan(
            plan_id=plan_id,
            steps=steps
        )

    async def _execute_coordination_plan(self, plan: CoordinationPlan) -> Dict[str, Any]:
        """执行协调计划"""
        results = {}

        for step in plan.steps:
            if step.agent_id in self.registered_agents:
                step.status = "running"
                try:
                    agent = self.registered_agents[step.agent_id]
                    result = await agent.execute(step.task)
                    step.result = result
                    step.status = "completed"
                    results[step.agent_id] = {
                        "success": result.success,
                        "output": result.output,
                        "execution_time": result.execution_time
                    }
                except Exception as e:
                    step.status = "failed"
                    results[step.agent_id] = {
                        "success": False,
                        "error": str(e)
                    }
            else:
                step.status = "failed"
                results[step.agent_id] = {
                    "success": False,
                    "error": "Agent not registered"
                }

        return results

    def register_agent(self, agent: BaseAgent) -> None:
        """注册Agent"""
        if agent.agent_id not in self.registered_agents:
            self.registered_agents[agent.agent_id] = agent
            logger.info(f"Agent已注册: {agent.agent_id} ({agent.agent_type.value})")
        else:
            logger.warning(f"Agent已存在: {agent.agent_id}")

    def unregister_agent(self, agent_id: str) -> None:
        """注销Agent"""
        if agent_id in self.registered_agents:
            del self.registered_agents[agent_id]
            logger.info(f"Agent已注销: {agent_id}")

    def _select_agents_for_task(self, task: Task) -> Dict[str, BaseAgent]:
        """选择适合任务的Agent"""
        selected = {}

        for agent_id, agent in self.registered_agents.items():
            # 简单策略：根据任务类型选择
            if agent.agent_type in [AgentType.WORKER, AgentType.EXPERT]:
                selected[agent_id] = agent

        return selected

    def _learn_from_coordination(self, reflection, result: Dict[str, Any]) -> None:
        """从协调结果学习"""
        # 记录成功的协调模式
        if hasattr(reflection, 'lessons_learned') and reflection.lessons_learned:
            logger.info(f"从协调中学习: {reflection.lessons_learned}")

    def get_coordination_statistics(self) -> Dict[str, Any]:
        """获取协调统计"""
        total_plans = len(self.coordination_history)
        total_agents = len(self.registered_agents)

        return {
            "total_plans": total_plans,
            "registered_agents": total_agents,
            "agent_types": [a.agent_type.value for a in self.registered_agents.values()]
        }
