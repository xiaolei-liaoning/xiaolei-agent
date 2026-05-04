"""
ReviewerAgent - 评审Agent

负责质量把关、结果评审
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

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
class ReviewResult:
    """评审结果"""
    approved: bool
    score: float
    comments: List[str]
    issues: List[str]
    suggestions: List[str]


class ReviewerAgent(BaseAgent):
    """ReviewerAgent - 负责质量把关和结果评审"""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        description: str = "评审Agent，负责质量把关和结果评审",
        review_criteria: Optional[List[str]] = None
    ):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.REVIEWER,
            name=name,
            description=description
        )

        self.review_criteria = review_criteria or [
            "准确性",
            "完整性",
            "一致性",
            "可读性",
            "性能"
        ]

        # 定义ReviewerAgent的能力
        self.capabilities = [
            Capability(
                name="quality_review",
                description="质量评审能力",
                keywords=["评审", "审查", "质量", "把关"],
                expertise_level=0.9,
                max_concurrent_tasks=3,
                avg_execution_time=5.0,
                success_rate=0.95
            ),
            Capability(
                name="error_detection",
                description="错误检测能力",
                keywords=["检测", "错误", "问题", "bug"],
                expertise_level=0.85,
                max_concurrent_tasks=5,
                avg_execution_time=3.0,
                success_rate=0.9
            ),
            Capability(
                name="suggestion_generation",
                description="建议生成能力",
                keywords=["建议", "改进", "优化"],
                expertise_level=0.8,
                max_concurrent_tasks=3,
                avg_execution_time=4.0,
                success_rate=0.88
            )
        ]

        # 评审历史
        self.review_history: List[ReviewResult] = []

        logger.info(f"ReviewerAgent初始化完成: {self.agent_id}")

    async def execute(self, task: Task) -> ActionResult:
        """执行评审任务"""
        logger.info(f"ReviewerAgent开始执行任务: {task.task_id}")

        try:
            # 1. 思考
            thought = await self.think(task)
            logger.info(f"思考完成: {thought.reasoning}")

            # 2. 执行评审
            review_result = await self._review(task)

            # 3. 反思
            reflection = await self.reflect(
                ActionResult(
                    success=review_result.approved,
                    output=review_result
                )
            )

            # 记录评审历史
            self.review_history.append(review_result)

            return ActionResult(
                success=review_result.approved,
                output=review_result,
                execution_time=5.0
            )

        except Exception as e:
            logger.error(f"ReviewerAgent执行失败: {e}")
            return ActionResult(
                success=False,
                error=str(e)
            )

    async def _review(self, task: Task) -> ReviewResult:
        """执行评审"""
        logger.info(f"开始评审任务: {task.description}")

        # 模拟评审过程
        await asyncio.sleep(1.0)

        # 根据任务内容生成评审结果
        comments = []
        issues = []
        suggestions = []

        # 检查各个标准
        for criterion in self.review_criteria:
            # 模拟检查
            check_result = await self._check_criterion(task, criterion)

            if check_result["passed"]:
                comments.append(f"✓ {criterion}: 通过")
            else:
                comments.append(f"✗ {criterion}: 未通过")
                issues.append(f"{criterion}存在问题")
                suggestions.append(f"建议改进{criterion}")

        # 计算评分
        passed_count = sum(1 for c in comments if "✓" in c)
        score = passed_count / len(self.review_criteria)

        # 决定是否通过
        approved = score >= 0.6

        return ReviewResult(
            approved=approved,
            score=score,
            comments=comments,
            issues=issues,
            suggestions=suggestions
        )

    async def _check_criterion(self, task: Task, criterion: str) -> Dict[str, Any]:
        """检查单个标准"""
        # 模拟检查逻辑
        # 实际应该根据任务内容进行真实检查

        # 简单模拟：随机通过
        import random
        passed = random.random() > 0.3

        return {
            "criterion": criterion,
            "passed": passed,
            "details": f"检查{criterion}的结果"
        }

    async def review_result(self, result: ActionResult) -> ReviewResult:
        """评审执行结果"""
        logger.info(f"评审执行结果: {result.success}")

        # 模拟评审
        await asyncio.sleep(0.5)

        comments = []
        issues = []
        suggestions = []

        if result.success:
            comments.append("✓ 执行成功")
            score = 0.8
        else:
            comments.append("✗ 执行失败")
            issues.append(f"错误: {result.error}")
            suggestions.append("建议检查错误原因")
            score = 0.3

        return ReviewResult(
            approved=result.success,
            score=score,
            comments=comments,
            issues=issues,
            suggestions=suggestions
        )

    def get_review_history(self, limit: int = 100) -> List[ReviewResult]:
        """获取评审历史"""
        return self.review_history[-limit:]

    def get_review_statistics(self) -> Dict[str, Any]:
        """获取评审统计"""
        if not self.review_history:
            return {
                "total_reviews": 0,
                "approved_count": 0,
                "rejected_count": 0,
                "approval_rate": 0.0,
                "avg_score": 0.0
            }

        total = len(self.review_history)
        approved = sum(1 for r in self.review_history if r.approved)
        rejected = total - approved
        avg_score = sum(r.score for r in self.review_history) / total

        return {
            "total_reviews": total,
            "approved_count": approved,
            "rejected_count": rejected,
            "approval_rate": approved / total,
            "avg_score": avg_score
        }

    def set_review_criteria(self, criteria: List[str]) -> None:
        """设置评审标准"""
        self.review_criteria = criteria
        logger.info(f"评审标准已更新: {criteria}")
