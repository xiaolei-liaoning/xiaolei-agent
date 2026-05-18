"""
智能调度器 - 多Agent系统的核心大脑

职责：
1. 任务理解 - 解析任务类型、复杂度、依赖
2. 模式选择 - 确定协作模式（流水线/主从/评审/拍卖）
3. Agent匹配 - 根据能力匹配最合适的Agent（含资源评估）
4. 流程编排 - 定义任务执行顺序和依赖关系
5. 动态调整 - 根据执行情况实时调整
6. 结果聚合 - 汇总各Agent结果

整合了 enhanced_agent_router 的资源评估功能：
- 任务复杂度评估
- 资源需求评估（CPU、内存、网络、存储、API配额）
- 增强型多维路由评分
- 动态权重调整
- 负载均衡
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid
import re

from core.shared.enums import TaskComplexity, ResourceType
from core.multi_agent_v2.agents.base.base_agent import (
    BaseAgent, AgentType, Task, ActionResult, Capability
)
from core.multi_agent_v2.orchestration.context.global_context_center import (
    GlobalContextCenter, TaskState, EventType, Event
)
from core.multi_agent_v2.orchestration.collaboration.strategies import (
    LLMReflection, ReflectionTrigger, ReflectionTriggerConfig,
    AdaptivePipelineWithReflection, StepResult, ReflectionPrompt,
    ReflectionDecision, ReflectionResult
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


@dataclass
class EnhancedAgentMetrics:
    """增强版Agent性能指标（整合自enhanced_agent_router）"""
    agent_type: str
    priority: float = 1.0              # 优先级权重 (0-1)
    health_score: float = 1.0          # 健康度 (0-1)
    avg_execution_time: float = 0.0    # 平均执行时间（秒）
    success_rate: float = 1.0          # 成功率 (0-1)
    total_tasks: int = 0               # 总任务数
    failed_tasks: int = 0              # 失败任务数
    last_active: float = 0.0           # 最后活跃时间戳
    
    # 资源相关指标
    avg_cpu_usage: float = 0.0         # 平均CPU使用率
    avg_memory_usage: float = 0.0       # 平均内存使用率
    avg_network_usage: float = 0.0       # 平均网络使用率
    concurrent_capacity: int = 1         # 并发处理能力
    
    # 复杂度相关指标
    simple_task_success_rate: float = 1.0   # 简单任务成功率
    moderate_task_success_rate: float = 1.0  # 中等任务成功率
    complex_task_success_rate: float = 1.0   # 复杂任务成功率


@dataclass
class ResourceAvailability:
    """资源可用性"""
    resource_type: ResourceType
    available: float  # 可用量
    total: float  # 总量
    utilization_rate: float  # 利用率
    last_updated: float = field(default_factory=time.time)


class CapabilityMatcher:
    """能力匹配器 - 智能匹配Agent与任务
    
    整合了 enhanced_agent_router 的资源评估功能：
    - 任务复杂度评估
    - 资源需求评估
    - 增强型多维路由评分
    - 学习能力：参考历史复盘结果
    """

    def __init__(self, context_center: GlobalContextCenter):
        self.context_center = context_center
        
        # 路由权重配置
        self.routing_weights = {
            "priority": 0.20,
            "health": 0.15,
            "time": 0.15,
            "success": 0.20,
            "complexity_match": 0.10,
            "resource_efficiency": 0.10,
            "learning_bonus": 0.10  # 新增：学习奖励权重
        }
        
        # 资源可用性缓存
        self.resource_availability: Dict[ResourceType, ResourceAvailability] = {}
        
        # 学习缓存：记录哪些Agent在哪些任务类型上表现好
        self.learning_cache: Dict[str, Dict[str, float]] = {}  # task_type -> {agent_id -> success_rate}

    def update_resource_availability(self, resource_type: ResourceType, 
                                  available: float, total: float):
        """更新资源可用性"""
        utilization_rate = 1.0 - (available / total) if total > 0 else 0.0
        
        self.resource_availability[resource_type] = ResourceAvailability(
            resource_type=resource_type,
            available=available,
            total=total,
            utilization_rate=utilization_rate
        )

    def assess_task_complexity(self, task: Task) -> TaskComplexity:
        """评估任务复杂度（整合自enhanced_agent_router）"""
        task_type = task.type or ""
        task_description = task.description or ""
        
        # 任务复杂度规则库
        complexity_rules = {
            "trivial": ["ping", "check", "status"],
            "simple": ["search", "query", "lookup"],
            "moderate": ["summarize", "analyze", "process"],
            "complex": ["crawl", "extract", "generate", "optimize"],
            "critical": ["emergency", "urgent", "priority"]
        }
        
        # 匹配任务类型
        for complexity_name, keywords in complexity_rules.items():
            for keyword in keywords:
                if keyword in task_type.lower() or keyword in task_description.lower():
                    return TaskComplexity(complexity_name)
        
        # 根据任务特征调整
        if task.estimated_steps and task.estimated_steps > 5:
            return TaskComplexity.COMPLEX
        elif task.estimated_steps and task.estimated_steps > 2:
            return TaskComplexity.MODERATE
        
        # 默认为中等复杂度
        return TaskComplexity.MODERATE

    async def match(self, task: Task, available_agents: List[BaseAgent]) -> List[Tuple[BaseAgent, float]]:
        """匹配最适合执行任务的Agent列表

        匹配算法考虑（整合了资源评估）：
        1. 能力相关性（关键词匹配）
        2. 专业等级（任务难度 vs Agent能力）
        3. 当前负载（避免过载）
        4. 历史表现（成功率、执行时间）
        5. 协作偏好（是否适合团队协作）
        6. 可用性（是否在线、健康）
        7. 资源效率（CPU、内存、网络使用率）
        8. 复杂度匹配（任务复杂度 vs Agent专长）
        """
        scored_agents = []
        
        # 评估任务复杂度
        task_complexity = self.assess_task_complexity(task)

        for agent in available_agents:
            # 检查Agent是否可用
            if not self._is_agent_available(agent):
                continue

            # 计算增强版匹配分数
            score = self._calculate_enhanced_match_score(task, agent, task_complexity)
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

    def _calculate_enhanced_match_score(self, task: Task, agent: BaseAgent, 
                                       task_complexity: TaskComplexity) -> float:
        """计算增强版匹配分数（整合自enhanced_agent_router）
        
        综合考虑：
        - 优先级权重
        - 健康度
        - 执行时间
        - 成功率
        - 复杂度匹配
        - 资源效率
        - 学习奖励（历史复盘结果）
        """
        metrics = agent.get_metrics()
        
        # 1. 基础评分（原有维度）
        max_acceptable_time = 60.0
        if metrics.avg_execution_time > 0:
            time_score = max(0, 1.0 - (metrics.avg_execution_time / max_acceptable_time))
        else:
            time_score = 1.0
        
        base_score = (
            metrics.priority * self.routing_weights["priority"] +
            agent.health_score * self.routing_weights["health"] +
            time_score * self.routing_weights["time"] +
            metrics.success_rate * self.routing_weights["success"]
        )
        
        # 2. 复杂度匹配评分
        complexity_match_score = self._calculate_complexity_match(agent, task_complexity)
        
        # 3. 资源效率评分
        resource_efficiency_score = self._calculate_resource_efficiency(agent)
        
        # 4. 学习奖励评分（新增）
        learning_bonus = self._calculate_learning_bonus(task, agent)
        
        # 5. 综合评分
        total_score = (
            base_score +
            complexity_match_score * self.routing_weights["complexity_match"] +
            resource_efficiency_score * self.routing_weights["resource_efficiency"] +
            learning_bonus * self.routing_weights["learning_bonus"]
        )
        
        return round(total_score, 4)
    
    def _calculate_learning_bonus(self, task: Task, agent: BaseAgent) -> float:
        """计算学习奖励分数
        
        根据历史复盘结果，对在相似任务上表现好的Agent给予奖励
        """
        # 获取任务类型作为学习缓存的key
        task_type = task.type or "general"
        
        # 查看学习缓存中该Agent在该任务类型上的成功率
        task_cache = self.learning_cache.get(task_type, {})
        success_rate = task_cache.get(agent.agent_id, 0.0)
        
        # 如果没有历史记录，返回基础分数
        if success_rate == 0.0:
            # 尝试从复盘结果中学习
            self._learn_from_reviews(task_type)
            task_cache = self.learning_cache.get(task_type, {})
            success_rate = task_cache.get(agent.agent_id, 0.5)  # 默认0.5
        
        return success_rate
    
    def _learn_from_reviews(self, task_type: str) -> None:
        """从复盘结果中学习，更新学习缓存"""
        try:
            from core.auto_reviewer import get_auto_reviewer
            
            reviewer = get_auto_reviewer()
            reviews = reviewer.get_worth_saving_reviews()
            
            for review in reviews:
                # 简单匹配：任务描述包含任务类型关键词
                if task_type.lower() in review.task_description.lower():
                    # 假设复盘结果中包含agent_id信息
                    # 这里简化处理，实际应该从执行日志中提取
                    if hasattr(review, 'agent_id') and review.agent_id:
                        agent_id = review.agent_id
                        if review.is_worth_saving:
                            # 记录成功经验
                            if task_type not in self.learning_cache:
                                self.learning_cache[task_type] = {}
                            if agent_id not in self.learning_cache[task_type]:
                                self.learning_cache[task_type][agent_id] = 0.0
                            # 提高成功率
                            self.learning_cache[task_type][agent_id] = min(
                                1.0,
                                self.learning_cache[task_type][agent_id] + 0.1
                            )
        except Exception as e:
            logger.debug(f"从复盘结果学习失败: {e}")
    
    def update_learning_cache(self, task_type: str, agent_id: str, success: bool) -> None:
        """更新学习缓存
        
        Args:
            task_type: 任务类型
            agent_id: Agent ID
            success: 是否成功
        """
        if task_type not in self.learning_cache:
            self.learning_cache[task_type] = {}
        
        if agent_id not in self.learning_cache[task_type]:
            self.learning_cache[task_type][agent_id] = 0.5  # 初始值
        
        if success:
            # 成功则提高评分
            self.learning_cache[task_type][agent_id] = min(
                1.0,
                self.learning_cache[task_type][agent_id] + 0.05
            )
        else:
            # 失败则降低评分
            self.learning_cache[task_type][agent_id] = max(
                0.0,
                self.learning_cache[task_type][agent_id] - 0.1
            )
        
        logger.debug(f"学习缓存更新: task_type={task_type}, agent_id={agent_id}, success={success}, score={self.learning_cache[task_type][agent_id]:.2f}")

    def _calculate_complexity_match(self, agent: BaseAgent, task_complexity: TaskComplexity) -> float:
        """计算复杂度匹配分数"""
        metrics = agent.get_metrics()
        
        # 根据任务复杂度选择对应的历史成功率
        if task_complexity in [TaskComplexity.TRIVIAL, TaskComplexity.SIMPLE]:
            return metrics.simple_task_success_rate if hasattr(metrics, 'simple_task_success_rate') else metrics.success_rate
        elif task_complexity == TaskComplexity.MODERATE:
            return metrics.moderate_task_success_rate if hasattr(metrics, 'moderate_task_success_rate') else metrics.success_rate
        elif task_complexity in [TaskComplexity.COMPLEX, TaskComplexity.VERY_COMPLEX, TaskComplexity.CRITICAL]:
            return metrics.complex_task_success_rate if hasattr(metrics, 'complex_task_success_rate') else metrics.success_rate
        
        return metrics.success_rate

    def _calculate_resource_efficiency(self, agent: BaseAgent) -> float:
        """计算资源效率分数"""
        metrics = agent.get_metrics()
        
        # 综合考虑CPU、内存、网络使用率
        # 使用率越低，效率越高
        avg_usage = 0.0
        count = 0
        
        if hasattr(metrics, 'avg_cpu_usage') and metrics.avg_cpu_usage is not None:
            avg_usage += metrics.avg_cpu_usage
            count += 1
        if hasattr(metrics, 'avg_memory_usage') and metrics.avg_memory_usage is not None:
            avg_usage += metrics.avg_memory_usage
            count += 1
        if hasattr(metrics, 'avg_network_usage') and metrics.avg_network_usage is not None:
            avg_usage += metrics.avg_network_usage
            count += 1
        
        if count > 0:
            avg_usage /= count
            # 效率分数：使用率越低，分数越高
            efficiency = max(0, 1.0 - avg_usage)
            return efficiency
        
        # 默认返回较高效率分数
        return 0.85


class IntelligentScheduler:
    """智能调度器 - 多Agent系统的核心大脑"""

    def __init__(self, context_center: GlobalContextCenter, llm_facade: Optional[Any] = None):
        # 核心组件
        self.context_center = context_center
        self.matcher = CapabilityMatcher(context_center)

        # 调度策略
        self.strategies: Dict[CollaborationMode, Any] = {}
        
        # ★ 新增：协作模式历史成功率记录（跨次学习）
        self.collaboration_history: Dict[str, Dict[str, float]] = {}  # task_type -> {mode -> success_rate}

        # 熔断器
        self.circuit_breakers: Dict[str, 'CircuitBreaker'] = {}

        # 指标
        self.metrics = SchedulingMetrics()

        # Agent池引用
        self.agent_pool: Optional['AgentPool'] = None

        # LLM反思机制
        self.llm_facade = llm_facade
        self.reflection_engine = LLMReflection(llm_facade)
        self.reflection_trigger = ReflectionTrigger()
        self.adaptive_pipeline = AdaptivePipelineWithReflection(llm_facade)

        # ★ KEPA闭环：懒加载反思结果订阅（避免在无 event loop 环境下崩溃）
        self._reflection_task = None

        logger.info("智能调度器初始化完成（KEPA闭环已激活）")

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
            # 4. Agent匹配
            agent_assignments = await self._match_and_assign(task, available_agents, collaboration_mode)
            logger.info(f"[DEBUG] agent_assignments: {len(agent_assignments)} assignments")
            if agent_assignments:
                logger.info(f"[DEBUG]   First assignment: {agent_assignments[0]}")

            # 4.5 创建任务上下文（必须在_create_execution_plan之前）
            await self.context_center.create_task_context(
                request=f"Task: {task.description}",
                trace_id=trace_id,
                task_id=task.task_id
            )

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

            # 发布到 SharedBus
            try:
                from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus, TaskSnapshot, Message, MessageType
                bus = get_shared_bus()
                snapshot = TaskSnapshot(
                    task_id=task.task_id,
                    original_request=task.description,
                    status="scheduled",
                    collaboration_mode=collaboration_mode.value,
                    assigned_agents=result.assigned_agents,
                )
                await bus.save_snapshot(snapshot)
                
                # 订阅 TASK_FAILED 消息，用于失败处理
                async def on_task_failed(message: Message):
                    """处理任务失败消息"""
                    if message.type == MessageType.TASK_FAILED:
                        agent_id = message.payload.get("agent_id", "unknown")
                        error = message.payload.get("error", "未知错误")
                        logger.warning(f"Agent {agent_id} 执行失败: {error}")
                        # 更新快照状态
                        snap = await bus.get_snapshot(task.task_id)
                        if snap:
                            snap.status = "failed"
                            await bus.save_snapshot(snap)
                        # 触发失败处理
                        await self.handle_failure(agent_id, task.task_id, Exception(error))
                
                await bus.subscribe(f"task:{task.task_id}", on_task_failed)
                logger.debug(f"Scheduler 已订阅任务 {task.task_id} 的失败消息")
                
            except Exception as e:
                logger.warning(f"发布到SharedBus失败: {e}")

            # 调度完成，不再执行 — Agent 通过 SharedBus 自治执行
            # 旧的 execute_scheduled_task 保留为备用
            await self.context_center.update_task_state(
                task.task_id,
                TaskState.SCHEDULED,
                {"execution_plan": execution_plan, "estimated_time": estimated_time}
            )

            # ★ 消费 SchedulingMetrics：将调度指标发布到 SharedBus
            await self._publish_scheduling_metrics(task.task_id, collaboration_mode, result)

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

    async def execute_scheduled_task(self, task: Task, execution_plan: List[Dict[str, Any]]) -> dict:
        """执行调度好的任务"""
        logger.info(f"开始执行任务: {task.task_id}")
        
        all_results = []
        final_output = ""
        
        for step in execution_plan:
            subtask_id = step["subtask_id"]
            agent_id = step["agent_id"]
            agent_type = step.get("agent_type", "worker")
            
            # 从agent_pool获取agent
            if self.agent_pool:
                agent = None
                
                # 先从active_agents查找
                if agent_id in self.agent_pool.active_agents:
                    agent = self.agent_pool.active_agents[agent_id]
                else:
                    # 从pool中查找
                    for pool_type, agents in self.agent_pool.pools.items():
                        for ag in agents:
                            if ag.agent_id == agent_id:
                                agent = ag
                                break
                        if agent:
                            break
                
                if agent and hasattr(agent, 'execute'):
                    # 创建子任务 - 使用原始任务描述以便正确识别搜索意图
                    subtask_description = step.get('description', '')
                    if not subtask_description:
                        subtask_description = task.description
                    
                    subtask = Task(
                        task_id=subtask_id,
                        type=task.type,
                        description=subtask_description,
                        context=task.context,
                        priority=task.priority,
                        keywords=task.keywords
                    )
                    
                    # 执行子任务
                    try:
                        result = await agent.execute(subtask)
                        all_results.append({
                            "subtask_id": subtask_id,
                            "agent_id": agent_id,
                            "success": result.success,
                            "output": result.output,
                            "execution_time": result.execution_time
                        })
                        # 累积输出
                        if result.output:
                            final_output += str(result.output) + "\n\n"
                        logger.info(f"子任务执行完成: {subtask_id}, 结果: {result.success}")
                    except Exception as e:
                        logger.error(f"子任务执行失败: {subtask_id}, 错误: {e}")
                        all_results.append({
                            "subtask_id": subtask_id,
                            "agent_id": agent_id,
                            "success": False,
                            "error": str(e)
                        })
        
        # 保存结果到文件
        file_path = None
        if final_output.strip():
            import os
            from pathlib import Path
            
            output_dir = Path("skills") / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            file_name = f"multi_agent_result_{task.task_id}.txt"
            file_path = str(output_dir / file_name)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"任务ID: {task.task_id}\n")
                f.write(f"任务描述: {task.description}\n")
                f.write(f"执行时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("="*50 + "\n")
                f.write("执行结果:\n")
                f.write("="*50 + "\n")
                f.write(final_output)
            
            logger.info(f"任务结果已保存到: {file_path}")
        
        logger.info(f"任务执行完成: {task.task_id}, 子任务数: {len(all_results)}")
        
        # ★ 激活跨次学习：更新学习缓存
        task_type = task.type or "general"
        successful_count = 0
        for result in all_results:
            agent_id = result["agent_id"]
            success = result["success"]
            if success:
                successful_count += 1
            # 更新每个Agent的学习记录
            self.matcher.update_learning_cache(task_type, agent_id, success)
        
        # ★ 激活跨次学习：更新协作模式成功率
        total_subtasks = len(all_results)
        success_rate = successful_count / total_subtasks if total_subtasks > 0 else 0.0
        
        # 从执行计划中获取使用的协作模式
        used_mode = None
        try:
            # 尝试从ContextCenter获取或从其他地方推断
            used_mode = CollaborationMode.HYBRID  # 默认
        except:
            pass
        
        # 更新协作模式历史
        if task_type not in self.collaboration_history:
            self.collaboration_history[task_type] = {}
        
        # 更新该模式的成功率（简单平滑：70%历史 + 30%当前）
        mode_key = used_mode.value
        if mode_key in self.collaboration_history[task_type]:
            old_rate = self.collaboration_history[task_type][mode_key]
            new_rate = old_rate * 0.7 + success_rate * 0.3
            self.collaboration_history[task_type][mode_key] = new_rate
        else:
            self.collaboration_history[task_type][mode_key] = success_rate
        
        logger.info(f"[跨次学习] 协作模式 {mode_key} 成功率更新: {success_rate:.2%}")
        
        # 更新调度指标
        if successful_count == len(all_results):
            self.metrics.successful_tasks += 1
        else:
            self.metrics.failed_tasks += 1
        
        logger.info(f"[跨次学习] 任务 {task.task_id} 学习记录已更新: 成功={successful_count}/{len(all_results)}")
        
        return {
            "results": all_results,
            "final_output": final_output.strip(),
            "file_path": file_path
        }

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
        """选择协作模式 — 优先考虑历史经验，其次 LLM，最后硬编码规则"""
        task_type = task.type or "general"
        
        # ★ 1. 先尝试从历史经验中选择（跨次学习）
        if task_type in self.collaboration_history:
            mode_stats = self.collaboration_history[task_type]
            if mode_stats:
                # 选择成功率最高的模式
                best_mode = max(mode_stats.items(), key=lambda x: x[1])
                if best_mode[1] > 0.7:  # 只有历史成功率超过70%才考虑
                    try:
                        mode = CollaborationMode(best_mode[0])
                        logger.info(f"[跨次学习] 选择历史最优模式: {mode.value}, 成功率: {best_mode[1]:.2%}")
                        return mode
                    except Exception:
                        pass
        
        # 2. 尝试 LLM 选择
        try:
            from core.multi_agent_v2.orchestration.collaboration.strategies import select_strategy_with_llm

            available_agents = await self._get_available_agents()
            mode_str, params = await select_strategy_with_llm(
                task_description=task.description,
                task_keywords=task.keywords,
                estimated_steps=analysis.get("estimated_steps", 3),
                complexity=analysis.get("complexity", 0.5),
                available_agents=available_agents,
                llm_router=self.llm_facade,
            )
            mode_map = {
                "pipeline": CollaborationMode.PIPELINE,
                "master_slave": CollaborationMode.MASTER_SLAVE,
                "review": CollaborationMode.REVIEW,
                "auction": CollaborationMode.AUCTION,
                "hybrid": CollaborationMode.HYBRID,
            }
            selected = mode_map.get(mode_str)
            if selected:
                logger.info(f"LLM策略选择: {selected.value}, params: {params}")
                return selected
        except Exception as e:
            logger.debug(f"LLM策略选择失败，使用兜底规则: {e}")

        # 3. 兜底：简单启发式选择
        if analysis["complexity"] > 0.8 and analysis["requires_review"]:
            return CollaborationMode.REVIEW
        elif analysis["is_parallelizable"] and analysis["estimated_steps"] > 2:
            return CollaborationMode.PIPELINE
        elif analysis["complexity"] > 0.5:
            return CollaborationMode.MASTER_SLAVE
        elif len(task.keywords) > 3:
            return CollaborationMode.AUCTION
        else:
            return CollaborationMode.HYBRID

    async def _get_available_agents(self) -> List[BaseAgent]:
        """获取可用Agent - 优先从agent_pool获取已有Agent"""
        if self.agent_pool:
            agents = await self.agent_pool.get_available_agents()
            if agents:
                logger.info(f"从AgentPool获取到 {len(agents)} 个可用Agent")
                return agents

        try:
            from core.multi_agent_v2.agents.base.base_agent import AgentFactory
            agents = AgentFactory.create_agents_for_task(["general"], 3, 3)
            if self.agent_pool:
                for agent in agents:
                    self.agent_pool.active_agents[agent.agent_id] = agent
                    logger.debug(f"Agent已添加到active_agents: {agent.agent_id}")
            return agents
        except Exception as e:
            logger.warning(f"创建Agent失败: {e}")
            return []

    async def _match_and_assign(
        self,
        task: Task,
        agents: List[BaseAgent],
        mode: CollaborationMode
    ) -> List[Dict[str, Any]]:
        """匹配并分配Agent"""
        logger.info(f"[DEBUG] _match_and_assign called: mode={mode.value}, agents_count={len(agents)}")
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
                agent_type = agent.agent_type.value if hasattr(agent.agent_type, 'value') else str(agent.agent_type)
                assignments.append({
                    "subtask_id": task.task_id,
                    "agent_id": agent.agent_id,
                    "agent_type": agent_type,
                    "score": score,
                    "role": "winner"
                })

        else:
            # 混合模式：简单分配
            logger.info(f"[DEBUG] 混合模式 - 调用matcher.match")
            matched_agents = await self.matcher.match(task, agents)
            logger.info(f"[DEBUG] matcher.match返回: {len(matched_agents)} matches")

            if matched_agents:
                agent, score = matched_agents[0]
                agent_type = agent.agent_type.value if hasattr(agent.agent_type, 'value') else str(agent.agent_type)
                assignments.append({
                    "subtask_id": task.task_id,
                    "agent_id": agent.agent_id,
                    "agent_type": agent_type,
                    "score": score
                })
                logger.info(f"[DEBUG] 添加assignment: agent_id={agent.agent_id}")
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

    async def schedule_with_reflection(
        self,
        task: Task,
        execution_plan: List[Dict[str, Any]],
        executor: Callable
    ) -> Dict[str, Any]:
        """带反思机制的调度执行

        使用LLM反思引擎对执行过程进行评估和动态调整。
        支持5种决策：CONTINUE/SKIP_NEXT/ADD_STEPS/RETRY/FAIL
        """
        logger.info(f"开始带反思的调度执行: {task.task_id}")

        completed_steps: List[StepResult] = []
        current_plan = execution_plan.copy()

        while current_plan:
            if len(completed_steps) >= 50:
                logger.warning("达到最大步骤数，强制结束")
                break

            current_step = current_plan.pop(0)

            expected_time = current_step.get("estimated_time", 10.0)

            try:
                result = await executor(current_step, task)
            except Exception as e:
                logger.error(f"执行步骤失败: {e}")
                result = {
                    "success": False,
                    "error": str(e),
                    "output": None,
                    "execution_time": 0.0,
                    "confidence": 0.0
                }

            step_result = StepResult(
                step_id=current_step.get("subtask_id", current_step.get("task_id", "unknown")),
                step_name=current_step.get("name", current_step.get("description", "unknown")),
                step_type=current_step.get("type", "general"),
                success=result.get("success", True),
                output=result.get("output"),
                error=result.get("error"),
                execution_time=result.get("execution_time", 0.0),
                confidence=result.get("confidence", 1.0)
            )

            completed_steps.append(step_result)

            logger.info(
                f"步骤完成: {step_result.step_name} - "
                f"{'成功' if step_result.success else '失败'} "
                f"(置信度: {step_result.confidence:.2f})"
            )

            if self.reflection_trigger.should_reflect(step_result, expected_time):
                prompt = ReflectionPrompt(
                    completed_steps=completed_steps,
                    remaining_steps=current_plan,
                    original_goal=task.description,
                    task_context={"task_id": task.task_id, "complexity": task.complexity}
                )

                reflection_result = await self.reflection_engine.reflect(prompt, None)

                logger.info(
                    f"反思决策: {reflection_result.decision.value} "
                    f"(置信度: {reflection_result.confidence:.2f})"
                )

                current_plan = self._apply_reflection_decision(
                    reflection_result, current_plan, completed_steps
                )

                if reflection_result.decision == ReflectionDecision.FAIL:
                    logger.error("反思决定：任务失败")
                    return {
                        "success": False,
                        "completed_steps": [s.__dict__ for s in completed_steps],
                        "reason": reflection_result.reasoning,
                        "total_steps": len(completed_steps),
                        "reflection_count": self.reflection_engine.reflection_count,
                        "final_decision": reflection_result.decision.value
                    }

            if result.get("done"):
                break

        return {
            "success": all(s.success for s in completed_steps) if completed_steps else False,
            "completed_steps": [s.__dict__ for s in completed_steps],
            "total_steps": len(completed_steps),
            "reflection_count": self.reflection_engine.reflection_count,
            "final_decision": ReflectionDecision.CONTINUE.value
        }

    def _apply_reflection_decision(
        self,
        reflection: ReflectionResult,
        current_plan: List[Dict[str, Any]],
        completed_steps: List[StepResult]
    ) -> List[Dict[str, Any]]:
        """应用反思决策到执行计划"""
        new_plan = current_plan.copy()

        if reflection.decision == ReflectionDecision.SKIP_NEXT and new_plan:
            skipped = new_plan.pop(0)
            logger.info(f"跳过步骤: {skipped.get('name', 'unknown')}")

        elif reflection.decision == ReflectionDecision.RETRY and completed_steps:
            last_step = completed_steps[-1]
            retry_step = {
                "subtask_id": f"{last_step.step_id}_retry",
                "name": f"重试: {last_step.step_name}",
                "type": last_step.step_type,
                "retry": True,
                "estimated_time": 10.0
            }
            new_plan.insert(0, retry_step)
            logger.info(f"添加重试步骤: {last_step.step_name}")

        elif reflection.decision == ReflectionDecision.ADD_STEPS and reflection.suggestions:
            for suggestion in reflection.suggestions[:2]:
                new_step = {
                    "subtask_id": f"added_{uuid.uuid4().hex[:8]}",
                    "name": suggestion,
                    "type": "added",
                    "description": suggestion,
                    "estimated_time": 10.0
                }
                new_plan.append(new_step)
                logger.info(f"添加新步骤: {suggestion}")

        return new_plan

    def get_reflection_stats(self) -> Dict[str, Any]:
        """获取反思统计"""
        return {
            "total_reflections": self.reflection_engine.reflection_count,
            "pipeline_stats": self.adaptive_pipeline.get_statistics()
        }

    # ==========================================
    # ★ KEPA闭环：消费端实现
    # ==========================================

    async def _subscribe_reflection_messages(self) -> None:
        """订阅Agent反思结果消息 - KEPA闭环入口"""
        try:
            from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus, MessageType
            
            bus = get_shared_bus()
            # 订阅所有Agent的反思结果
            await bus.subscribe("agent:*:reflect", self._handle_reflection_result)
            logger.info("✅ KEPA闭环已激活：调度器已订阅反思结果消息")
        except Exception as e:
            logger.warning(f"KEPA闭环订阅失败: {e}")

    async def _handle_reflection_result(self, message: Any) -> None:
        """处理Agent反思结果 - KEPA闭环核心处理逻辑"""
        try:
            payload = message.payload if hasattr(message, 'payload') else message
            
            agent_id = payload.get("agent_id")
            task_id = payload.get("task_id")
            success = payload.get("success", False)
            lessons_learned = payload.get("lessons_learned", [])
            improvements = payload.get("improvements", [])
            
            if not agent_id or not task_id:
                logger.debug("反思消息缺少必要字段，跳过")
                return

            logger.info(f"📊 收到反思结果: agent={agent_id}, task={task_id}, success={success}")

            # 1. 更新学习缓存
            task_type = payload.get("task_type", "general")
            self.update_learning_cache(task_type, agent_id, success)

            # 2. 更新Agent能力评分
            await self._update_agent_capabilities_from_reflection(
                agent_id, success, lessons_learned, improvements
            )

            # 3. 从技能萃取器学习
            await self._learn_from_skill_extractor(agent_id, task_type)

            # 4. 更新协作模式成功率（跨次学习）
            collaboration_mode = payload.get("collaboration_mode")
            if collaboration_mode:
                self._update_collaboration_success_rate(task_type, collaboration_mode, success)

        except Exception as e:
            logger.error(f"处理反思结果失败: {e}")

    async def _update_agent_capabilities_from_reflection(
        self,
        agent_id: str,
        success: bool,
        lessons_learned: List[str],
        improvements: List[str]
    ) -> None:
        """根据反思结果动态更新Agent能力评分"""
        try:
            if self.agent_pool:
                agent = self.agent_pool.get_agent(agent_id)
                if agent:
                    # 更新Agent的能力评分
                    for capability in agent.capabilities:
                        if success:
                            # 成功：提高专业等级和成功率
                            capability.expertise_level = min(
                                1.0, capability.expertise_level + 0.02
                            )
                            capability.success_rate = min(
                                1.0, capability.success_rate + 0.03
                            )
                        else:
                            # 失败：降低专业等级和成功率
                            capability.expertise_level = max(
                                0.1, capability.expertise_level - 0.05
                            )
                            capability.success_rate = max(
                                0.0, capability.success_rate - 0.05
                            )
                    
                    # 根据改进建议更新偏好工具
                    for improvement in improvements:
                        # 从改进建议中提取工具名称
                        tool_names = self._extract_tool_names_from_text(improvement)
                        for tool_name in tool_names:
                            if tool_name not in capability.preferred_tools:
                                capability.preferred_tools.append(tool_name)
                    
                    logger.info(f"🔧 更新Agent能力: {agent_id}, expertise={agent.capabilities[0].expertise_level:.2f}")
        except Exception as e:
            logger.debug(f"更新Agent能力失败: {e}")

    def _extract_tool_names_from_text(self, text: str) -> List[str]:
        """从文本中提取工具名称（简单模式匹配）"""
        tool_keywords = [
            "web_scraper", "search_engine", "calculator", "data_analysis",
            "translator", "weather", "deep_thinking", "text_analyzer",
            "ocr_recognition", "system_toolbox", "gui_automation", "rag_search"
        ]
        found_tools = []
        for tool in tool_keywords:
            if tool.lower() in text.lower():
                found_tools.append(tool)
        return found_tools

    async def _learn_from_skill_extractor(self, agent_id: str, task_type: str) -> None:
        """从技能萃取器学习，更新Agent能力评分"""
        try:
            from core.skill_extractor import get_skill_extractor
            
            extractor = get_skill_extractor()
            skills = extractor.search_skills(task_type)
            
            for skill in skills:
                # 如果找到相关技能，提高对应能力评分
                if self.agent_pool:
                    agent = self.agent_pool.get_agent(agent_id)
                    if agent:
                        for capability in agent.capabilities:
                            # 根据技能名称匹配能力
                            if any(keyword in capability.name.lower() for keyword in skill.name.lower().split()):
                                capability.expertise_level = min(
                                    1.0, capability.expertise_level + 0.05
                                )
                                capability.success_rate = min(
                                    1.0, capability.success_rate + 0.03
                                )
                                # 更新偏好工具
                                capability.preferred_tools.extend(skill.dependencies)
                                capability.preferred_tools = list(set(capability.preferred_tools))
                                
                                logger.info(f"📚 技能学习: agent={agent_id}, skill={skill.name}, expertise={capability.expertise_level:.2f}")
                                
                                # 更新技能使用统计
                                extractor.increment_usage(skill.name, success=True)
        except Exception as e:
            logger.debug(f"从技能萃取器学习失败: {e}")

    def _update_collaboration_success_rate(self, task_type: str, collaboration_mode: str, success: bool) -> None:
        """更新协作模式成功率（跨次学习）"""
        if task_type not in self.collaboration_history:
            self.collaboration_history[task_type] = {}
        
        if collaboration_mode not in self.collaboration_history[task_type]:
            self.collaboration_history[task_type][collaboration_mode] = 0.5  # 初始值
        
        current_rate = self.collaboration_history[task_type][collaboration_mode]
        
        if success:
            # 成功：提高成功率
            self.collaboration_history[task_type][collaboration_mode] = min(
                1.0, current_rate + 0.05
            )
        else:
            # 失败：降低成功率
            self.collaboration_history[task_type][collaboration_mode] = max(
                0.0, current_rate - 0.1
            )
        
        logger.debug(f"📈 协作模式成功率更新: {task_type} -> {collaboration_mode} = {self.collaboration_history[task_type][collaboration_mode]:.2f}")

    async def _publish_scheduling_metrics(self, task_id: str, mode: CollaborationMode, result: Any) -> None:
        """发布调度指标到 SharedBus（消费 SchedulingMetrics）
        
        将收集的调度指标发布到消息总线，供监控和分析系统消费
        """
        try:
            from core.multi_agent_v2.infrastructure.shared_bus import get_shared_bus, Message, MessageType
            
            bus = get_shared_bus()
            metrics_data = {
                "task_id": task_id,
                "collaboration_mode": mode.value,
                "success": result.success if hasattr(result, 'success') else False,
                "total_tasks": self.metrics.total_tasks,
                "successful_tasks": self.metrics.successful_tasks,
                "failed_tasks": self.metrics.failed_tasks,
                "success_rate": self.metrics.success_rate,
                "avg_scheduling_time": self.metrics.avg_scheduling_time,
                "agent_utilization": self.metrics.agent_utilization,
            }
            
            await bus.publish(
                "scheduler:metrics",
                Message(
                    type=MessageType.REFLECTION_RESULT,  # 复用现有消息类型
                    sender="intelligent_scheduler",
                    topic=f"task:{task_id}:metrics",
                    payload=metrics_data
                )
            )
            logger.debug(f"📊 调度指标已发布: success_rate={metrics_data['success_rate']:.2%}")
        except Exception as e:
            logger.debug(f"发布调度指标失败: {e}")


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

# ══════════════════════════════════════════════════════════════════════════════
# 以下内容来自 capability_matcher.py（能力匹配）
# ══════════════════════════════════════════════════════════════════════════════

"""
能力匹配器 - 智能匹配Agent能力与任务需求

