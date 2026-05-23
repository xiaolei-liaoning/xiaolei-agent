"""
能力匹配器 - 智能匹配Agent与任务

整合了 enhanced_agent_router 的资源评估功能：
- 任务复杂度评估
- 资源需求评估
- 增强型多维路由评分
- 学习能力：参考历史复盘结果
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from core.shared.enums import TaskComplexity, ResourceType
from core.multi_agent_v2.agents.base.base_agent import (
    BaseAgent, AgentType, Task, Capability
)
from core.multi_agent_v2.orchestration.context.global_context_center import (
    GlobalContextCenter
)

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



class CapabilityMatcher:
    """能力匹配器 - 智能匹配Agent与任务

    匹配算法考虑：
    1. 能力相关性（关键词匹配）
    2. 专业等级（任务难度 vs Agent能力）
    3. 当前负载（避免过载）
    4. 历史表现（成功率、执行时间）
    5. 协作偏好（是否适合团队协作）
    6. 可用性（是否在线、健康）
    7. 资源效率（CPU、内存、网络使用率）
    8. 复杂度匹配（任务复杂度 vs Agent专长）
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
        """匹配最适合执行任务的Agent列表"""
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
        """所有 Agent 统一为 WORKER，协作分数一致"""
        return 0.7

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
