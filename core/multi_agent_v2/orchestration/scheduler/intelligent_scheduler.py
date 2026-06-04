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
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid

from core.shared.enums import TaskComplexity, ResourceType
from core.multi_agent_v2.agents.base.base_agent import (
    BaseAgent, AgentType, Task, ActionResult,
)
from core.multi_agent_v2.agents.base.models import Capability
from core.multi_agent_v2.orchestration.context.global_context_center import (
    GlobalContextCenter, TaskState, EventType, Event
)
from core.multi_agent_v2.orchestration.collaboration.strategies import (
    LLMReflection, ReflectionTrigger, ReflectionTriggerConfig,
    AdaptivePipelineWithReflection, StepResult, ReflectionPrompt,
    ReflectionDecision, ReflectionResult
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 子模块导入 — 提取到独立模块后在此引用，保持向后兼容
# ---------------------------------------------------------------------------
from .capability_matcher import CapabilityMatcher
from .task_analyzer import TaskAnalyzer
from .mode_selector import ModeSelector
from .execution_planner import ExecutionPlanner
from .result_aggregator import ResultAggregator


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


class IntelligentScheduler:
    """智能调度器 - 多Agent系统的核心大脑"""

    def __init__(self, context_center: GlobalContextCenter, llm_facade: Optional[Any] = None):
        # 核心组件
        self.context_center = context_center
        self.matcher = CapabilityMatcher(context_center)

        # ★ 子模块（从独立模块导入）
        self.analyzer = TaskAnalyzer()
        self.mode_selector = ModeSelector()
        self.planner = ExecutionPlanner(context_center, self.matcher)
        self.aggregator = ResultAggregator()

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
            # 1. 任务理解（使用 TaskAnalyzer 模块）
            task_analysis = self.analyzer.analyze(task)

            # 2. 模式选择（使用 ModeSelector 模块）
            collaboration_mode = await self.mode_selector.select(
                task, task_analysis,
                available_agents=None,
                llm_facade=self.llm_facade,
                collaboration_history=self.collaboration_history,
            )

            # 3. 根据协作模式确定 Agent 数量，按需创建
            agent_count = self._estimate_agent_count(collaboration_mode, task)
            if self.agent_pool and hasattr(self.agent_pool, 'create_agents'):
                available_agents = await self.agent_pool.create_agents(task, agent_count)
            else:
                available_agents = []

            if not available_agents:
                raise RuntimeError("没有可用的Agent")

            # 4. Agent匹配 + 执行计划（使用 ExecutionPlanner 模块）
            agent_assignments = await self.planner.create_plan(
                task, available_agents, collaboration_mode, self.agent_pool
            )
            logger.info(f"[DEBUG] agent_assignments: {len(agent_assignments)} assignments")
            if agent_assignments:
                logger.info(f"[DEBUG]   First assignment: {agent_assignments[0]}")

            # 4.5 反问确认：向用户展示计划，获得确认后才继续
            user_confirmed = await self._ask_user_confirmation(
                task, agent_assignments, collaboration_mode
            )
            if not user_confirmed:
                raise RuntimeError("用户取消了任务执行")

            # 5. 创建任务上下文
            await self.context_center.create_task_context(
                request=f"Task: {task.description}",
                trace_id=trace_id,
                task_id=task.task_id
            )

            # 6. agent_assignments 即执行计划（ExecutionPlanner 已包含注册逻辑）
            execution_plan = agent_assignments

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

            # Persist scheduling snapshot
            try:
                from core.multi_agent_v2.infrastructure.persistence import get_snapshot_store
                snapshot_store = get_snapshot_store()
                await snapshot_store.save(task.task_id, {
                    "task_id": task.task_id,
                    "status": "scheduled",
                    "original_request": task.description,
                    "collaboration_mode": collaboration_mode.value,
                    "assigned_agents": dict(result.assigned_agents),
                    "execution_plan": execution_plan,
                    "trace_id": trace_id,
                })
            except Exception as e:
                logger.warning(f"Persist scheduling snapshot failed: {e}")

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

            # 从agent_pool获取agent（OnDemandAgentPool 使用 get_agent()）
            if self.agent_pool:
                agent = self.agent_pool.get_agent(agent_id)

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

    def _estimate_agent_count(self, mode: CollaborationMode, task: Task) -> int:
        """根据协作模式估算需要的 Agent 数量"""
        counts = {
            CollaborationMode.PIPELINE: max(task.estimated_steps, 3),
            CollaborationMode.MASTER_SLAVE: 1 + max(task.estimated_steps, 2),
            CollaborationMode.REVIEW: 3,
            CollaborationMode.AUCTION: 1,
            CollaborationMode.HYBRID: 2,
        }
        return counts.get(mode, 2)

    async def _ask_user_confirmation(
        self,
        task: Task,
        agent_assignments: List[Dict[str, Any]],
        collaboration_mode: CollaborationMode,
    ) -> bool:
        """反问确认：向用户展示调度计划，等待确认

        Returns:
            True 表示用户确认，False 表示取消
        """
        # 构建计划摘要
        lines = [f"任务: {task.description}"]
        lines.append(f"协作模式: {collaboration_mode.value}")
        lines.append(f"Agent 分配 ({len(agent_assignments)} 个):")
        for a in agent_assignments:
            description = a.get("description", a.get("role", "worker"))
            lines.append(f"  - {a['agent_id']}: {description}")
        lines.append("是否继续执行？")

        question = "\n".join(lines)

        try:
            from core.agents.agent_communication import get_question_registry
            import asyncio

            future = get_question_registry().ask(
                agent_id="scheduler",
                agent_name="智能调度器",
                question=question,
                context=f"task:{task.task_id}",
                timeout=30,
            )
            result = await asyncio.wait_for(future, timeout=35)

            if result is None:
                logger.warning(f"反问超时，默认继续: {task.task_id}")
                return True
            if result.lower() in ("cancel", "no", "取消"):
                logger.info(f"用户取消了任务: {task.task_id}")
                return False
            logger.info(f"用户确认执行: {task.task_id}")
            return True
        except ImportError:
            logger.warning("QuestionRegistry 不可用，跳过反问确认")
            return True
        except asyncio.TimeoutError:
            logger.warning(f"反问超时，默认继续: {task.task_id}")
            return True
        except Exception as e:
            logger.warning(f"反问过程异常，默认继续: {e}")
            return True

    async def _get_available_agents(self) -> List[BaseAgent]:
        """获取可用Agent - 使用OnDemandAgentPool创建新Agent"""
        if self.agent_pool:
            agents = await self.agent_pool.get_available_agents()
            if agents:
                logger.info(f"从AgentPool获取到 {len(agents)} 个可用Agent")
                return agents

        logger.warning("AgentPool 无可用 Agent，返回空列表")
        return []

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
                if self.agent_pool and hasattr(self.agent_pool, 'find_alternative_agent'):
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
        if hasattr(self.agent_pool, 'get_all_agents'):
            agents = await self.agent_pool.get_all_agents()

            for agent in agents:
                if agent.current_load > agent.max_load * 0.9:
                    # 负载过高，尝试转移任务
                    logger.info(f"Agent {agent.agent_id} 负载过高，尝试重新分配任务")

                    # 找到负载较低的Agent
                    if hasattr(self.agent_pool, 'find_low_load_agent'):
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
            self.matcher.update_learning_cache(task_type, agent_id, success)

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
        """熔断器是否打开（纯检查，不修改状态）"""
        return self.state == "OPEN"

    async def record_failure(self) -> None:
        """记录失败"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"熔断器打开，失败次数: {self.failure_count}")

    async def record_success(self) -> None:
        """记录成功"""
        self.failure_count = 0

        if self.state == "HALF_OPEN":
            self.half_open_calls += 1

            if self.half_open_calls >= self.half_open_max_calls:
                self.state = "CLOSED"
                logger.info("熔断器关闭，系统恢复")

        elif self.state == "OPEN":
            self.state = "CLOSED"
            self.half_open_calls = 0
            logger.info("熔断器从 OPEN 恢复为 CLOSED")

    async def can_execute(self) -> bool:
        """是否可以执行"""
        if self.state == "CLOSED":
            return True

        if self.state == "OPEN":
            # 检查是否超过恢复超时，触发 OPEN → HALF_OPEN
            if self.last_failure_time and (time.time() - self.last_failure_time > self.recovery_timeout):
                self.state = "HALF_OPEN"
                self.half_open_calls = 0
                return True
            return False

        if self.state == "HALF_OPEN":
            return self.half_open_calls < self.half_open_max_calls

        return False