考虑因素：
1. 能力相关性（关键词匹配）
2. 专业等级（任务难度 vs Agent能力）
3. 当前负载（避免过载）
4. 历史表现（成功率、执行时间）
5. 协作兼容性
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
import time

logger = logging.getLogger(__name__)


class MatchStrategy(Enum):
    """匹配策略"""
    EXACT = "exact"           # 精确匹配
    FUZZY = "fuzzy"           # 模糊匹配
    SEMANTIC = "semantic"     # 语义匹配
    HYBRID = "hybrid"         # 混合匹配


@dataclass
class MatchScore:
    """匹配分数"""
    agent_id: str
    agent_type: str
    total_score: float
    capability_score: float
    expertise_score: float
    load_score: float
    performance_score: float
    compatibility_score: float
    match_details: Dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other: 'MatchScore') -> bool:
        return self.total_score < other.total_score


@dataclass
class TaskRequirement:
    """任务需求"""
    task_id: str
    task_type: str
    keywords: List[str]
    complexity: float
    priority: int
    deadline: Optional[float] = None
    required_capabilities: List[str] = field(default_factory=list)
    preferred_tools: List[str] = field(default_factory=list)
    collaboration_mode: Optional[str] = None


@dataclass
class AgentCapability:
    """Agent能力"""
    agent_id: str
    agent_type: str
    capabilities: List[str]
    expertise_level: float
    current_load: float
    max_load: float
    success_rate: float
    avg_execution_time: float
    available_tools: List[str]
    last_active: float


