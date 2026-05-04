"""
智能调度器 - 多Agent系统的核心大脑

职责：
1. 任务理解 - 解析任务类型、复杂度、依赖
2. 模式选择 - 确定协作模式（流水线/主从/评审/拍卖）
3. Agent匹配 - 根据能力匹配最合适的Agent
4. 流程编排 - 定义任务执行顺序和依赖关系
5. 动态调整 - 根据执行情况实时调整
6. 结果聚合 - 汇总各Agent结果
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import uuid

from core.multi_agent_v2.agents.base.base_agent import (
    BaseAgent, AgentType, Task, ActionResult, Capability
)
from core.multi_agent_v2.orchestration.context.global_context_center import (
    GlobalContextCenter, TaskState, EventType, Event
)

logger = logging.getLogger(__name__)


class CollaborationMode(Enum):
    """协作模式"""
    PIPELINE = "pipeline"              # 流水线：顺序执行
    MASTER_SLAVE = "master_slave"    # 主从：主Agent分解+聚合
    REVIEW = "review"               # 评审：多Agent并行+评审
    AUCTION = "auction"             # 拍卖：任务竞标
    HYBRID = "hybrid"               # 混合模式


@dataclass
class ScheduleResult:
    """调度结果"""
    task_id: str
    success: bool
    collaboration_mode: CollaborationMode
    assigned_agents: Dict[str, str]  # subtask_id -> agent_id
    execution_plan: List[Dict[str, Any]]
    estimated_time: float
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SchedulingMetrics:
    """调度指标"""
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    avg_scheduling_time: float = 0.0
    total_scheduling_time: float = 0.0
    agent_utilization: Dict[str, float] = field(default_factory=dict)  # agent_id -> utilization

    @property
    def success_rate(self) -> float:
        return self.successful_tasks / self.total_tasks if self.total_tasks > 0 else 0.0


class CapabilityMatcher:
    """能力匹配器 - 智能匹配Agent与任务"""

    def __init__(self, context_center: GlobalContextCenter):
        self.context_center = context_center

    async def match(self, task: Task, available_agents: List[BaseAgent]) -> List[Tuple[BaseAgent, float]]:
        """匹配最适合执行任务的Agent列表

        匹配算法考虑：
        1. 能力相关性（关键词匹配）
        2. 专业等级（任务难度 vs Agent能力）
        3. 当前负载（避免过载）
        4. 历史表现（成功率、执行时间）
        5. 协作偏好（是否适合团队协作）
        6. 可用性（是否在线、健康）
        """
        scored_agents = []

        for agent in available_agents:
            # 检查Agent是否可用
            if not self._is_agent_available(agent):
                continue

            # 计算匹配分数
            score = self._calculate_match_score(task, agent)
            scored_agents.append((agent, score))

        # 按分数排序
        scored_agents.sort(key=lambda x: x[1], reverse=True)

        return scored_agents

    def _is_agent_available(self, agent: BaseAgent) -> bool:
        """检查Agent是否可用"""
        # 检查状态
        if agent.state.value not in ["idle", "ready"]:
            return False

        # 检查负载
        if agent.current_load >= agent.max_load:
            return False

        # 检查健康状态
        if agent.health_score < 0.5:
            return False

        return True

    def _calculate_match_score(self, task: Task, agent: BaseAgent) -> float:
        """计算匹配分数"""
        scores = []

        # 1. 能力匹配分数 (权重: 40%)
        capability_score = self._calculate_capability_score(task, agent)
        scores.append(("capability", capability_score, 0.4))

        # 2. 负载分数 (权重: 20%)
        load_score = self._calculate_load_score(agent)
        scores.append(("load", load_score, 0.2))

        # 3. 历史表现分数 (权重: 25%)
        performance_score = self._calculate_performance_score(agent)
        scores.append(("performance", performance_score, 0.25))

        # 4. 协作兼容性分数 (权重: 15%)
        collaboration_score = self._calculate_collaboration_score(agent)
        scores.append(("collaboration", collaboration_score, 0.15))

        # 加权求和
        total_score = sum(score * weight for _, score, weight in scores)

        return total_score

    def _calculate_capability_score(self, task: Task, agent: BaseAgent) -> float:
        """计算能力匹配分数"""
        if not agent.capabilities:
            return 0.0

        max_score = 0.0

        for capability in agent.capabilities:
            # 关键词匹配
            keyword_matches = sum(1 for kw in task.keywords if kw in capability.keywords)

            # 专业等级
            level_score = capability.expertise_level

            # 综合分数
            score = (keyword_matches / max(len(task.keywords), 1)) * 0.5 + level_score * 0.5
            max_score = max(max_score, score)

        return max_score

    def _calculate_load_score(self, agent: BaseAgent) -> float:
        """计算负载分数"""
        if agent.max_load == 0:
            return 0.0

        # 负载越低，分数越高
        load_ratio = agent.current_load / agent.max_load
        return 1.0 - load_ratio

    def _calculate_performance_score(self, agent: BaseAgent) -> float:
        """计算历史表现分数"""
        metrics = agent.get_metrics()

        # 成功率分数
        success_score = metrics.success_rate

        # 执行时间分数（越快越好）
        if metrics.avg_execution_time > 0:
            # 假设10秒是标准时间
            time_score = max(0, 1.0 - (metrics.avg_execution_time / 10.0))
        else:
            time_score = 1.0

        return success_score * 0.6 + time_score * 0.4

    def _calculate_collaboration_score(self, agent: BaseAgent) -> float:
        """计算协作兼容性分数"""
        # 简单实现：Master类型更擅长协作
        if agent.agent_type == AgentType.MASTER:
            return 0.9
        elif agent.agent_type == AgentType.COORDINATOR:
            return 0.8
        elif agent.agent_type == AgentType.WORKER:
            return 0.6
        else:
            return 0.5


class IntelligentScheduler:
    """智能调度器 - 多Agent系统的核心大脑"""

    def __init__(self, context_center: GlobalContextCenter):
        # 核心组件
        self.context_center = context_center
        self.matcher = CapabilityMatcher(context_center)

        # 调度策略
        self.strategies: Dict[CollaborationMode, Any] = {}

        # 熔断器
        self.circuit_breakers: Dict[str, 'CircuitBreaker'] = {}

        # 指标
        self.metrics = SchedulingMetrics()

        # Agent池引用
        self.agent_pool: Optional['AgentPool'] = None

        logger.info("智能调度器初始化完成")

    def set_agent_pool(self, agent_pool: 'AgentPool') -> None:
        """设置Agent池引用"""
        self.agent_pool = agent_pool

    async def schedule(self, task: Task) -> ScheduleResult:
        """调度任务 - 核心方法

        调度流程：
        1. 任务理解 - 解析任务类型、复杂度、依赖
        2. 模式选择 - 确定协作模式
        3. Agent匹配 - 根据能力匹配
        4. 流程编排 - 定义执行顺序
        5. 动态调整 - 实时调整分配
        6. 结果聚合 - 汇总结果
        """
        start_time = time.time()
        trace_id = self.context_center.generate_trace_id()

        logger.info(f"开始调度任务: {task.task_id} (trace: {trace_id})")

        try:
            # 1. 任务理解
            task_analysis = await self._analyze_task(task)

            # 2. 模式选择
            collaboration_mode = await self._select_collaboration_mode(task, task_analysis)

            # 3. 获取可用Agent
            available_agents = await self._get_available_agents()

            if not available_agents:
                raise RuntimeError("没有可用的Agent")

            # 4. Agent匹配
            agent_assignments = await self._match_and_assign(task, available_agents, collaboration_mode)

            # 5. 创建执行计划
            execution_plan = await self._create_execution_plan(
                task, agent_assignments, collaboration_mode
            )

            # 6. 更新任务状态
            await self.context_center.update_task_state(
                task.task_id,
                TaskState.SCHEDULED,
                {"trace_id": trace_id, "collaboration_mode": collaboration_mode.value}
            )

            # 计算预估时间
            estimated_time = sum(a.get("estimated_time", 10) for a in execution_plan)

            # 更新指标
            scheduling_time = time.time() - start_time
            self.metrics.total_tasks += 1
            self.metrics.total_scheduling_time += scheduling_time
            self.metrics.avg_scheduling_time = (
                self.metrics.total_scheduling_time / self.metrics.total_tasks
            )

            result = ScheduleResult(
                task_id=task.task_id,
                success=True,
                collaboration_mode=collaboration_mode,
                assigned_agents={a["subtask_id"]: a["agent_id"] for a in execution_plan},
                execution_plan=execution_plan,
                estimated_time=estimated_time,
                metadata={"trace_id": trace_id, "scheduling_time": scheduling_time}
            )

            logger.info(f"任务调度成功: {task.task_id}, 模式: {collaboration_mode.value}, 预估时间: {estimated_time}s")

            return result

        except Exception as e:
            logger.error(f"任务调度失败: {task.task_id}, 错误: {e}")

            self.metrics.failed_tasks += 1

            return ScheduleResult(
                task_id=task.task_id,
                success=False,
                collaboration_mode=CollaborationMode.HYBRID,
                assigned_agents={},
                execution_plan=[],
                estimated_time=0.0,
                error=str(e)
            )

    async def _analyze_task(self, task: Task) -> Dict[str, Any]:
        """分析任务"""
        analysis = {
            "complexity": task.complexity,
            "has_dependencies": len(task.dependencies) > 0,
            "estimated_steps": task.estimated_steps,
            "requires_review": task.complexity > 0.7,
            "is_parallelizable": len(task.dependencies) == 0 and task.estimated_steps > 1,
            "keywords": task.keywords
        }

        return analysis

    async def _select_collaboration_mode(self, task: Task, analysis: Dict[str, Any]) -> CollaborationMode:
        """选择协作模式"""

        # 简单启发式选择
        if analysis["complexity"] > 0.8 and analysis["requires_review"]:
            # 复杂任务 + 需要评审 -> 评审模式
            return CollaborationMode.REVIEW

        elif analysis["is_parallelizable"] and analysis["estimated_steps"] > 2:
            # 可并行 + 多步骤 -> 流水线模式
            return CollaborationMode.PIPELINE

        elif analysis["complexity"] > 0.5:
            # 中等复杂度 -> 主从模式
            return CollaborationMode.MASTER_SLAVE

        elif len(task.keywords) > 3:
            # 多技能需求 -> 拍卖模式
            return CollaborationMode.AUCTION

        else:
            # 简单任务 -> 混合模式
            return CollaborationMode.HYBRID

    async def _get_available_agents(self) -> List[BaseAgent]:
        """获取可用Agent"""
        if not self.agent_pool:
            return []

        agents = await self.agent_pool.get_available_agents()
        return agents

    async def _match_and_assign(
        self,
        task: Task,
        agents: List[BaseAgent],
        mode: CollaborationMode
    ) -> List[Dict[str, Any]]:
        """匹配并分配Agent"""
        assignments = []

        if mode == CollaborationMode.PIPELINE:
            # 流水线模式：为每个步骤分配专门的Agent
            for step in range(task.estimated_steps):
                subtask_id = f"{task.task_id}_step_{step}"
                step_keywords = task.keywords  # 简化处理

                step_task = Task(
                    task_id=subtask_id,
                    type=f"{task.type}_step_{step}",
                    description=f"步骤 {step}: {task.description}",
                    keywords=step_keywords,
                    complexity=task.complexity / task.estimated_steps,
                    estimated_steps=1
                )

                matched_agents = await self.matcher.match(step_task, agents)

                if matched_agents:
                    agent, score = matched_agents[0]
                    assignments.append({
                        "subtask_id": subtask_id,
                        "agent_id": agent.agent_id,
                        "agent_type": agent.agent_type.value,
                        "score": score,
                        "step": step
                    })

        elif mode == CollaborationMode.MASTER_SLAVE:
            # 主从模式：分配一个Master和多个Worker
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
                        assignments.append({
                            "subtask_id": subtask_id,
                            "agent_id": slave.agent_id,
                            "agent_type": "worker",
                            "role": "slave",
                            "step": i
                        })

        elif mode == CollaborationMode.REVIEW:
            # 评审模式：分配多个Worker和Reviewer
            workers = [a for a in agents if a.agent_type == AgentType.WORKER][:3]
            reviewers = [a for a in agents if a.agent_type == AgentType.REVIEWER]

            # 分配Worker
            for i, worker in enumerate(workers):
                assignments.append({
                    "subtask_id": f"{task.task_id}_work_{i}",
                    "agent_id": worker.agent_id,
                    "agent_type": "worker",
                    "role": "worker"
                })

            # 分配Reviewer
            if reviewers:
                assignments.append({
                    "subtask_id": f"{task.task_id}_review",
                    "agent_id": reviewers[0].agent_id,
                    "agent_type": "reviewer",
                    "role": "reviewer"
                })

        elif mode == CollaborationMode.AUCTION:
            # 拍卖模式：发布任务，让Agent竞标
            # 这里简化处理，直接选择最匹配的Agent
            matched_agents = await self.matcher.match(task, agents)

            if matched_agents:
                agent, score = matched_agents[0]
                assignments.append({
                    "subtask_id": task.task_id,
                    "agent_id": agent.agent_id,
                    "agent_type": agent.agent_type.value,
                    "score": score,
                    "role": "winner"
                })

        else:
            # 混合模式：简单分配
            matched_agents = await self.matcher.match(task, agents)

            if matched_agents:
                agent, score = matched_agents[0]
                assignments.append({
                    "subtask_id": task.task_id,
                    "agent_id": agent.agent_id,
                    "agent_type": agent.agent_type.value,
                    "score": score
                })

        return assignments

    async def _create_execution_plan(
        self,
        task: Task,
        assignments: List[Dict[str, Any]],
        mode: CollaborationMode
    ) -> List[Dict[str, Any]]:
        """创建执行计划"""
        plan = []

        for assignment in assignments:
            subtask_id = assignment["subtask_id"]
            agent_id = assignment["agent_id"]

            # 更新上下文中的分配
            await self.context_center.assign_subtask(task.task_id, subtask_id, agent_id)

            # 注册到Agent
            if self.agent_pool:
                await self.agent_pool.assign_task(agent_id, subtask_id)

            # 添加到执行计划
            plan.append({
                **assignment,
                "task_id": task.task_id,
                "status": "pending"
            })

        return plan

    async def handle_failure(self, agent_id: str, task_id: str, error: Exception) -> None:
        """处理Agent执行失败"""
        logger.error(f"Agent {agent_id} 执行任务 {task_id} 失败: {error}")

        # 获取Agent的熔断器
        breaker = self.circuit_breakers.get(agent_id)

        if breaker:
            await breaker.record_failure()

            if breaker.is_open:
                # 熔断器打开，尝试重路由
                logger.warning(f"Agent {agent_id} 熔断器打开，尝试重路由")

                # 找到替代Agent
                if self.agent_pool:
                    alternative = await self.agent_pool.find_alternative_agent(agent_id)

                    if alternative:
                        # 重新分配任务
                        await self.context_center.assign_subtask(task_id, f"{task_id}_retry", alternative.agent_id)
                        logger.info(f"任务 {task_id} 已重新分配给替代Agent {alternative.agent_id}")

        # 更新任务状态
        await self.context_center.update_task_state(task_id, TaskState.FAILED, {"error": str(error)})

        # 更新指标
        self.metrics.failed_tasks += 1

    async def rebalance(self) -> None:
        """负载再平衡"""
        if not self.agent_pool:
            return

        # 获取所有Agent的负载
        agents = await self.agent_pool.get_all_agents()

        for agent in agents:
            if agent.current_load > agent.max_load * 0.9:
                # 负载过高，尝试转移任务
                logger.info(f"Agent {agent.agent_id} 负载过高，尝试重新分配任务")

                # 找到负载较低的Agent
                low_load_agent = await self.agent_pool.find_low_load_agent()

                if low_load_agent:
                    # 转移任务（简化处理）
                    logger.info(f"将任务从 {agent.agent_id} 转移到 {low_load_agent.agent_id}")

    def get_metrics(self) -> SchedulingMetrics:
        """获取调度指标"""
        return self.metrics


class CircuitBreaker:
    """熔断器 - 防止故障扩散"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.half_open_calls = 0

    @property
    def is_open(self) -> bool:
        """熔断器是否打开"""
        if self.state == "OPEN":
            # 检查是否超过恢复超时
            if self.last_failure_time:
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    self.half_open_calls = 0
                    return False
            return True
        return False

    async def record_failure(self) -> None:
        """记录失败"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"熔断器打开，失败次数: {self.failure_count}")

    async def record_success(self) -> None:
        """记录成功"""
        if self.state == "HALF_OPEN":
            self.half_open_calls += 1

            if self.half_open_calls >= self.half_open_max_calls:
                self.state = "CLOSED"
                self.failure_count = 0
                logger.info("熔断器关闭，系统恢复")

    async def can_execute(self) -> bool:
        """是否可以执行"""
        if self.state == "CLOSED":
            return True

        if self.state == "HALF_OPEN":
            return self.half_open_calls < self.half_open_max_calls

        return False  # OPEN状态不允许执行
