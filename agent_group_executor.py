#!/usr/bin/env python3
"""
Agent小组执行引擎 - 协作编排增强版
实现：
1. 三层协作架构：任务感知路由 + 多模式编排 + 动态熔断
2. 四种协作模式：流水线、并行评审、主从协作、动态拍卖
3. 智能负载感知与动态调度
4. 完整的失败降级机制
"""

import asyncio
import logging
import time
import random
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ==========================================
# 枚举定义
# ==========================================
class CollaborationMode(Enum):
    """协作模式枚举（用户建议的4种核心模式）"""
    PIPELINE = "pipeline"              # 流水线模式
    PARALLEL_REVIEW = "parallel_review"  # 并行评审模式
    MASTER_SLAVE = "master_slave"        # 主从协作模式
    DYNAMIC_AUCTION = "dynamic_auction"  # 动态拍卖模式


class CircuitBreakerStrategy(Enum):
    """熔断策略枚举"""
    COUNT_BASED = "count_based"        # 基于失败次数
    RATE_BASED = "rate_based"          # 基于失败率
    TIME_BASED = "time_based"          # 基于时间窗口


class FailureStrategy(Enum):
    """失败处理策略枚举"""
    FAST_FAIL = "fast_fail"            # 快速失败
    RETRY = "retry"                    # 重试
    DEGRADE = "degrade"                # 降级处理
    FALLBACK = "fallback"              # 备用方案


# ==========================================
# 数据结构
# ==========================================
@dataclass
class CircuitBreakerState:
    """熔断器状态"""
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    is_open: bool = False
    half_open_attempts: int = 0


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    delay: float = 1.0  # 秒
    backoff_factor: float = 2.0


@dataclass
class TaskContext:
    """任务上下文（用于流水线模式传递）"""
    task_id: str
    original_task: str
    current_step: int = 0
    results: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class PipelineStep:
    """流水线步骤定义"""
    step_id: str
    name: str
    required_skill: str
    description: str = ""
    optional: bool = False
    retry_on_failure: bool = True


@dataclass
class AgentLoadInfo:
    """Agent负载信息"""
    agent_id: str
    current_tasks: int = 0
    max_tasks: int = 10
    avg_response_time: float = 0.0
    success_rate: float = 1.0
    
    @property
    def load_ratio(self) -> float:
        """计算负载率"""
        return min(1.0, self.current_tasks / self.max_tasks)


# ==========================================
# 熔断策略实现
# ==========================================
class CircuitBreaker:
    """熔断器实现"""
    
    def __init__(
        self,
        strategy: CircuitBreakerStrategy = CircuitBreakerStrategy.COUNT_BASED,
        failure_threshold: int = 5,
        failure_rate_threshold: float = 0.5,
        open_timeout: float = 30.0,
        half_open_attempts: int = 3
    ):
        self.strategy = strategy
        self.failure_threshold = failure_threshold
        self.failure_rate_threshold = failure_rate_threshold
        self.open_timeout = open_timeout
        self.half_open_attempts = half_open_attempts
        self.state = CircuitBreakerState()
    
    def record_success(self):
        """记录成功"""
        self.state.success_count += 1
        self.state.last_success_time = time.time()
        
        # 成功时重置状态
        if self.state.is_open:
            # 半开状态成功，关闭熔断器
            if self.state.half_open_attempts >= 0:
                self.state.is_open = False
                self.state.failure_count = 0
                self.state.half_open_attempts = 0
        else:
            # 关闭状态，重置失败计数
            self.state.failure_count = 0
    
    def record_failure(self):
        """记录失败"""
        self.state.failure_count += 1
        self.state.last_failure_time = time.time()
        self.state.success_count = 0
        
        # 根据策略判断是否打开熔断器
        if self.strategy == CircuitBreakerStrategy.COUNT_BASED:
            self._check_count_based()
        elif self.strategy == CircuitBreakerStrategy.RATE_BASED:
            self._check_rate_based()
        elif self.strategy == CircuitBreakerStrategy.TIME_BASED:
            self._check_time_based()
    
    def _check_count_based(self):
        """基于失败次数的熔断"""
        if self.state.failure_count >= self.failure_threshold:
            self.state.is_open = True
            logger.warning(f"熔断器打开（连续失败 {self.state.failure_count} 次）")
    
    def _check_rate_based(self):
        """基于失败率的熔断"""
        total = self.state.failure_count + self.state.success_count
        if total >= self.failure_threshold:
            failure_rate = self.state.failure_count / total
            if failure_rate >= self.failure_rate_threshold:
                self.state.is_open = True
                logger.warning(f"熔断器打开（失败率 {failure_rate:.2%}）")
    
    def _check_time_based(self):
        """基于时间窗口的熔断"""
        time_window = 60.0
        now = time.time()
        
        if now - self.state.last_failure_time < time_window:
            if self.state.failure_count >= self.failure_threshold:
                self.state.is_open = True
                logger.warning(f"熔断器打开（{time_window}秒内失败 {self.state.failure_count} 次）")
    
    def is_allowed(self) -> bool:
        """检查是否允许执行"""
        if not self.state.is_open:
            return True
        
        # 检查是否可以半开
        if time.time() - self.state.last_failure_time >= self.open_timeout:
            if self.state.half_open_attempts < self.half_open_attempts:
                self.state.half_open_attempts += 1
                logger.info(f"熔断器半开，允许尝试 {self.state.half_open_attempts}/{self.half_open_attempts}")
                return True
        
        return False
    
    def get_state(self) -> Dict[str, Any]:
        """获取熔断器状态"""
        return {
            "is_open": self.state.is_open,
            "failure_count": self.state.failure_count,
            "success_count": self.state.success_count,
            "last_failure_time": self.state.last_failure_time,
            "last_success_time": self.state.last_success_time,
            "half_open_attempts": self.state.half_open_attempts
        }