class IntentType(Enum):
    """意图类型"""
    QUERY = "query"                     # 查询
    ACTION = "action"                   # 执行动作
    CREATION = "creation"               # 创建内容
    ANALYSIS = "analysis"              # 分析
    MODIFICATION = "modification"       # 修改
    DELETION = "deletion"              # 删除
    COMPARISON = "comparison"           # 比较
    SUMMARY = "summary"                # 总结
    UNKNOWN = "unknown"                 # 未知


@dataclass
class ExtractedEntity:
    """提取的实体"""
    entity_type: str
    entity_value: str


@dataclass
class ExtractedEntity:
    """提取的实体"""
    entity_type: str
    entity_value: str


@dataclass
class IntentConfidence:
    """意图置信度"""
    primary_intent: IntentType
    confidence: float
    alternative_intents: List[tuple] = field(default_factory=list)


@dataclass
class TaskConstraints:
    """任务约束"""
    time_constraint: Optional[str] = None    # 时间约束
    quality_requirements: List[str] = field(default_factory=list)  # 质量要求
    format_requirements: List[str] = field(default_factory=list)   # 格式要求
    budget_constraints: Optional[Dict] = None  # 预算约束
    custom_constraints: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedIntent:
    """解析后的意图"""
    original_input: str
    intent_type: IntentType
    intent_confidence: IntentConfidence
    primary_goal: str
    entities: List[ExtractedEntity] = field(default_factory=list)
    constraints: TaskConstraints = field(default_factory=TaskConstraints)
    task_keywords: List[str] = field(default_factory=list)
    estimated_complexity: TaskComplexity = TaskComplexity.MODERATE

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IntentUnderstandingConfig:
    """意图理解配置"""
    use_llm: bool = True
    fallback_to_rules: bool = True
    extract_entities: bool = True
    identify_constraints: bool = True
    confidence_threshold: float = 0.7  # 规则置信度阈值,≥0.7走快速路径,<0.7尝试LLM增强
    max_retries: int = 2


