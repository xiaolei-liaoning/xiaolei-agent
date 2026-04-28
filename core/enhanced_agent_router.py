"""增强版Agent路由器 - 任务复杂度 + 资源评估

核心功能：
- 任务复杂度评估
- 资源需求评估
- 增强型多维路由
- 动态权重调整
- 负载均衡

优势：
- 更精准的Agent选择
- 资源利用率优化
- 任务完成率提升
"""

import logging
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import re

logger = logging.getLogger(__name__)


class TaskComplexity(Enum):
    """任务复杂度等级"""
    SIMPLE = "simple"       # 简单任务（单步骤，低资源）
    MODERATE = "moderate" # 中等任务（多步骤，中等资源）
    COMPLEX = "complex"     # 复杂任务（多步骤，高资源）
    CRITICAL = "critical"   # 关键任务（高优先级，紧急处理）


class ResourceType(Enum):
    """资源类型"""
    CPU = "cpu"
    MEMORY = "memory"
    NETWORK = "network"
    STORAGE = "storage"
    API_QUOTA = "api_quota"


@dataclass
class TaskComplexityAssessment:
    """任务复杂度评估结果"""
    task_type: str
    complexity: TaskComplexity
    estimated_steps: int
    estimated_duration: float  # 预估耗时（秒）
    resource_requirements: Dict[ResourceType, float] = field(default_factory=dict)
    confidence: float = 0.0  # 评估置信度


@dataclass
class ResourceAvailability:
    """资源可用性"""
    resource_type: ResourceType
    available: float  # 可用量
    total: float  # 总量
    utilization_rate: float  # 利用率
    last_updated: float = field(default_factory=time.time)


@dataclass
class EnhancedAgentMetrics:
    """增强版Agent性能指标"""
    agent_type: str
    priority: float = 1.0              # 优先级权重 (0-1)
    health_score: float = 1.0          # 健康度 (0-1)
    avg_execution_time: float = 0.0    # 平均执行时间（秒）
    success_rate: float = 1.0          # 成功率 (0-1)
    total_tasks: int = 0               # 总任务数
    failed_tasks: int = 0              # 失败任务数
    last_active: float = 0.0           # 最后活跃时间戳
    
    # 新增：资源相关指标
    avg_cpu_usage: float = 0.0         # 平均CPU使用率
    avg_memory_usage: float = 0.0       # 平均内存使用率
    avg_network_usage: float = 0.0       # 平均网络使用率
    concurrent_capacity: int = 1         # 并发处理能力
    
    # 新增：复杂度相关指标
    simple_task_success_rate: float = 1.0   # 简单任务成功率
    moderate_task_success_rate: float = 1.0  # 中等任务成功率
    complex_task_success_rate: float = 1.0   # 复杂任务成功率
    
    def calculate_enhanced_routing_score(
        self, 
        task_complexity: TaskComplexity,
        resource_weights: Dict[str, float] = None
    ) -> float:
        """计算增强版路由评分
        
        Args:
            task_complexity: 任务复杂度
            resource_weights: 资源权重配置
            
        Returns:
            路由评分 (0-1)，越高越优先
        """
        # 默认权重配置
        if resource_weights is None:
            resource_weights = {
                "priority": 0.25,
                "health": 0.20,
                "time": 0.15,
                "success": 0.20,
                "complexity_match": 0.10,
                "resource_efficiency": 0.10
            }
        
        # 1. 基础评分（原有维度）
        max_acceptable_time = 60.0
        if self.avg_execution_time > 0:
            time_score = max(0, 1.0 - (self.avg_execution_time / max_acceptable_time))
        else:
            time_score = 1.0
        
        base_score = (
            self.priority * resource_weights["priority"] +
            self.health_score * resource_weights["health"] +
            time_score * resource_weights["time"] +
            self.success_rate * resource_weights["success"]
        )
        
        # 2. 复杂度匹配评分
        complexity_match_score = self._calculate_complexity_match(task_complexity)
        
        # 3. 资源效率评分
        resource_efficiency_score = self._calculate_resource_efficiency()
        
        # 4. 综合评分
        total_score = (
            base_score +
            complexity_match_score * resource_weights["complexity_match"] +
            resource_efficiency_score * resource_weights["resource_efficiency"]
        )
        
        return round(total_score, 4)
    
    def _calculate_complexity_match(self, task_complexity: TaskComplexity) -> float:
        """计算复杂度匹配分数
        
        Args:
            task_complexity: 任务复杂度
            
        Returns:
            匹配分数 (0-1)
        """
        # 根据任务复杂度选择对应的历史成功率
        if task_complexity == TaskComplexity.SIMPLE:
            success_rate = self.simple_task_success_rate
        elif task_complexity == TaskComplexity.MODERATE:
            success_rate = self.moderate_task_success_rate
        elif task_complexity == TaskComplexity.COMPLEX:
            success_rate = self.complex_task_success_rate
        else:  # CRITICAL
            success_rate = self.success_rate
        
        return success_rate
    
    def _calculate_resource_efficiency(self) -> float:
        """计算资源效率分数
        
        Returns:
            效率分数 (0-1)
        """
        # 综合考虑CPU、内存、网络使用率
        # 使用率越低，效率越高
        avg_usage = (
            self.avg_cpu_usage + 
            self.avg_memory_usage + 
            self.avg_network_usage
        ) / 3.0
        
        # 效率分数：使用率越低，分数越高
        efficiency = max(0, 1.0 - avg_usage)
        
        return efficiency


