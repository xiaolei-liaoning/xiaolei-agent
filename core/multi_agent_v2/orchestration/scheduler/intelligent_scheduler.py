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
from core.multi_agent_v2.orchestration.collaboration.llm_reflection import (
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
    """

    def __init__(self, context_center: GlobalContextCenter):
        self.context_center = context_center
        
        # 路由权重配置
        self.routing_weights = {
            "priority": 0.25,
            "health": 0.20,
            "time": 0.15,
            "success": 0.20,
            "complexity_match": 0.10,
            "resource_efficiency": 0.10
        }
        
        # 资源可用性缓存
        self.resource_availability: Dict[ResourceType, ResourceAvailability] = {}

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
        
        # 4. 综合评分
        total_score = (
            base_score +
            complexity_match_score * self.routing_weights["complexity_match"] +
            resource_efficiency_score * self.routing_weights["resource_efficiency"]
        )
        
        return round(total_score, 4)

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

            # 执行调度好的任务
            execution_result = await self.execute_scheduled_task(task, execution_plan)
            
            # 将执行结果添加到metadata
            result.metadata["final_result"] = execution_result.get("final_output", "")
            result.metadata["results"] = execution_result.get("results", [])
            result.metadata["file_path"] = execution_result.get("file_path", "")

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
                    # 创建子任务
                    subtask = Task(
                        task_id=subtask_id,
                        type=task.type,
                        description=f"子任务: {step.get('description', '')}",
                        context=task.context,
                        priority=task.priority
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
        if self.agent_pool:
            agents = await self.agent_pool.get_available_agents()
            if agents:
                return agents

        try:
            from core.multi_agent_v2.agents.lazy_agent import LazyAgent
            from core.multi_agent_v2.agents.base.base_agent import AgentType

            agents = []
            for agent_type in [AgentType.MASTER, AgentType.WORKER, AgentType.REVIEWER]:
                agent = LazyAgent(agent_type=agent_type.value)
                await agent.ensure_initialized()
                agents.append(agent)
                logger.debug(f"创建Agent用于调度: {agent.agent_id} ({agent_type.value})")
            
            # 如果有agent_pool，将创建的Agent添加到池中
            if self.agent_pool:
                for agent in agents:
                    agent_type_str = agent.agent_type.value if hasattr(agent.agent_type, 'value') else str(agent.agent_type)
                    await self.agent_pool.acquire(agent_type_str)
                    self.agent_pool.active_agents[agent.agent_id] = agent
                    self.agent_pool.stats.current_active += 1
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