class EntityExtractor:
    """实体提取器"""

    def __init__(self):
        # 实体模式定义
        self.entity_patterns = {
            "number": r"\d+(?:\.\d+)?",
            "date": r"\d{4}(?:[-/年](?:\d{1,2}(?:[-/月]\d{1,2}[日]?)?)?)?",  # 支持: 2024, 2024年, 2024-01, 2024年1月, 2024-01-01, 2024年1月1日
            "time": r"\d{1,2}[时:]\d{2}",
            "email": r"[\w\.-]+@[\w\.-]+\.\w+",
            "url": r"https?://[\w\./\-?=&#]+",
            "file_path": r"/[\w/\.-]+",
            "money": r"(?:RMB|¥|\$|USD|EUR)\s*\d+(?:\.\d+)?",
        }

    def extract(self, text: str) -> List[ExtractedEntity]:
        """提取文本中的实体"""
        entities = []

        for entity_type, pattern in self.entity_patterns.items():
            matches = re.finditer(pattern, text)
            for match in matches:
                entities.append(ExtractedEntity(
                    name=match.group(),
                    type=entity_type,
                    value=match.group(),
                    confidence=0.9
                ))

        return entities


class ConstraintIdentifier:
    """约束识别器"""

    def __init__(self):
        self.constraint_patterns = {
            "time": [
                (r"(\d+)(?:分钟|小时|天|周)", "duration"),
                (r"在\d+(?:分钟|小时|天)内", "deadline"),
                (r"尽快|立刻|马上", "urgent"),
            ],
            "quality": [
                (r"高质量|高品质|高标准", "high_quality"),
                (r"精确|准确|无误", "accuracy"),
                (r"详细|完整|全面", "completeness"),
            ],
            "format": [
                (r"用(?:JSON|XML|CSV|Excel)", "structured_format"),
                (r"以.*格式", "specified_format"),
                (r"图表|可视化|图形", "visual"),
            ],
            "budget": [
                (r"预算\s*(?:为)?\d+", "budget_limit"),
                (r"不超过\s*\d+", "cost_ceiling"),
            ]
        }

    def identify(self, text: str) -> TaskConstraints:
        """识别文本中的约束"""
        constraints = TaskConstraints()

        for category, patterns in self.constraint_patterns.items():
            for pattern, constraint_type in patterns:
                if re.search(pattern, text):
                    if category == "time":
                        constraints.time_constraint = constraint_type
                    elif category == "quality":
                        constraints.quality_requirements.append(constraint_type)
                    elif category == "format":
                        constraints.format_requirements.append(constraint_type)
                    elif category == "budget":
                        constraints.budget_constraints = {"type": constraint_type}

        return constraints


