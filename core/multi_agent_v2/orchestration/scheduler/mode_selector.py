"""
协作模式选择器 - 智能选择Agent协作模式

选择优先级：
1. 关键词语义覆盖 — 任务描述中的语义线索强制指定模式
2. 历史经验（跨次学习）— 基于历史成功率选择
3. LLM智能选择 — 使用LLM分析任务特征
4. 启发式兜底规则
"""

import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from core.multi_agent_v2.agents.base.base_agent import Task, BaseAgent

logger = logging.getLogger(__name__)


class CollaborationMode(Enum):
    """协作模式"""
    PIPELINE = "pipeline"              # 流水线：顺序执行
    MASTER_SLAVE = "master_slave"    # 主从：主Agent分解+聚合
    REVIEW = "review"               # 评审：多Agent并行+评审
    AUCTION = "auction"             # 拍卖：任务竞标
    HYBRID = "hybrid"               # 混合模式


class ModeSelector:
    """协作模式选择器

    根据任务特征、历史经验、LLM分析等多维度选择最佳协作模式。
    选择优先级：关键词语义 > 历史经验 > LLM > 启发式兜底规则
    """

    PIPELINE_KEYWORDS = {
        "排序", "依次", "按步骤", "顺序执行", "逐步", "步骤",
        "流水线", "先后", "按顺序", "先处理", "再处理", "然后",
    }
    MASTER_SLAVE_KEYWORDS = {"分配", "委派", "派发", "主从", "分工", "协调", "指派"}
    REVIEW_KEYWORDS = {"评审", "审查", "复审", "审核", "质量", "验证"}
    AUCTION_KEYWORDS = {"竞标", "最优", "最佳", "比较", "择优", "选择"}

    # LLM选择返回的模式名称映射
    MODE_MAP = {
        "pipeline": CollaborationMode.PIPELINE,
        "master_slave": CollaborationMode.MASTER_SLAVE,
        "review": CollaborationMode.REVIEW,
        "auction": CollaborationMode.AUCTION,
        "hybrid": CollaborationMode.HYBRID,
    }

    def __init__(self):
        logger.info("协作模式选择器初始化完成")

    async def select(
        self,
        task: Task,
        analysis: Dict[str, Any],
        available_agents: Optional[List[BaseAgent]] = None,
        llm_facade: Optional[Any] = None,
        collaboration_history: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> CollaborationMode:
        """选择协作模式

        选择优先级：
        1. 关键词语义覆盖 — 检测任务描述中的语义线索
        2. 历史经验（跨次学习）— 历史成功率超过70%的模式
        3. LLM智能选择 — 使用LLM分析任务特征
        4. 启发式兜底规则 — 基于复杂度和步骤数

        Args:
            task: 待调度的任务
            analysis: 任务分析结果（来自TaskAnalyzer）
            available_agents: 可用Agent列表（供LLM选择使用）
            llm_facade: LLM门面（供LLM选择使用）
            collaboration_history: 历史协作模式成功率记录

        Returns:
            选择的协作模式
        """
        task_type = task.type or "general"
        complexity = analysis.get("complexity", 0.5)

        # ★ 1. 关键词语义覆盖（优先级最高）
        keyword_mode = self._keyword_semantic_override(task, complexity)
        if keyword_mode:
            return keyword_mode

        # ★ 2. 尝试从历史经验中选择（跨次学习）
        history_mode = self._history_based_select(task_type, collaboration_history or {})
        if history_mode:
            return history_mode

        # 3. 尝试 LLM 选择
        if llm_facade and available_agents:
            llm_mode = await self._llm_based_select(task, analysis, available_agents, llm_facade)
            if llm_mode:
                return llm_mode

        # 4. 兜底：简单启发式选择
        return self._fallback_select(analysis, task)

    def _keyword_semantic_override(
        self, task: Task, complexity: float
    ) -> Optional[CollaborationMode]:
        """关键词语义覆盖 — 检测任务描述中的语义线索强制指定协作模式

        即使复杂度不高，包含 pipeline 关键词（"排序""依次""按步骤"）也走流水线模式。

        Args:
            task: 待调度的任务
            complexity: 任务复杂度

        Returns:
            匹配到关键词时返回对应模式，否则返回 None
        """
        description_lower = task.description.lower()
        keywords_lower = [kw.lower() for kw in task.keywords]

        # 检测 pipeline 关键词 — 优先级最高
        for kw in self.PIPELINE_KEYWORDS:
            if kw in description_lower or any(kw in tk for tk in keywords_lower):
                logger.info(
                    f"[关键词语义] 检测到 pipeline 关键词 '{kw}'，"
                    f"强制使用 pipeline 模式 (复杂度: {complexity})"
                )
                return CollaborationMode.PIPELINE

        # 检测 review 关键词
        for kw in self.REVIEW_KEYWORDS:
            if kw in description_lower or any(kw in tk for tk in keywords_lower):
                logger.info(
                    f"[关键词语义] 检测到 review 关键词 '{kw}'，强制使用 review 模式"
                )
                return CollaborationMode.REVIEW

        # 检测 master_slave 关键词
        for kw in self.MASTER_SLAVE_KEYWORDS:
            if kw in description_lower or any(kw in tk for tk in keywords_lower):
                logger.info(
                    f"[关键词语义] 检测到 master_slave 关键词 '{kw}'，"
                    f"强制使用 master_slave 模式"
                )
                return CollaborationMode.MASTER_SLAVE

        # 检测 auction 关键词
        for kw in self.AUCTION_KEYWORDS:
            if kw in description_lower or any(kw in tk for tk in keywords_lower):
                logger.info(
                    f"[关键词语义] 检测到 auction 关键词 '{kw}'，强制使用 auction 模式"
                )
                return CollaborationMode.AUCTION

        return None

    def _history_based_select(
        self,
        task_type: str,
        collaboration_history: Dict[str, Dict[str, float]],
    ) -> Optional[CollaborationMode]:
        """基于历史经验选择协作模式（跨次学习）

        如果历史中该任务类型有成功率超过70%的协作模式，则选择该模式。

        Args:
            task_type: 任务类型
            collaboration_history: 历史协作模式成功率记录 {task_type: {mode: success_rate}}

        Returns:
            历史最优模式，或 None
        """
        if task_type not in collaboration_history:
            return None

        mode_stats = collaboration_history[task_type]
        if not mode_stats:
            return None

        # 选择成功率最高的模式
        best_mode = max(mode_stats.items(), key=lambda x: x[1])
        if best_mode[1] > 0.7:  # 只有历史成功率超过70%才考虑
            try:
                mode = CollaborationMode(best_mode[0])
                logger.info(
                    f"[跨次学习] 选择历史最优模式: {mode.value}, "
                    f"成功率: {best_mode[1]:.2%}"
                )
                return mode
            except Exception:
                pass

        return None

    async def _llm_based_select(
        self,
        task: Task,
        analysis: Dict[str, Any],
        available_agents: List[BaseAgent],
        llm_facade: Any,
    ) -> Optional[CollaborationMode]:
        """使用LLM选择协作模式

        Args:
            task: 待调度的任务
            analysis: 任务分析结果
            available_agents: 可用Agent列表
            llm_facade: LLM门面

        Returns:
            LLM选择的模式，或 None
        """
        try:
            from core.multi_agent_v2.orchestration.collaboration.strategies import (
                select_strategy_with_llm
            )

            mode_str, params = await select_strategy_with_llm(
                task_description=task.description,
                task_keywords=task.keywords,
                estimated_steps=analysis.get("estimated_steps", 3),
                complexity=analysis.get("complexity", 0.5),
                available_agents=available_agents,
                llm_router=llm_facade,
            )
            selected = self.MODE_MAP.get(mode_str)
            if selected:
                logger.info(f"LLM策略选择: {selected.value}, params: {params}")
                return selected
        except Exception as e:
            logger.debug(f"LLM策略选择失败，使用兜底规则: {e}")

        return None

    def _fallback_select(self, analysis: Dict[str, Any], task: Task) -> CollaborationMode:
        """兜底选择 — 简单启发式规则

        当关键词语义和历史经验都未命中时使用。

        Args:
            analysis: 任务分析结果
            task: 待调度的任务

        Returns:
            启发式规则选择的模式
        """
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