# ==========================================
# 协作编排器实现
# ==========================================
class AgentGroupExecutor:
    """Agent小组执行引擎 - 支持多模式协作编排"""
    
    def __init__(self):
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.agent_performance: Dict[str, Dict[str, Any]] = {}
        self.agent_load: Dict[str, AgentLoadInfo] = {}
        self._fallback_handlers: Dict[str, Callable] = {}
        self._mode_handlers = {
            CollaborationMode.PIPELINE: self._execute_pipeline,
            CollaborationMode.PARALLEL_REVIEW: self._execute_parallel_review,
            CollaborationMode.MASTER_SLAVE: self._execute_master_slave,
            CollaborationMode.DYNAMIC_AUCTION: self._execute_dynamic_auction
        }
    
    # ==========================================
    # 第一层：任务感知的路由匹配
    # ==========================================
    def _route_agent(
        self,
        required_skill: str,
        available_agents: List[Any],
        exclude_agents: List[str] = None
    ) -> Optional[Any]:
        """
        根据技能和负载路由Agent（核心路由逻辑）
        
        匹配逻辑：
        1. 过滤有对应技能的Agent
        2. 排除指定的Agent
        3. 检查熔断器状态
        4. 优先选择负载最低的Agent
        """
        exclude_agents = exclude_agents or []
        
        # 1. 过滤有对应技能的Agent
        candidates = []
        for agent in available_agents:
            if agent.agent_id in exclude_agents:
                continue
            
            # 检查熔断器
            cb = self.circuit_breakers.get(agent.agent_id)
            if cb and not cb.is_allowed():
                continue
            
            # 检查技能匹配
            agent_skills = [s.skill_id for s in agent.skills]
            if required_skill in agent_skills:
                # 获取负载信息
                load_info = self.agent_load.get(agent.agent_id)
                if load_info and load_info.load_ratio >= 1.0:
                    logger.debug(f"Agent {agent.agent_name} 负载已满，跳过")
                    continue
                
                candidates.append(agent)
        
        if not candidates:
            logger.warning(f"没有找到具备技能 {required_skill} 的可用Agent")
            return None
        
        # 2. 优先选择负载最低、成功率最高的Agent
        best_agent = None
        best_score = float('-inf')
        
        for agent in candidates:
            load_info = self.agent_load.get(agent.agent_id, AgentLoadInfo(agent_id=agent.agent_id))
            perf = self.agent_performance.get(agent.agent_id, {})
            success_rate = perf.get('success_rate', 1.0)
            
            # 综合评分 = 优先级权重 + 成功率权重 + 负载权重
            score = (
                agent.priority * 0.3 +
                success_rate * 0.4 +
                (1 - load_info.load_ratio) * 0.3
            )
            
            if score > best_score:
                best_score = score
                best_agent = agent
        
        logger.info(f"路由选择: {best_agent.agent_name} (技能: {required_skill}, 评分: {best_score:.3f})")
        return best_agent
    
    def _extract_task_features(self, message: str) -> Dict[str, Any]:
        """提取任务特征，用于智能路由"""
        features = {
            "skill_keywords": [],
            "complexity": "simple",
            "requires_review": False,
            "requires_decomposition": False
        }
        
        # 技能关键词映射
        skill_keywords = {
            "code": ["代码", "编程", "开发", "python", "javascript", "java"],
            "research": ["研究", "分析", "调研", "报告"],
            "writing": ["写", "创作", "文案", "文章", "诗"],
            "translation": ["翻译", "英文", "中文"],
            "analysis": ["分析", "统计", "数据", "趋势"],
            "search": ["搜索", "查询", "找", "信息"],
            "review": ["评审", "审核", "检查", "验证"]
        }
        
        for skill, keywords in skill_keywords.items():
            for keyword in keywords:
                if keyword in message:
                    features["skill_keywords"].append(skill)
                    break
        
        # 判断复杂度
        if len(features["skill_keywords"]) >= 2:
            features["complexity"] = "complex"
        
        # 判断是否需要评审
        if any(k in message for k in ["评审", "审核", "验证"]):
            features["requires_review"] = True
        
        # 判断是否需要拆解
        if len(message) > 100 or features["complexity"] == "complex":
            features["requires_decomposition"] = True
        
        return features
    
    # ==========================================
    # 第二层：多模式协作编排
    # ==========================================
    async def execute_with_group(
        self,
        group: Any,
        message: str,
        strategy: Optional[str] = None,
        failure_strategy: Optional[str] = None,
        circuit_strategy: Optional[str] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """使用Agent小组执行任务（统一入口）"""
        
        # 确定协作模式
        mode = self._resolve_collaboration_mode(group, message, strategy)
        
        # 确定失败处理策略
        fail_strategy = FailureStrategy(failure_strategy or getattr(group, 'failure_strategy', "retry"))
        
        logger.info(f"开始执行任务，小组: {group.name}, 协作模式: {mode.value}, 失败策略: {fail_strategy.value}")
        
        # 获取可用Agent
        available_agents = await self._get_available_agents(group, circuit_strategy)
        
        if not available_agents:
            return {
                "success": False,
                "error": "没有可用的Agent",
                "results": [],
                "mode": mode.value,
                "reason": "all_agents_blocked"
            }
        
        # 根据模式执行
        handler = self._mode_handlers.get(mode)
        if not handler:
            return {
                "success": False,
                "error": f"不支持的协作模式: {mode.value}",
                "results": [],
                "mode": mode.value
            }
        
        try:
            result = await handler(group, available_agents, message, fail_strategy, circuit_strategy, timeout)
            result["mode"] = mode.value
            return result
        except Exception as e:
            logger.error(f"任务执行失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "results": [],
                "mode": mode.value
            }
    
    def _resolve_collaboration_mode(self, group: Any, message: str, strategy: Optional[str]) -> CollaborationMode:
        """解析协作模式（智能选择或使用指定策略）"""
        # 策略名称映射（向后兼容旧策略）
        strategy_mapping = {
            "weighted_round_robin": CollaborationMode.DYNAMIC_AUCTION,
            "round_robin": CollaborationMode.DYNAMIC_AUCTION,
            "priority": CollaborationMode.DYNAMIC_AUCTION,
            "collaborative": CollaborationMode.MASTER_SLAVE
        }
        
        if strategy:
            # 如果指定了策略，直接使用
            try:
                return CollaborationMode(strategy)
            except ValueError:
                # 尝试旧策略映射
                if strategy in strategy_mapping:
                    return strategy_mapping[strategy]
                pass
        
        # 获取小组配置的策略
        group_strategy = getattr(group, 'strategy', None)
        if group_strategy:
            try:
                return CollaborationMode(group_strategy)
            except ValueError:
                # 尝试旧策略映射
                if group_strategy in strategy_mapping:
                    return strategy_mapping[group_strategy]
                pass
        
        # 智能推断模式
        return self._infer_mode_from_task(message)
    
    def _infer_mode_from_task(self, message: str) -> CollaborationMode:
        """根据任务内容智能推断协作模式
        
        智能推断逻辑（按优先级）：
        1. 需要评审/审核的任务 → 并行评审模式（最明确）
        2. 需要拆解的复杂任务 → 主从协作模式（需要先拆解再执行）
        3. 需要多步骤流程的任务 → 流水线模式（流程关键词明确）
        4. 简单单一任务 → 动态拍卖模式
        """
        features = self._extract_task_features(message)
        
        # 关键词触发模式判断
        review_keywords = ["评审", "审核", "检查", "验证", "评估", "审查", "复核"]
        pipeline_keywords = ["然后", "接着", "之后", "步骤", "流程", "依次", "先...再", "先...然后", "首先...然后", "第一步", "第二步"]
        master_slave_keywords = ["分析", "研究", "拆解", "分解", "复杂", "详细", "深入"]
        
        # 检查评审关键词（最高优先级）
        if any(keyword in message for keyword in review_keywords) or features["requires_review"]:
            logger.info(f"任务包含评审关键词，推断为并行评审模式")
            return CollaborationMode.PARALLEL_REVIEW
        
        # 检查复杂任务关键词（第二优先级 - 需要先拆解）
        has_complex_keywords = any(keyword in message for keyword in master_slave_keywords)
        has_decomposition_need = features["requires_decomposition"] and features["complexity"] == "complex"
        if has_complex_keywords or has_decomposition_need:
            # 检查是否同时有明确的流程指示
            has_pipeline_keywords = any(keyword in message for keyword in pipeline_keywords)
            if not has_pipeline_keywords:
                logger.info(f"任务需要拆解或复杂，推断为主从协作模式")
                return CollaborationMode.MASTER_SLAVE
        
        # 检查流水线关键词（第三优先级 - 流程描述更明确）
        if any(keyword in message for keyword in pipeline_keywords):
            logger.info(f"任务包含流程步骤关键词，推断为流水线模式")
            return CollaborationMode.PIPELINE
        
        # 检查多技能需求（第四优先级）
        if len(features["skill_keywords"]) >= 2:
            logger.info(f"任务需要多种技能，推断为流水线模式")
            return CollaborationMode.PIPELINE
        
        # 如果之前没匹配到但有复杂关键词，再次检查
        if has_complex_keywords or has_decomposition_need:
            logger.info(f"任务需要拆解或复杂，推断为主从协作模式")
            return CollaborationMode.MASTER_SLAVE
        
        # 默认使用动态拍卖模式
        logger.info(f"任务简单单一，使用动态拍卖模式")
        return CollaborationMode.DYNAMIC_AUCTION
    
    async def _get_available_agents(self, group: Any, circuit_strategy: Optional[str]) -> List[Any]:
        """获取可用的Agent列表（考虑熔断器和负载）"""
        available = []
        
        for agent in group.agents:
            if not agent.enabled:
                continue
            
            # 检查熔断器
            if group.circuit_breaker:
                cb = self._get_circuit_breaker(agent.agent_id, circuit_strategy)
                if not cb.is_allowed():
                    logger.warning(f"Agent {agent.agent_name} 熔断器已打开，跳过")
                    continue
            
            # 检查负载（软限制）
            load_info = self.agent_load.get(agent.agent_id)
            if load_info and load_info.load_ratio >= 0.9:
                logger.warning(f"Agent {agent.agent_name} 负载过高 ({load_info.load_ratio:.1%})，跳过")
                continue
            
            available.append(agent)
        
        return available
    
    # ==========================================
    # 模式1：流水线模式
    # ==========================================
    async def _execute_pipeline(
        self,
        group: Any,
        available_agents: List[Any],
        message: str,
        fail_strategy: FailureStrategy,
        circuit_strategy: Optional[str],
        timeout: Optional[float]
    ) -> Dict[str, Any]:
        """流水线模式：按步骤顺序执行，前一个Agent的输出是后一个的输入"""
        
        # 分析任务，生成流水线步骤
        pipeline_steps = self._generate_pipeline_steps(message)
        
        if not pipeline_steps:
            return {"success": False, "error": "无法生成流水线步骤"}
        
        logger.info(f"流水线模式：{len(pipeline_steps)} 个步骤")
        
        context = {
            "task_id": f"pipeline_{int(time.time())}",
            "original_task": message,
            "current_step": 0,
            "results": {},
            "errors": []
        }
        
        executed_steps = []
        failed_steps = []
        
        for step in pipeline_steps:
            context["current_step"] = step.step_id
            
            # 路由到合适的Agent
            agent = self._route_agent(step.required_skill, available_agents)
            
            if not agent:
                if step.optional:
                    logger.info(f"步骤 {step.name} 可选，跳过")
                    continue
                
                error_msg = f"步骤 {step.name} 无法找到具备技能 {step.required_skill} 的Agent"
                context["errors"].append(error_msg)
                failed_steps.append({"step_id": step.step_id, "error": error_msg})
                continue
            
            # 执行步骤
            try:
                step_input = self._prepare_step_input(context, step)
                result = await self._execute_with_agent(
                    agent,
                    step_input,
                    fail_strategy,
                    group.circuit_breaker,
                    circuit_strategy,
                    timeout
                )
                
                if result.get("success"):
                    context["results"][step.step_id] = result
                    executed_steps.append({
                        "step_id": step.step_id,
                        "agent_name": agent.agent_name,
                        "success": True
                    })
                    self._update_agent_performance(agent.agent_id, success=True)
                    if group.circuit_breaker:
                        self._get_circuit_breaker(agent.agent_id, circuit_strategy).record_success()
                else:
                    if step.retry_on_failure and fail_strategy == FailureStrategy.RETRY:
                        logger.info(f"步骤 {step.name} 失败，尝试重试")
                        result = await self._execute_with_agent(
                            agent,
                            step_input,
                            FailureStrategy.FAST_FAIL,
                            group.circuit_breaker,
                            circuit_strategy,
                            timeout
                        )
                
                if not result.get("success"):
                    failed_steps.append({
                        "step_id": step.step_id,
                        "agent_name": agent.agent_name,
                        "error": result.get("error", "未知错误")
                    })
                    self._update_agent_performance(agent.agent_id, success=False)
                    if group.circuit_breaker:
                        self._get_circuit_breaker(agent.agent_id, circuit_strategy).record_failure()
                    
                    if fail_strategy == FailureStrategy.FAST_FAIL:
                        break
            
            except Exception as e:
                error_msg = f"步骤 {step.name} 执行异常: {str(e)}"
                context["errors"].append(error_msg)
                failed_steps.append({"step_id": step.step_id, "error": error_msg})
                if fail_strategy == FailureStrategy.FAST_FAIL:
                    break
        
        # 整合结果
        final_result = self._aggregate_pipeline_results(context, pipeline_steps)
        
        return {
            "success": len(failed_steps) == 0,
            "mode": "pipeline",
            "pipeline_steps": [s.__dict__ for s in pipeline_steps],
            "executed_steps": executed_steps,
            "failed_steps": failed_steps,
            "result": final_result,
            "total_steps": len(pipeline_steps),
            "completed_steps": len(executed_steps)
        }
    
    def _generate_pipeline_steps(self, message: str) -> List[PipelineStep]:
        """根据任务生成流水线步骤"""
        features = self._extract_task_features(message)
        steps = []
        step_counter = 1
        
        # 根据技能关键词生成步骤
        skill_mapping = {
            "search": ("搜索信息", "搜索相关信息"),
            "research": ("调研分析", "进行调研和分析"),
            "analysis": ("数据分析", "对数据进行分析"),
            "writing": ("内容创作", "创作文本内容"),
            "code": ("代码开发", "开发代码实现"),
            "translation": ("翻译处理", "进行翻译"),
            "review": ("审核评审", "进行审核评审")
        }
        
        for skill in features["skill_keywords"]:
            name, desc = skill_mapping.get(skill, (skill, f"处理{skill}相关任务"))
            steps.append(PipelineStep(
                step_id=f"step_{step_counter}",
                name=name,
                required_skill=skill,
                description=f"{desc}：{message[:30]}...",
                optional=False,
                retry_on_failure=True
            ))
            step_counter += 1
        
        # 如果没有识别到技能，添加默认步骤
        if not steps:
            steps.append(PipelineStep(
                step_id="step_1",
                name="任务处理",
                required_skill="general",
                description=f"处理任务：{message[:50]}...",
                optional=False,
                retry_on_failure=True
            ))
        
        return steps
    
    def _prepare_step_input(self, context: Dict, step: PipelineStep) -> str:
        """准备步骤输入（包含前序结果）"""
        if not context["results"]:
            return step.description
        
        # 拼接前序结果
        inputs = [step.description]
        for prev_step_id, prev_result in context["results"].items():
            if prev_result.get("results"):
                for r in prev_result["results"]:
                    msg = r.get("message", "")
                    if msg:
                        inputs.append(f"【{prev_step_id}结果】{msg[:100]}")
        
        return "\n".join(inputs)
    
    def _aggregate_pipeline_results(self, context: Dict, steps: List[PipelineStep]) -> str:
        """整合流水线结果"""
        if not context["results"]:
            return "未获得有效结果"
        
        parts = ["【流水线执行总结】", f"原始任务: {context['original_task']}", "="*50]
        
        for step in steps:
            result = context["results"].get(step.step_id)
            if result:
                parts.append(f"✓ {step.name}")
                if result.get("results"):
                    for r in result["results"][:2]:
                        msg = r.get("message", "")[:200]
                        if msg:
                            parts.append(f"  {msg}")
        
        parts.append("="*50)
        parts.append(f"完成 {len(context['results'])} / {len(steps)} 步骤")
        
        return "\n".join(parts)
    
    # ==========================================
    # 模式2：并行评审模式
    # ==========================================
    async def _execute_parallel_review(
        self,
        group: Any,
        available_agents: List[Any],
        message: str,
        fail_strategy: FailureStrategy,
        circuit_strategy: Optional[str],
        timeout: Optional[float]
    ) -> Dict[str, Any]:
        """并行评审模式：多Agent并行处理，汇总结果做投票/对比"""
        
        # 筛选评审Agent（具备review技能或高优先级的Agent）
        reviewers = self._select_reviewers(available_agents)
        
        if not reviewers:
            return {"success": False, "error": "没有可用的评审Agent"}
        
        logger.info(f"并行评审模式：{len(reviewers)} 个评审Agent")
        
        # 并行执行评审
        tasks = []
        for agent in reviewers:
            tasks.append(self._execute_review_task(
                agent, message, fail_strategy, group.circuit_breaker, circuit_strategy, timeout
            ))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        review_results = []
        success_count = 0
        errors = []
        
        for i, (agent, result) in enumerate(zip(reviewers, results)):
            if isinstance(result, Exception):
                review_results.append({
                    "agent_id": agent.agent_id,
                    "agent_name": agent.agent_name,
                    "success": False,
                    "error": str(result)
                })
                errors.append(f"评审员 {agent.agent_name} 执行异常: {result}")
            else:
                success_count += 1 if result.get("success") else 0
                review_results.append({
                    "agent_id": agent.agent_id,
                    "agent_name": agent.agent_name,
                    "success": result.get("success", False),
                    "result": result.get("results", [])
                })
                
                if result.get("success"):
                    self._update_agent_performance(agent.agent_id, success=True)
                    if group.circuit_breaker:
                        self._get_circuit_breaker(agent.agent_id, circuit_strategy).record_success()
                else:
                    self._update_agent_performance(agent.agent_id, success=False)
                    if group.circuit_breaker:
                        self._get_circuit_breaker(agent.agent_id, circuit_strategy).record_failure()
        
        # 投票/汇总
        final_decision = self._aggregate_review_votes(review_results)
        
        return {
            "success": success_count > 0,
            "mode": "parallel_review",
            "reviewers": [{"agent_id": a.agent_id, "agent_name": a.agent_name} for a in reviewers],
            "total_reviewers": len(reviewers),
            "success_count": success_count,
            "review_results": review_results,
            "final_decision": final_decision,
            "errors": errors
        }
    
    def _select_reviewers(self, available_agents: List[Any]) -> List[Any]:
        """选择评审Agent"""
        reviewers = []
        
        for agent in available_agents:
            # 检查是否有评审相关技能
            agent_skills = [s.skill_id for s in agent.skills]
            has_review_skill = any(skill in ["review", "checker", "validator"] for skill in agent_skills)
            
            # 高优先级Agent也可以作为评审
            if has_review_skill or agent.priority >= 0.8:
                reviewers.append(agent)
        
        # 限制评审人数（最多5人）
        return reviewers[:5]
    
    async def _execute_review_task(
        self,
        agent: Any,
        message: str,
        fail_strategy: FailureStrategy,
        circuit_breaker: bool,
        circuit_strategy: Optional[str],
        timeout: Optional[float]
    ) -> Dict[str, Any]:
        """执行单个评审任务"""
        review_prompt = f"请对以下内容进行评审：\n\n{message}\n\n请提供详细的评审意见和建议。"
        
        return await self._execute_with_agent(
            agent,
            review_prompt,
            fail_strategy,
            circuit_breaker,
            circuit_strategy,
            timeout
        )
    
    def _aggregate_review_votes(self, results: List[Dict]) -> Dict:
        """汇总评审投票"""
        positive_count = sum(1 for r in results if r.get("success"))
        total_count = len(results)
        
        return {
            "vote_result": "approved" if positive_count >= total_count * 0.6 else "needs_revision",
            "positive_count": positive_count,
            "total_count": total_count,
            "approval_rate": positive_count / total_count if total_count > 0 else 0
        }
    
    # ==========================================
    # 模式3：主从协作模式
    # ==========================================
    async def _execute_master_slave(
        self,
        group: Any,
        available_agents: List[Any],
        message: str,
        fail_strategy: FailureStrategy,
        circuit_strategy: Optional[str],
        timeout: Optional[float]
    ) -> Dict[str, Any]:
        """主从协作模式：主Agent拆解任务，从Agent执行，最后汇总"""
        
        # 选择主Agent（优先级最高的人物Agent）
        master = self._select_master_agent(available_agents)
        
        if not master:
            return {"success": False, "error": "找不到主Agent"}
        
        logger.info(f"主从协作模式：主Agent={master.agent_name}")
        
        # 主Agent拆解任务
        subtasks = await self._decompose_task(master, message)
        
        if not subtasks:
            return {"success": False, "error": "主Agent无法拆解任务"}
        
        logger.info(f"任务拆解为 {len(subtasks)} 个子任务")
        
        # 从Agent执行子任务
        slave_results = []
        executed_subtasks = []
        failed_subtasks = []
        
        for subtask in subtasks:
            # 路由到合适的从Agent
            slave = self._route_agent(subtask["skill"], available_agents, exclude_agents=[master.agent_id])
            
            if not slave:
                failed_subtasks.append({
                    "subtask_id": subtask["subtask_id"],
                    "description": subtask["description"],
                    "error": "找不到合适的从Agent"
                })
                continue
            
            # 执行子任务
            try:
                result = await self._execute_with_agent(
                    slave,
                    subtask["description"],
                    fail_strategy,
                    group.circuit_breaker,
                    circuit_strategy,
                    timeout
                )
                
                if result.get("success"):
                    slave_results.append({
                        "subtask_id": subtask["subtask_id"],
                        "agent_id": slave.agent_id,
                        "agent_name": slave.agent_name,
                        "result": result
                    })
                    executed_subtasks.append(subtask["subtask_id"])
                    self._update_agent_performance(slave.agent_id, success=True)
                    if group.circuit_breaker:
                        self._get_circuit_breaker(slave.agent_id, circuit_strategy).record_success()
                else:
                    failed_subtasks.append({
                        "subtask_id": subtask["subtask_id"],
                        "description": subtask["description"],
                        "agent_name": slave.agent_name,
                        "error": result.get("error", "执行失败")
                    })
                    self._update_agent_performance(slave.agent_id, success=False)
                    if group.circuit_breaker:
                        self._get_circuit_breaker(slave.agent_id, circuit_strategy).record_failure()
            
            except Exception as e:
                failed_subtasks.append({
                    "subtask_id": subtask["subtask_id"],
                    "description": subtask["description"],
                    "error": str(e)
                })
        
        # 主Agent汇总结果
        final_result = await self._merge_results(master, message, slave_results)
        
        return {
            "success": len(failed_subtasks) == 0,
            "mode": "master_slave",
            "master_agent": {"agent_id": master.agent_id, "agent_name": master.agent_name},
            "total_subtasks": len(subtasks),
            "completed_subtasks": len(executed_subtasks),
            "subtasks": subtasks,
            "slave_results": slave_results,
            "failed_subtasks": failed_subtasks,
            "final_result": final_result
        }
    
    def _select_master_agent(self, available_agents: List[Any]) -> Optional[Any]:
        """选择主Agent"""
        # 优先选择人物Agent
        character_agents = [a for a in available_agents if a.agent_type == "character"]
        
        if character_agents:
            return max(character_agents, key=lambda a: a.priority)
        
        # 否则选择优先级最高的Agent
        return max(available_agents, key=lambda a: a.priority) if available_agents else None
    
    async def _decompose_task(self, master: Any, message: str) -> List[Dict]:
        """主Agent拆解任务"""
        decompose_prompt = f"""请将以下任务拆解为若干个子任务：

任务：{message}

请输出JSON格式的子任务列表，每个子任务包含：
- subtask_id: 子任务ID
- description: 子任务描述
- skill: 需要的技能（如search, analysis, writing, code等）
- priority: 优先级（0-1）

输出格式：
[
  {{"subtask_id": "sub1", "description": "...", "skill": "...", "priority": 1.0}},
  ...
]
"""
        
        result = await self._execute_with_agent(master, decompose_prompt, FailureStrategy.FAST_FAIL, False, None, 30)
        
        if not result.get("success"):
            return []
        
        try:
            # 从结果中提取JSON
            for r in result.get("results", []):
                msg = r.get("message", "")
                if "[" in msg and "]" in msg:
                    start = msg.find("[")
                    end = msg.rfind("]") + 1
                    return eval(msg[start:end])
        except Exception as e:
            logger.error(f"解析子任务失败: {e}")
        
        # 如果解析失败，返回默认拆解
        return [
            {"subtask_id": "sub1", "description": message, "skill": "general", "priority": 1.0}
        ]
    
    async def _merge_results(self, master: Any, original_task: str, results: List[Dict]) -> str:
        """主Agent汇总结果"""
        if not results:
            return "没有获得子任务结果"
        
        results_text = "\n\n".join([
            f"【子任务 {r['subtask_id']}】\n{r['agent_name']} 的结果：\n{str(r['result'])}"
            for r in results
        ])
        
        merge_prompt = f"""请汇总以下子任务结果，给出最终答案：

原始任务：{original_task}

子任务结果：
{results_text}

请提供清晰、完整的最终总结。
"""
        
        result = await self._execute_with_agent(master, merge_prompt, FailureStrategy.FAST_FAIL, False, None, 30)
        
        if result.get("success") and result.get("results"):
            final_msg = result["results"][0].get("message", "")
            if final_msg:
                return final_msg
        
        return "汇总完成，但未能生成最终答案"
    
    # ==========================================
    # 模式4：动态拍卖模式
    # ==========================================
    async def _execute_dynamic_auction(
        self,
        group: Any,
        available_agents: List[Any],
        message: str,
        fail_strategy: FailureStrategy,
        circuit_strategy: Optional[str],
        timeout: Optional[float]
    ) -> Dict[str, Any]:
        """动态拍卖模式：Agent通过"出价"竞争任务，调度器选最优解"""
        
        logger.info(f"动态拍卖模式：{len(available_agents)} 个Agent参与")
        
        # 收集Agent出价
        bids = await self._collect_bids(available_agents, message, circuit_strategy)
        
        if not bids:
            return {"success": False, "error": "没有Agent出价"}
        
        # 选择最优Agent
        winning_bid = self._select_winning_bid(bids)
        
        logger.info(f"拍卖结果：{winning_bid['agent_name']} 中标（出价: {winning_bid['bid_score']:.3f}）")
        
        # 执行任务
        winning_agent = next(a for a in available_agents if a.agent_id == winning_bid["agent_id"])
        
        try:
            result = await self._execute_with_agent(
                winning_agent,
                message,
                fail_strategy,
                group.circuit_breaker,
                circuit_strategy,
                timeout
            )
            
            if result.get("success"):
                self._update_agent_performance(winning_agent.agent_id, success=True)
                if group.circuit_breaker:
                    self._get_circuit_breaker(winning_agent.agent_id, circuit_strategy).record_success()
            else:
                self._update_agent_performance(winning_agent.agent_id, success=False)
                if group.circuit_breaker:
                    self._get_circuit_breaker(winning_agent.agent_id, circuit_strategy).record_failure()
            
            return {
                "success": result.get("success"),
                "mode": "dynamic_auction",
                "bids": bids,
                "winning_bid": winning_bid,
                "result": result,
                "auction_summary": f"{winning_bid['agent_name']} 以出价 {winning_bid['bid_score']:.3f} 中标"
            }
        
        except Exception as e:
            return {
                "success": False,
                "mode": "dynamic_auction",
                "error": str(e),
                "bids": bids,
                "winning_bid": winning_bid
            }
    
    async def _collect_bids(self, available_agents: List[Any], message: str, circuit_strategy: Optional[str]) -> List[Dict]:
        """收集Agent出价"""
        bids = []
        
        for agent in available_agents:
            # 检查熔断器
            cb = self.circuit_breakers.get(agent.agent_id)
            if cb and not cb.is_allowed():
                continue
            
            # 计算出价分数
            bid_score = self._calculate_bid(agent, message)
            
            if bid_score > 0:
                bids.append({
                    "agent_id": agent.agent_id,
                    "agent_name": agent.agent_name,
                    "bid_score": bid_score,
                    "priority": agent.priority,
                    "skills": [s.skill_id for s in agent.skills]
                })
        
        # 按出价排序
        bids.sort(key=lambda x: x["bid_score"], reverse=True)
        return bids
    
    def _calculate_bid(self, agent: Any, message: str) -> float:
        """计算Agent出价（综合评分）"""
        features = self._extract_task_features(message)
        agent_skills = [s.skill_id for s in agent.skills]
        
        score = 0.0
        
        # 技能匹配分（最多0.5分）
        skill_matches = sum(1 for skill in features["skill_keywords"] if skill in agent_skills)
        if features["skill_keywords"]:
            score += (skill_matches / len(features["skill_keywords"])) * 0.5
        
        # 优先级分（最多0.3分）
        score += agent.priority * 0.3
        
        # 负载分（最多0.2分）- 负载越低分数越高
        load_info = self.agent_load.get(agent.agent_id, AgentLoadInfo(agent_id=agent.agent_id))
        score += (1 - load_info.load_ratio) * 0.2
        
        # 成功率加成
        perf = self.agent_performance.get(agent.agent_id, {})
        success_rate = perf.get('success_rate', 1.0)
        score *= success_rate
        
        return round(score, 4)
    
    def _select_winning_bid(self, bids: List[Dict]) -> Dict:
        """选择获胜出价"""
        if not bids:
            return {}
        
        # 简单策略：选择分数最高的
        return bids[0]
    
    # ==========================================
    # 第三层：动态调度与熔断（通用方法）
    # ==========================================
    def _get_circuit_breaker(self, agent_id: str, strategy: Optional[str]) -> CircuitBreaker:
        """获取或创建熔断器"""
        if agent_id not in self.circuit_breakers:
            cb_strategy = CircuitBreakerStrategy(strategy or "count_based")
            self.circuit_breakers[agent_id] = CircuitBreaker(strategy=cb_strategy)
        return self.circuit_breakers[agent_id]
    
    async def _execute_with_agent(
        self,
        agent: Any,
        message: str,
        fail_strategy: FailureStrategy,
        circuit_breaker: bool,
        circuit_strategy: Optional[str],
        timeout: Optional[float]
    ) -> Dict[str, Any]:
        """执行单个Agent任务（带重试和超时处理）"""
        attempts = 0
        max_attempts = 3 if fail_strategy == FailureStrategy.RETRY else 1
        delay = 1.0
        
        while attempts < max_attempts:
            attempts += 1
            
            try:
                # 记录开始时间
                start_time = time.time()
                
                # 执行Agent
                result = await self._call_agent(agent, message, timeout)
                
                # 记录执行时间
                execution_time = time.time() - start_time
                self._update_execution_time(agent.agent_id, execution_time)
                
                return result
                
            except asyncio.TimeoutError:
                if attempts < max_attempts:
                    logger.info(f"Agent {agent.agent_name} 超时，重试 ({attempts}/{max_attempts})")
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    return {"success": False, "error": "任务超时"}
            except Exception as e:
                if attempts < max_attempts:
                    logger.info(f"Agent {agent.agent_name} 失败，重试 ({attempts}/{max_attempts}): {e}")
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    return {"success": False, "error": str(e)}
    
    async def _call_agent(self, agent: Any, message: str, timeout: Optional[float]) -> Dict[str, Any]:
        """调用Agent执行任务"""
        # 模拟执行（实际应该调用真正的Agent）
        await asyncio.sleep(random.uniform(0.5, 2.0))
        
        # 返回模拟结果
        return {
            "success": True,
            "agent_id": agent.agent_id,
            "agent_name": agent.agent_name,
            "results": [{
                "task_id": f"task_{int(time.time())}",
                "message": f"已处理任务: {message[:30]}...",
                "role": "assistant"
            }]
        }
    
    def _update_agent_performance(self, agent_id: str, success: bool):
        """更新Agent性能统计"""
        if agent_id not in self.agent_performance:
            self.agent_performance[agent_id] = {
                "total_tasks": 0,
                "success_count": 0,
                "success_rate": 1.0,
                "avg_execution_time": 0.0
            }
        
        perf = self.agent_performance[agent_id]
        perf["total_tasks"] += 1
        if success:
            perf["success_count"] += 1
        perf["success_rate"] = perf["success_count"] / perf["total_tasks"]
    
    def _update_execution_time(self, agent_id: str, execution_time: float):
        """更新Agent执行时间统计"""
        if agent_id not in self.agent_performance:
            self.agent_performance[agent_id] = {
                "total_tasks": 0,
                "success_count": 0,
                "success_rate": 1.0,
                "avg_execution_time": 0.0
            }
        
        perf = self.agent_performance[agent_id]
        current_avg = perf["avg_execution_time"]
        total_tasks = perf["total_tasks"]
        perf["avg_execution_time"] = (current_avg * (total_tasks - 1) + execution_time) / total_tasks


# ==========================================
# 全局实例
# ==========================================
agent_group_executor = AgentGroupExecutor()