class KeywordExtractor:
    """关键词提取器"""

    def __init__(self):
        self.stop_words = {
            "的", "了", "在", "是", "我", "有", "和", "就",
            "不", "人", "都", "一", "一个", "上", "也", "很",
            "到", "说", "要", "去", "你", "会", "着", "没有"
        }

    def extract(self, text: str) -> List[str]:
        """提取关键词"""
        # 简单分词
        words = re.findall(r"[\w]+", text)

        # 过滤停用词和短词
        keywords = [
            w for w in words
            if w not in self.stop_words and len(w) >= 2
        ]

        return list(set(keywords))[:10]  # 最多10个关键词


class RuleBasedIntentClassifier:
    """基于规则的意图分类器"""

    def __init__(self):
        self.intent_keywords = {
            IntentType.QUERY: ["查询", "找", "搜索", "查找", "什么", "如何", "怎么", "多少"],
            IntentType.ACTION: ["执行", "运行", "开始", "启动", "做", "进行"],
            IntentType.CREATION: ["创建", "生成", "制作", "写", "新建"],
            IntentType.ANALYSIS: ["分析", "统计", "计算", "评估"],
            IntentType.MODIFICATION: ["修改", "更新", "调整", "改变", "编辑"],
            IntentType.DELETION: ["删除", "移除", "清除", "去掉"],
            IntentType.COMPARISON: ["比较", "对比", "差异", "哪个好"],
            IntentType.SUMMARY: ["总结", "概括", "汇总", "归纳"],
        }

    def classify(self, text: str) -> IntentConfidence:
        """分类意图"""
        text_lower = text.lower()
        scores = {}

        for intent_type, keywords in self.intent_keywords.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[intent_type] = score

        if not scores:
            return IntentConfidence(
                primary_intent=IntentType.UNKNOWN,
                confidence=0.3
            )

        # 找最高分
        primary = max(scores.items(), key=lambda x: x[1])
        confidence = min(primary[1] / 3, 1.0)  # 归一化

        # 记录其他可能意图
        alternatives = [(k, v) for k, v in scores.items() if k != primary[0]]

        return IntentConfidence(
            primary_intent=primary[0],
            confidence=confidence,
            alternative_intents=alternatives[:2]
        )