class EnhancedAgentRouter:
    """增强版Agent路由器"""
    
    def __init__(self):
        self.agent_metrics: Dict[str, EnhancedAgentMetrics] = {}
        self.resource_availability: Dict[ResourceType, ResourceAvailability] = {}
        self.task_complexity_cache: Dict[str, TaskComplexityAssessment] = {}
        
        # 权重配置
        self.routing_weights = {
            "priority": 0.25,
            "health": 0.20,
            "time": 0.15,
            "success": 0.20,
            "complexity_match": 0.10,
            "resource_efficiency": 0.10
        }
        
        logger.info("增强版Agent路由器初始化完成")
    
    def register_agent(self, agent_type: str, priority: float = 1.0, 
                    concurrent_capacity: int = 1):
        """注册Agent
        
        Args:
            agent_type: Agent类型
            priority: 优先级 (0-1)
            concurrent_capacity: 并发处理能力
        """
        if agent_type not in self.agent_metrics:
            self.agent_metrics[agent_type] = EnhancedAgentMetrics(
                agent_type=agent_type,
                priority=priority,
                concurrent_capacity=concurrent_capacity
            )
            logger.info("注册Agent: %s (priority=%.2f, capacity=%d)", 
                       agent_type, priority, concurrent_capacity)
    
    def assess_task_complexity(self, task: Dict[str, Any]) -> TaskComplexityAssessment:
        """评估任务复杂度
        
        Args:
            task: 任务信息
            
        Returns:
            复杂度评估结果
        """
        task_type = task.get("type", "")
        task_params = task.get("params", {})
        
        # 检查缓存
        cache_key = f"{task_type}_{str(task_params)}"
        if cache_key in self.task_complexity_cache:
            return self.task_complexity_cache[cache_key]
        
        # 基于任务类型和参数评估复杂度
        complexity, steps, duration, resources = self._analyze_task_characteristics(
            task_type, task_params
        )
        
        assessment = TaskComplexityAssessment(
            task_type=task_type,
            complexity=complexity,
            estimated_steps=steps,
            estimated_duration=duration,
            resource_requirements=resources,
            confidence=0.8  # 默认置信度
        )
        
        # 缓存结果
        self.task_complexity_cache[cache_key] = assessment
        
        logger.info(f"任务复杂度评估: {task_type} -> {complexity.value} "
                   f"(步骤={steps}, 耗时={duration:.1f}s)")
        
        return assessment
    
    def _analyze_task_characteristics(
        self, 
        task_type: str, 
        params: Dict[str, Any]
    ) -> Tuple[TaskComplexity, int, float, Dict[ResourceType, float]]:
        """分析任务特征
        
        Args:
            task_type: 任务类型
            params: 任务参数
            
        Returns:
            (复杂度, 步骤数, 预估耗时, 资源需求)
        """
        # 任务复杂度规则库
        complexity_rules = {
            # 简单任务
            "simple": {
                "types": ["check", "status", "ping"],
                "steps": 1,
                "duration": 2.0,
                "resources": {ResourceType.CPU: 0.1, ResourceType.NETWORK: 0.2}
            },
            # 中等任务
            "moderate": {
                "types": ["search", "scrape", "summarize"],
                "steps": 3,
                "duration": 10.0,
                "resources": {ResourceType.CPU: 0.3, ResourceType.NETWORK: 0.5, ResourceType.MEMORY: 0.2}
            },
            # 复杂任务
            "complex": {
                "types": ["analyze", "crawl", "extract"],
                "steps": 5,
                "duration": 30.0,
                "resources": {ResourceType.CPU: 0.5, ResourceType.NETWORK: 0.7, ResourceType.MEMORY: 0.4}
            },
            # 关键任务
            "critical": {
                "types": ["emergency", "urgent", "priority"],
                "steps": 2,
                "duration": 5.0,
                "resources": {ResourceType.CPU: 0.4, ResourceType.NETWORK: 0.3}
            }
        }
        
        # 匹配任务类型
        matched_complexity = TaskComplexity.MODERATE
        matched_rule = complexity_rules["moderate"]
        
        for complexity_name, rule in complexity_rules.items():
            if task_type in rule["types"] or any(
                keyword in task_type.lower() 
                for keyword in rule["types"]
            ):
                matched_complexity = TaskComplexity(complexity_name)
                matched_rule = rule
                break
        
        # 根据参数调整复杂度
        steps = matched_rule["steps"]
        duration = matched_rule["duration"]
        resources = matched_rule["resources"].copy()
        
        # 参数复杂度调整
        param_complexity = self._calculate_param_complexity(params)
        steps += param_complexity["extra_steps"]
        duration *= (1 + param_complexity["time_multiplier"])
        
        # 资源需求调整
        for resource_type, multiplier in param_complexity["resource_multipliers"].items():
            if resource_type in resources:
                resources[resource_type] *= multiplier
        
        return matched_complexity, steps, duration, resources
    
    def _calculate_param_complexity(self, params: Dict[str, Any]) -> Dict[str, float]:
        """计算参数复杂度
        
        Args:
            params: 任务参数
            
        Returns:
            复杂度调整因子
        """
        extra_steps = 0
        time_multiplier = 0.0
        resource_multipliers = {
            ResourceType.CPU: 1.0,
            ResourceType.MEMORY: 1.0,
            ResourceType.NETWORK: 1.0
        }
        
        # 分析参数特征
        for key, value in params.items():
            # 列表/数组参数增加复杂度
            if isinstance(value, (list, tuple)):
                extra_steps += len(value) // 5  # 每5个元素增加1步
                time_multiplier += len(value) * 0.1
                resource_multipliers[ResourceType.CPU] *= (1 + len(value) * 0.05)
            
            # 大文本参数增加复杂度
            elif isinstance(value, str) and len(value) > 1000:
                extra_steps += 1
                time_multiplier += 0.2
                resource_multipliers[ResourceType.MEMORY] *= 1.2
            
            # 嵌套字典参数增加复杂度
            elif isinstance(value, dict):
                nested_count = len(value)
                extra_steps += nested_count // 3
                time_multiplier += nested_count * 0.05
        
        return {
            "extra_steps": extra_steps,
            "time_multiplier": time_multiplier,
            "resource_multipliers": resource_multipliers
        }
    
    def update_resource_availability(self, resource_type: ResourceType, 
                                  available: float, total: float):
        """更新资源可用性
        
        Args:
            resource_type: 资源类型
            available: 可用量
            total: 总量
        """
        utilization_rate = 1.0 - (available / total) if total > 0 else 0.0
        
        self.resource_availability[resource_type] = ResourceAvailability(
            resource_type=resource_type,
            available=available,
            total=total,
            utilization_rate=utilization_rate
        )
        
        logger.debug(f"更新资源可用性: {resource_type.value} "
                    f"(可用={available:.1f}, 总量={total:.1f}, "
                    f"利用率={utilization_rate:.2f})")
    
    def select_best_agent_enhanced(
        self, 
        task: Dict[str, Any],
        candidate_agents: Optional[List[str]] = None
    ) -> Optional[str]:
        """选择最优Agent（增强版）
        
        Args:
            task: 任务信息
            candidate_agents: 候选Agent列表
            
        Returns:
            最优Agent类型
        """
        # 评估任务复杂度
        task_assessment = self.assess_task_complexity(task)
        task_complexity = task_assessment.complexity
        
        # 确定候选Agent
        if candidate_agents is None:
            candidates = list(self.agent_metrics.keys())
        else:
            candidates = [a for a in candidate_agents if a in self.agent_metrics]
        
        if not candidates:
            logger.warning("没有可用的候选Agent")
            return None
        
        # 计算每个候选Agent的增强评分
        scored_agents = []
        for agent_type in candidates:
            metrics = self.agent_metrics[agent_type]
            score = metrics.calculate_enhanced_routing_score(
                task_complexity,
                self.routing_weights
            )
            scored_agents.append((agent_type, score, metrics))
        
        # 按评分排序
        scored_agents.sort(key=lambda x: x[1], reverse=True)
        
        # 返回最高分的Agent
        best_agent = scored_agents[0][0]
        best_score = scored_agents[0][1]
        best_metrics = scored_agents[0][2]
        
        logger.info(f"选择Agent: {best_agent} (score={best_score:.4f}, "
                   f"task_complexity={task_complexity.value})")
        
        return best_agent
    
    def record_execution_enhanced(
        self, 
        agent_type: str, 
        execution_time: float, 
        success: bool,
        task_complexity: TaskComplexity,
        resource_usage: Dict[ResourceType, float] = None
    ):
        """记录执行结果（增强版）
        
        Args:
            agent_type: Agent类型
            execution_time: 执行时间
            success: 是否成功
            task_complexity: 任务复杂度
            resource_usage: 资源使用情况
        """
        if agent_type not in self.agent_metrics:
            return
        
        metrics = self.agent_metrics[agent_type]
        
        # 更新基础指标
        metrics.total_tasks += 1
        if not success:
            metrics.failed_tasks += 1
        metrics.success_rate = (
            (metrics.total_tasks - metrics.failed_tasks) / metrics.total_tasks
        )
        
        # 更新平均执行时间（移动平均）
        if metrics.avg_execution_time > 0:
            metrics.avg_execution_time = (
                metrics.avg_execution_time * 0.9 + execution_time * 0.1
            )
        else:
            metrics.avg_execution_time = execution_time
        
        # 更新复杂度相关成功率
        if task_complexity == TaskComplexity.SIMPLE:
            success_count = metrics.simple_task_success_rate * (metrics.total_tasks - 1)
            metrics.simple_task_success_rate = (success_count + (1 if success else 0)) / metrics.total_tasks
        elif task_complexity == TaskComplexity.MODERATE:
            success_count = metrics.moderate_task_success_rate * (metrics.total_tasks - 1)
            metrics.moderate_task_success_rate = (success_count + (1 if success else 0)) / metrics.total_tasks
        elif task_complexity == TaskComplexity.COMPLEX:
            success_count = metrics.complex_task_success_rate * (metrics.total_tasks - 1)
            metrics.complex_task_success_rate = (success_count + (1 if success else 0)) / metrics.total_tasks
        
        # 更新资源使用情况
        if resource_usage:
            for resource_type, usage in resource_usage.items():
                if resource_type == ResourceType.CPU:
                    metrics.avg_cpu_usage = (
                        metrics.avg_cpu_usage * 0.9 + usage * 0.1
                    )
                elif resource_type == ResourceType.MEMORY:
                    metrics.avg_memory_usage = (
                        metrics.avg_memory_usage * 0.9 + usage * 0.1
                    )
                elif resource_type == ResourceType.NETWORK:
                    metrics.avg_network_usage = (
                        metrics.avg_network_usage * 0.9 + usage * 0.1
                    )
        
        metrics.last_active = time.time()
        
        logger.debug(f"记录Agent执行: {agent_type} "
                    f"(time={execution_time:.2f}s, success={success}, "
                    f"complexity={task_complexity.value})")
    
    def update_routing_weights(self, weights: Dict[str, float]):
        """更新路由权重
        
        Args:
            weights: 新的权重配置
        """
        # 归一化权重
        total = sum(weights.values())
        self.routing_weights = {
            key: value / total 
            for key, value in weights.items()
        }
        
        logger.info(f"路由权重已更新: {self.routing_weights}")
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态
        
        Returns:
            系统状态信息
        """
        return {
            "agent_count": len(self.agent_metrics),
            "resource_status": {
                rt.value: {
                    "available": ra.available,
                    "total": ra.total,
                    "utilization_rate": ra.utilization_rate
                }
                for rt, ra in self.resource_availability.items()
            },
            "routing_weights": self.routing_weights.copy(),
            "agent_metrics": {
                agent_type: {
                    "priority": metrics.priority,
                    "health_score": metrics.health_score,
                    "success_rate": metrics.success_rate,
                    "avg_execution_time": metrics.avg_execution_time,
                    "concurrent_capacity": metrics.concurrent_capacity
                }
                for agent_type, metrics in self.agent_metrics.items()
            }
        }


# 全局增强路由器实例
_enhanced_router = None
_router_lock = None


def get_enhanced_agent_router() -> EnhancedAgentRouter:
    """获取增强版Agent路由器单例
    
    Returns:
        增强版Agent路由器实例
    """
    global _enhanced_router, _router_lock
    
    if _enhanced_router is None:
        import threading
        _router_lock = threading.Lock()
        
        with _router_lock:
            if _enhanced_router is None:
                _enhanced_router = EnhancedAgentRouter()
    
    return _enhanced_router