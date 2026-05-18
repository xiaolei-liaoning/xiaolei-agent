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
            
            # ★ 激活KEPA循环：应用学习
            if reflection:
                self._apply_reviewer_learning(reflection, review_result)

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
        """评审：LLM驱动，断线重连3次，全失败反问"""
        logger.info(f"开始评审任务: {task.description}")

        last_error = None
        for attempt in range(3):
            try:
                llm_result = await self._review_with_llm(task)
                if llm_result:
                    return llm_result
            except Exception as e:
                last_error = str(e)
                logger.warning(f"LLM评审失败(第{attempt+1}次): {e}")
                if attempt < 2:
                    await asyncio.sleep(1)
                    continue

        # 3次全失败 → 反问用户
        answer = await self.ask_user(
            f"LLM断线重连3次仍失败({str(last_error)[:60]})，是否使用模拟评审降级处理？",
            context=f"任务: {task.description[:80]}",
        )
        if answer == "retry":
            try:
                llm = await self._review_with_llm(task)
                if llm:
                    return llm
            except Exception:
                pass
        elif answer == "cancel":
            raise

        return await self._review_simulated(task)

    async def _review_with_llm(self, task: Task) -> Optional[ReviewResult]:
        """使用LLM进行智能评审"""
        from core.engine.llm_backend import get_llm_router
        from core.multi_agent_v2.agents.prompts.agent_prompts import get_prompt_manager
        
        llm_router = get_llm_router()
        prompt_manager = get_prompt_manager()
        
        if not llm_router.is_available():
            return None

        prompt = prompt_manager.get_prompt("reviewer")
        if not prompt:
            return None

        # 构建评审提示词
        task_prompt = prompt.task_prompt.format(
            task_description=task.description,
            task_result="待评审",
            execution_log=""
        )

        messages = [
            {"role": "system", "content": prompt.system_prompt},
            {"role": "user", "content": task_prompt}
        ]

        response = await llm_router.chat(messages, temperature=0.4, max_tokens=2000)
        
        # 解析LLM响应
        return self._parse_llm_review(response)

    def _parse_llm_review(self, response: str) -> ReviewResult:
        """解析LLM响应为评审结果"""
        # 提取关键信息
        score = 0.7
        approved = True
        comments = []
        issues = []
        suggestions = []
        
        lines = response.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 匹配评分
            if "评分" in line or "分数" in line:
                try:
                    score_str = ''.join([c for c in line if c.isdigit() or c == '.'])
                    score = min(float(score_str) / 100, 1.0)
                except (ValueError, TypeError):
                    pass
            # 匹配通过状态
            elif "通过" in line:
                approved = "通过" in line
            # 匹配问题
            elif "问题" in line or "错误" in line or "✗" in line:
                issues.append(line)
            # 匹配建议
            elif "建议" in line or "改进" in line:
                suggestions.append(line)
            # 其他作为评论
            else:
                comments.append(line)
        
        # 设置通过阈值
        approved = score >= 0.6
        
        # 如果没有提取到具体内容，使用默认值
        if not comments:
            comments = ["评审完成"]
        if not issues:
            issues = [] if approved else ["存在一些问题"]
        if not suggestions:
            suggestions = ["继续保持"] if approved else ["建议改进"]

        return ReviewResult(
            approved=approved,
            score=score,
            comments=comments[:5],
            issues=issues[:3],
            suggestions=suggestions[:3]
        )



    async def review_result(self, result: ActionResult) -> ReviewResult:
        """评审执行结果"""
        logger.info(f"评审执行结果: {result.success}")

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
    
    def _apply_reviewer_learning(self, reflection, review_result) -> None:
        """应用评审学习"""
        from datetime import datetime
        
        logger.info(f"[KEPA] ReviewerAgent 从反思中学习: {len(reflection.lessons_learned) if hasattr(reflection, 'lessons_learned') else 0} 条经验")
        
        # 可以根据评审结果调整评审标准
        if review_result.approved and hasattr(reflection, 'improvements') and reflection.improvements:
            # 如果批准但有改进建议，可以考虑
            pass
    
    def get_reviewer_effectiveness(self) -> Dict[str, Any]:
        """获取评审有效性统计"""
        if not self.review_history:
            return {"total_reviews": 0, "approval_rate": 0}
        
        approved = sum(1 for r in self.review_history if r.approved)
        total = len(self.review_history)
        
        return {
            "total_reviews": total,
            "approved": approved,
            "approval_rate": approved / total if total > 0 else 0,
            "avg_score": sum(r.score for r in self.review_history) / total if total > 0 else 0
        }