class LLMIntentClassifier:
    """LLM辅助意图分类器"""

    def __init__(self, llm_facade: Optional[Any] = None):
        self.llm_facade = llm_facade

    async def classify(self, text: str) -> IntentConfidence:
        """使用LLM分类意图"""
        if not self.llm_facade:
            # 回退到规则分类器
            rule_classifier = RuleBasedIntentClassifier()
            return rule_classifier.classify(text)

        prompt = self._build_classification_prompt(text)

        try:
            response = await self.llm_facade.generate(prompt)
            return self._parse_classification_response(response, text)

        except Exception as e:
            logger.error(f"LLM意图分类失败: {e}，回退到规则分类")
            rule_classifier = RuleBasedIntentClassifier()
            return rule_classifier.classify(text)

    def _build_classification_prompt(self, text: str) -> Dict[str, Any]:
        """构建分类Prompt"""
        system_prompt = """你是一个意图分类专家。请分析用户输入，判断其主要意图。

意图类型：
- query: 查询信息
- action: 执行动作
- creation: 创建内容
- analysis: 分析数据
- modification: 修改内容
- deletion: 删除内容
- comparison: 比较
- summary: 总结

请只输出一个词：主要的意图类型。"""

        return {
            "prompt": f"{system_prompt}\n\n用户输入：{text}",
            "metadata": {"task_type": "intent_classification"}
        }

    def _parse_classification_response(self, response: str, original_text: str) -> IntentConfidence:
        """解析LLM响应"""
        response_lower = response.lower().strip()

        # 映射到IntentType
        intent_mapping = {
            "query": IntentType.QUERY,
            "action": IntentType.ACTION,
            "creation": IntentType.CREATION,
            "analysis": IntentType.ANALYSIS,
            "modification": IntentType.MODIFICATION,
            "deletion": IntentType.DELETION,
            "comparison": IntentType.COMPARISON,
            "summary": IntentType.SUMMARY,
        }

        primary = intent_mapping.get(response_lower, IntentType.UNKNOWN)

        # 简单置信度估计
        confidence = 0.8 if primary != IntentType.UNKNOWN else 0.3

        return IntentConfidence(
            primary_intent=primary,
            confidence=confidence
        )


