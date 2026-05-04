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


class CapabilityMatcher:
    """能力匹配器"""

    def __init__(self, strategy: MatchStrategy = MatchStrategy.HYBRID):
        self.strategy = strategy
        self.match_history: List[Dict[str, Any]] = []
        self._weights = {
            "capability": 0.35,
            "expertise": 0.25,
            "load": 0.20,
            "performance": 0.15,
            "compatibility": 0.05
        }
        logger.info(f"能力匹配器初始化完成 (strategy={strategy.value})")

    def set_weights(self, **kwargs) -> None:
        """设置权重"""
        for key, value in kwargs.items():
            if key in self._weights:
                self._weights[key] = value
                logger.info(f"权重更新: {key}={value}")

    async def match(
        self,
        task: TaskRequirement,
        agents: List[AgentCapability],
        top_k: int = 3
    ) -> List[MatchScore]:
        """匹配任务与Agent

        Args:
            task: 任务需求
            agents: 候选Agent列表
            top_k: 返回前k个匹配结果

        Returns:
            匹配分数列表（按分数降序）
        """
        logger.info(f"开始匹配任务 {task.task_id}，候选Agent数量: {len(agents)}")

        scores = []

        for agent in agents:
            score = await self._calculate_match_score(task, agent)
            if score.total_score > 0:
                scores.append(score)

        # 按分数降序排序
        scores.sort(reverse=True)

        # 返回前k个
        result = scores[:top_k]

        # 记录匹配历史
        self._record_match(task, result)

        logger.info(f"匹配完成，返回前{len(result)}个Agent")
        return result

    async def _calculate_match_score(
        self,
        task: TaskRequirement,
        agent: AgentCapability
    ) -> MatchScore:
        """计算匹配分数"""

        # 1. 能力匹配分数
        capability_score = await self._calculate_capability_score(task, agent)

        # 2. 专业等级分数
        expertise_score = await self._calculate_expertise_score(task, agent)

        # 3. 负载分数
        load_score = await self._calculate_load_score(task, agent)

        # 4. 性能分数
        performance_score = await self._calculate_performance_score(task, agent)

        # 5. 兼容性分数
        compatibility_score = await self._calculate_compatibility_score(task, agent)

        # 计算总分
        total_score = (
            capability_score * self._weights["capability"] +
            expertise_score * self._weights["expertise"] +
            load_score * self._weights["load"] +
            performance_score * self._weights["performance"] +
            compatibility_score * self._weights["compatibility"]
        )

        return MatchScore(
            agent_id=agent.agent_id,
            agent_type=agent.agent_type,
            total_score=total_score,
            capability_score=capability_score,
            expertise_score=expertise_score,
            load_score=load_score,
            performance_score=performance_score,
            compatibility_score=compatibility_score,
            match_details={
                "strategy": self.strategy.value,
                "matched_capabilities": self._get_matched_capabilities(task, agent)
            }
        )

    async def _calculate_capability_score(
        self,
        task: TaskRequirement,
        agent: AgentCapability
    ) -> float:
        """计算能力匹配分数"""
        if not task.required_capabilities:
            return 1.0

        matched = sum(1 for cap in task.required_capabilities if cap in agent.capabilities)
        score = matched / len(task.required_capabilities)

        # 关键词匹配加分
        keyword_matches = sum(1 for kw in task.keywords if kw in agent.capabilities)
        if keyword_matches > 0:
            score += (keyword_matches / len(task.keywords)) * 0.2

        return min(score, 1.0)

    async def _calculate_expertise_score(
        self,
        task: TaskRequirement,
        agent: AgentCapability
    ) -> float:
        """计算专业等级分数"""
        # 基础分数：Agent的专业等级
        base_score = agent.expertise_level

        # 任务复杂度调整
        if task.complexity > 0.7:
            # 高复杂度任务，需要更高的专业等级
            if agent.expertise_level >= 0.8:
                base_score *= 1.1
            else:
                base_score *= 0.8
        elif task.complexity < 0.3:
            # 低复杂度任务，专业等级要求较低
            base_score *= 1.0

        return min(base_score, 1.0)

    async def _calculate_load_score(
        self,
        task: TaskRequirement,
        agent: AgentCapability
    ) -> float:
        """计算负载分数"""
        if agent.max_load == 0:
            return 0.0

        load_ratio = agent.current_load / agent.max_load

        # 负载越低，分数越高
        if load_ratio < 0.3:
            return 1.0
        elif load_ratio < 0.5:
            return 0.8
        elif load_ratio < 0.7:
            return 0.6
        elif load_ratio < 0.9:
            return 0.4
        else:
            return 0.2

    async def _calculate_performance_score(
        self,
        task: TaskRequirement,
        agent: AgentCapability
    ) -> float:
        """计算性能分数"""
        # 成功率权重
        success_score = agent.success_rate

        # 执行时间权重（越快越好）
        if agent.avg_execution_time > 0:
            time_score = max(0, 1.0 - (agent.avg_execution_time / 60.0))
        else:
            time_score = 1.0

        # 综合分数
        performance_score = (success_score * 0.7 + time_score * 0.3)

        return performance_score

    async def _calculate_compatibility_score(
        self,
        task: TaskRequirement,
        agent: AgentCapability
    ) -> float:
        """计算兼容性分数"""
        # 工具兼容性
        if task.preferred_tools:
            tool_matches = sum(1 for tool in task.preferred_tools if tool in agent.available_tools)
            tool_score = tool_matches / len(task.preferred_tools)
        else:
            tool_score = 1.0

        # 协作模式兼容性
        if task.collaboration_mode:
            # 这里可以根据Agent类型和协作模式计算兼容性
            collaboration_score = 1.0
        else:
            collaboration_score = 1.0

        return (tool_score + collaboration_score) / 2

    def _get_matched_capabilities(
        self,
        task: TaskRequirement,
        agent: AgentCapability
    ) -> List[str]:
        """获取匹配的能力"""
        matched = []
        for cap in task.required_capabilities:
            if cap in agent.capabilities:
                matched.append(cap)
        return matched

    def _record_match(self, task: TaskRequirement, scores: List[MatchScore]) -> None:
        """记录匹配历史"""
        self.match_history.append({
            "task_id": task.task_id,
            "task_type": task.task_type,
            "timestamp": time.time(),
            "matched_agents": [s.agent_id for s in scores],
            "top_score": scores[0].total_score if scores else 0.0
        })

        # 限制历史记录大小
        if len(self.match_history) > 1000:
            self.match_history = self.match_history[-1000:]

    def get_match_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取匹配历史"""
        return self.match_history[-limit:]

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self.match_history:
            return {
                "total_matches": 0,
                "avg_top_score": 0.0,
                "most_matched_agent": None
            }

        total_matches = len(self.match_history)
        avg_top_score = sum(h["top_score"] for h in self.match_history) / total_matches

        # 统计最常被匹配的Agent
        agent_counts = {}
        for history in self.match_history:
            for agent_id in history["matched_agents"]:
                agent_counts[agent_id] = agent_counts.get(agent_id, 0) + 1

        most_matched_agent = max(agent_counts.items(), key=lambda x: x[1])[0] if agent_counts else None

        return {
            "total_matches": total_matches,
            "avg_top_score": avg_top_score,
            "most_matched_agent": most_matched_agent,
            "agent_match_counts": agent_counts
        }


# 全局能力匹配器实例
_capability_matcher: Optional[CapabilityMatcher] = None


def get_capability_matcher(strategy: MatchStrategy = MatchStrategy.HYBRID) -> CapabilityMatcher:
    """获取能力匹配器实例"""
    global _capability_matcher
    if _capability_matcher is None:
        _capability_matcher = CapabilityMatcher(strategy=strategy)
    return _capability_matcher