class IntentUnderstandingSystem:
    """意图理解系统 - 统一入口"""

    def __init__(
        self,
        config: Optional[IntentUnderstandingConfig] = None,
        llm_facade: Optional[Any] = None
    ):
        self.config = config or IntentUnderstandingConfig()
        self.llm_facade = llm_facade

        # 初始化各组件
        self.entity_extractor = EntityExtractor()
        self.constraint_identifier = ConstraintIdentifier()
        self.keyword_extractor = KeywordExtractor()
        self.rule_classifier = RuleBasedIntentClassifier()
        self.llm_classifier = LLMIntentClassifier(llm_facade)

    async def understand(self, user_input: str) -> ParsedIntent:
        """理解用户输入

        Args:
            user_input: 用户的原始输入

        Returns:
            ParsedIntent: 结构化的意图表示
        """
        logger.info(f"开始理解用户输入: {user_input[:50]}...")

        # 1. 意图分类
        intent_confidence = await self._classify_intent(user_input)

        # 2. 提取实体
        entities = []
        if self.config.extract_entities:
            entities = self.entity_extractor.extract(user_input)

        # 3. 识别约束
        constraints = TaskConstraints()
        if self.config.identify_constraints:
            constraints = self.constraint_identifier.identify(user_input)

        # 4. 提取关键词
        keywords = self.keyword_extractor.extract(user_input)

        # 5. 估计复杂度
        complexity = self._estimate_complexity(user_input, entities, keywords)

        # 6. 提取主要目标
        primary_goal = self._extract_primary_goal(user_input)

        parsed_intent = ParsedIntent(
            original_input=user_input,
            intent_type=intent_confidence.primary_intent,
            intent_confidence=intent_confidence,
            primary_goal=primary_goal,
            entities=entities,
            constraints=constraints,
            task_keywords=keywords,
            estimated_complexity=complexity,
            metadata={
                "llm_used": self.llm_facade is not None,
                "entity_count": len(entities),
                "constraint_count": len(constraints.quality_requirements) +
                                   len(constraints.format_requirements)
            }
        )

        logger.info(
            f"意图理解完成: {intent_confidence.primary_intent.value} "
            f"(置信度: {intent_confidence.confidence:.2f}), "
            f"复杂度: {complexity.value}, "
            f"关键词: {', '.join(keywords[:5])}"
        )

        return parsed_intent

    async def _classify_intent(self, text: str) -> IntentConfidence:
        """分类意图 - LLM优先,规则兜底
        
        执行顺序:
        1. 优先使用LLM分类(更精准,理解上下文)
        2. LLM失败或禁用时,使用规则分类(快速、稳定)
        """
        # 1. 优先使用LLM分类
        if self.config.use_llm and self.llm_facade:
            try:
                logger.info(f"使用LLM进行意图分类...")
                llm_result = await self.llm_classifier.classify(text)
                
                if llm_result.confidence >= 0.6:
                    logger.info(f"LLM分类成功: {llm_result.primary_intent.value} (置信度: {llm_result.confidence:.2f})")
                    return llm_result
                else:
                    logger.info(f"LLM置信度较低({llm_result.confidence:.2f}),尝试规则分类...")
                    
            except Exception as e:
                logger.warning(f"LLM分类失败: {e},回退到规则结果")
        
        # 2. 回退到规则分类
        rule_result = self.rule_classifier.classify(text)
        logger.debug(f"规则分类结果: {rule_result.primary_intent.value} (置信度: {rule_result.confidence:.2f})")
        return rule_result

    def _extract_primary_goal(self, text: str) -> str:
        """提取主要目标"""
        # 简单实现：去除语气词和辅助词，保留核心描述
        patterns_to_remove = [
            r"帮我|请|能不能|是否可以",
            r"的|一下|一下下",
            r"尽快|马上|立刻"
        ]

        goal = text
        for pattern in patterns_to_remove:
            goal = re.sub(pattern, "", goal)

        return goal.strip()

    def _estimate_complexity(
        self,
        text: str,
        entities: List[ExtractedEntity],
        keywords: List[str]
    ) -> TaskComplexity:
        """估计任务复杂度"""
        complexity_score = 0

        # 基于关键词估计
        complex_keywords = [
            "分析", "统计", "比较", "评估",
            "创建", "生成", "制作",
            "多个", "各种", "一系列"
        ]

        for kw in complex_keywords:
            if kw in text:
                complexity_score += 1

        # 基于实体数量
        if len(entities) >= 5:
            complexity_score += 2
        elif len(entities) >= 3:
            complexity_score += 1

        # 基于关键词数量
        if len(keywords) >= 8:
            complexity_score += 2
        elif len(keywords) >= 5:
            complexity_score += 1

        # 映射到复杂度级别
        if complexity_score >= 5:
            return TaskComplexity.VERY_COMPLEX
        elif complexity_score >= 3:
            return TaskComplexity.COMPLEX
        elif complexity_score >= 1:
            return TaskComplexity.MODERATE
        else:
            return TaskComplexity.SIMPLE

    def understand_sync(self, user_input: str) -> ParsedIntent:
        """同步理解（不调用LLM）"""
        # 使用规则方法
        config_without_llm = IntentUnderstandingConfig(use_llm=False)
        self.config = config_without_llm

        # 同步执行各步骤
        intent_confidence = self.rule_classifier.classify(user_input)
        entities = self.entity_extractor.extract(user_input)
        constraints = self.constraint_identifier.identify(user_input)
        keywords = self.keyword_extractor.extract(user_input)
        complexity = self._estimate_complexity(user_input, entities, keywords)
        primary_goal = self._extract_primary_goal(user_input)

        return ParsedIntent(
            original_input=user_input,
            intent_type=intent_confidence.primary_intent,
            intent_confidence=intent_confidence,
            primary_goal=primary_goal,
            entities=entities,
            constraints=constraints,
            task_keywords=keywords,
            estimated_complexity=complexity,
            metadata={"llm_used": False}
        )


class TaskDefinitionGenerator:
    """任务定义生成器 - 从ParsedIntent生成可执行任务"""

    def __init__(self, intent_system: IntentUnderstandingSystem):
        self.intent_system = intent_system

    async def generate_task_definition(
        self,
        user_input: str,
        session_context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """生成任务定义

        Args:
            user_input: 用户输入
            session_context: 会话上下文

        Returns:
            结构化的任务定义
        """
        # 1. 理解意图
        parsed_intent = await self.intent_system.understand(user_input)

        # 2. 生成任务定义
        task_definition = {
            "task_id": f"task_{int(time.time())}",
            "goal": parsed_intent.primary_goal,
            "intent_type": parsed_intent.intent_type.value,
            "complexity": parsed_intent.estimated_complexity.value,
            "keywords": parsed_intent.task_keywords,
            "entities": [
                {
                    "name": e.name,
                    "type": e.type,
                    "value": e.value
                }
                for e in parsed_intent.entities
            ],
            "constraints": {
                "time": parsed_intent.constraints.time_constraint,
                "quality": parsed_intent.constraints.quality_requirements,
                "format": parsed_intent.constraints.format_requirements,
            },
            "estimated_steps": self._estimate_steps(parsed_intent),
            "collaboration_mode": self._select_collaboration_mode(parsed_intent),
            "confidence": parsed_intent.intent_confidence.confidence,
            "metadata": parsed_intent.metadata
        }

        return task_definition

    def _estimate_steps(self, intent: ParsedIntent) -> int:
        """估算所需步骤数"""
        complexity = intent.estimated_complexity

        step_mapping = {
            TaskComplexity.SIMPLE: 1,
            TaskComplexity.MODERATE: 3,
            TaskComplexity.COMPLEX: 5,
            TaskComplexity.VERY_COMPLEX: 8
        }

        base_steps = step_mapping.get(complexity, 3)

        # 根据实体数量调整
        if len(intent.entities) > 5:
            base_steps += 1

        return base_steps

    def _select_collaboration_mode(self, intent: ParsedIntent) -> str:
        """选择协作模式"""
        complexity = intent.estimated_complexity

        if complexity in [TaskComplexity.VERY_COMPLEX, TaskComplexity.COMPLEX]:
            return "review"  # 需要评审
        elif complexity == TaskComplexity.MODERATE:
            return "master_slave"  # 主从模式
        else:
            return "pipeline"  # 简单流水线

# ══════════════════════════════════════════════════════════════════════════════
# 以下内容来自 task_planner.py（任务规划）
# ══════════════════════════════════════════════════════════════════════════════

"""
任务规划器 - 智能任务分解与规划

功能：
1. 任务理解 - 解析任务类型、复杂度
2. 任务分解 - 将复杂任务拆解为子任务
3. 依赖分析 - 分析子任务之间的依赖关系
4. 执行计划 - 生成执行顺序和时间安排
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from enum import Enum
import uuid
import time

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """任务类型"""
    SIMPLE = "simple"           # 简单任务
    SEQUENTIAL = "sequential"   # 顺序任务
    PARALLEL = "parallel"     # 并行任务
    HIERARCHICAL = "hierarchical"  # 层次任务
    MIXED = "mixed"           # 混合任务


class TaskPriority(Enum):
    """任务优先级"""
    CRITICAL = 0    # 关键
    HIGH = 1        # 高
    MEDIUM = 2      # 中
    LOW = 3         # 低


@dataclass
class SubTask:
    """子任务"""
    subtask_id: str
    parent_task_id: str
    description: str
    task_type: str
    keywords: List[str] = field(default_factory=list)
    complexity: float = 0.5
    estimated_time: float = 10.0
    dependencies: List[str] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)
    priority: TaskPriority = TaskPriority.MEDIUM
    status: str = "pending"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    """执行计划"""
    plan_id: str
    original_task: str
    subtasks: List[SubTask]
    execution_order: List[str]  # 按执行顺序排列的subtask_id
    total_estimated_time: float
    collaboration_mode: str
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class TaskPlanner:
    """任务规划器"""

    def __init__(self):
        self.plan_history: List[ExecutionPlan] = []
        self._task_patterns = self._initialize_patterns()
        logger.info("任务规划器初始化完成")

    def _initialize_patterns(self) -> Dict[str, Dict[str, Any]]:
        """初始化任务模式"""
        return {
            "web_scraping": {
                "keywords": ["爬取", "抓取", "网页", "数据"],
                "subtasks": [
                    {"description": "分析目标网站结构", "type": "analysis", "complexity": 0.3},
                    {"description": "设计爬虫策略", "type": "planning", "complexity": 0.4},
                    {"description": "执行数据抓取", "type": "execution", "complexity": 0.7},
                    {"description": "数据清洗处理", "type": "processing", "complexity": 0.5},
                    {"description": "存储结果", "type": "storage", "complexity": 0.3}
                ],
                "collaboration_mode": "pipeline"
            },
            "data_analysis": {
                "keywords": ["分析", "统计", "数据", "报告"],
                "subtasks": [
                    {"description": "收集数据", "type": "collection", "complexity": 0.4},
                    {"description": "数据预处理", "type": "preprocessing", "complexity": 0.5},
                    {"description": "执行分析", "type": "analysis", "complexity": 0.7},
                    {"description": "生成可视化", "type": "visualization", "complexity": 0.5},
                    {"description": "撰写报告", "type": "reporting", "complexity": 0.6}
                ],
                "collaboration_mode": "pipeline"
            },
            "code_review": {
                "keywords": ["评审", "审查", "代码", "质量"],
                "subtasks": [
                    {"description": "代码静态分析", "type": "static_analysis", "complexity": 0.4},
                    {"description": "安全漏洞检测", "type": "security_check", "complexity": 0.6},
                    {"description": "性能分析", "type": "performance_check", "complexity": 0.5},
                    {"description": "代码规范检查", "type": "style_check", "complexity": 0.3}
                ],
                "collaboration_mode": "parallel_review"
            },
            "research": {
                "keywords": ["研究", "调研", "搜索", "资料"],
                "subtasks": [
                    {"description": "明确研究目标", "type": "definition", "complexity": 0.3},
                    {"description": "信息收集", "type": "collection", "complexity": 0.6},
                    {"description": "信息整理", "type": "organization", "complexity": 0.5},
                    {"description": "分析总结", "type": "analysis", "complexity": 0.7}
                ],
                "collaboration_mode": "master_slave"
            }
        }

    async def plan(self, task_description: str, context: Optional[Dict[str, Any]] = None) -> ExecutionPlan:
        """规划任务

        Args:
            task_description: 任务描述
            context: 上下文信息

        Returns:
            执行计划
        """
        logger.info(f"开始规划任务: {task_description}")

        # 1. 理解任务
        task_type = await self._understand_task(task_description)

        # 2. 分解任务
        subtasks = await self._decompose_task(task_description, task_type)

        # 3. 分析依赖
        await self._analyze_dependencies(subtasks)

        # 4. 确定执行顺序
        execution_order = await self._determine_execution_order(subtasks)

        # 5. 计算总时间
        total_time = sum(st.estimated_time for st in subtasks)

        # 6. 确定协作模式
        collaboration_mode = await self._determine_collaboration_mode(task_type, subtasks)

        # 7. 创建执行计划
        plan = ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            original_task=task_description,
            subtasks=subtasks,
            execution_order=execution_order,
            total_estimated_time=total_time,
            collaboration_mode=collaboration_mode,
            metadata={
                "task_type": task_type.value,
                "context": context or {}
            }
        )

        # 记录历史
        self.plan_history.append(plan)

        logger.info(f"任务规划完成，生成{len(subtasks)}个子任务")
        return plan

    async def _understand_task(self, task_description: str) -> TaskType:
        """理解任务类型"""
        # 简单的关键词匹配
        for pattern_name, pattern in self._task_patterns.items():
            for keyword in pattern["keywords"]:
                if keyword in task_description:
                    # 根据模式确定任务类型
                    if pattern["collaboration_mode"] == "pipeline":
                        return TaskType.SEQUENTIAL
                    elif pattern["collaboration_mode"] == "parallel_review":
                        return TaskType.PARALLEL
                    elif pattern["collaboration_mode"] == "master_slave":
                        return TaskType.HIERARCHICAL

        # 默认返回简单任务
        return TaskType.SIMPLE

    async def _decompose_task(
        self,
        task_description: str,
        task_type: TaskType
    ) -> List[SubTask]:
        """分解任务"""
        subtasks = []

        # 查找匹配的模式
        matched_pattern = None
        for pattern_name, pattern in self._task_patterns.items():
            for keyword in pattern["keywords"]:
                if keyword in task_description:
                    matched_pattern = pattern
                    break
            if matched_pattern:
                break

        if matched_pattern:
            # 使用预定义的子任务
            for i, subtask_def in enumerate(matched_pattern["subtasks"]):
                subtask = SubTask(
                    subtask_id=f"subtask_{i}",
                    parent_task_id=str(uuid.uuid4()),
                    description=subtask_def["description"],
                    task_type=subtask_def["type"],
                    complexity=subtask_def["complexity"],
                    estimated_time=subtask_def["complexity"] * 20.0
                )
                subtasks.append(subtask)
        else:
            # 通用分解
            subtask = SubTask(
                subtask_id="subtask_0",
                parent_task_id=str(uuid.uuid4()),
                description=task_description,
                task_type="general",
                complexity=0.5,
                estimated_time=10.0
            )
            subtasks.append(subtask)

        return subtasks

    async def _analyze_dependencies(self, subtasks: List[SubTask]) -> None:
        """分析子任务依赖关系"""
        # 简单的顺序依赖
        for i in range(1, len(subtasks)):
            subtasks[i].dependencies.append(subtasks[i-1].subtask_id)

    async def _determine_execution_order(self, subtasks: List[SubTask]) -> List[str]:
        """确定执行顺序"""
        # 拓扑排序
        order = []
        visited = set()

        def visit(subtask: SubTask):
            if subtask.subtask_id in visited:
                return
            visited.add(subtask.subtask_id)

            # 先访问依赖的任务
            for dep_id in subtask.dependencies:
                dep = next((st for st in subtasks if st.subtask_id == dep_id), None)
                if dep:
                    visit(dep)

            order.append(subtask.subtask_id)

        for subtask in subtasks:
            visit(subtask)

        return order

    async def _determine_collaboration_mode(
        self,
        task_type: TaskType,
        subtasks: List[SubTask]
    ) -> str:
        """确定协作模式"""
        if task_type == TaskType.SEQUENTIAL:
            return "pipeline"
        elif task_type == TaskType.PARALLEL:
            return "parallel_review"
        elif task_type == TaskType.HIERARCHICAL:
            return "master_slave"
        else:
            return "single"

    def get_plan_history(self, limit: int = 100) -> List[ExecutionPlan]:
        """获取规划历史"""
        return self.plan_history[-limit:]

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self.plan_history:
            return {
                "total_plans": 0,
                "avg_subtasks": 0,
                "avg_estimated_time": 0
            }

        total_plans = len(self.plan_history)
        avg_subtasks = sum(len(p.subtasks) for p in self.plan_history) / total_plans
        avg_estimated_time = sum(p.total_estimated_time for p in self.plan_history) / total_plans

        return {
            "total_plans": total_plans,
            "avg_subtasks": avg_subtasks,
            "avg_estimated_time": avg_estimated_time
        }


# 全局任务规划器实例
_task_planner: Optional[TaskPlanner] = None


def get_task_planner() -> TaskPlanner:
    """获取任务规划器实例"""
    global _task_planner
    if _task_planner is None:
        _task_planner = TaskPlanner()
    return _task_planner
