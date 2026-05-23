"""
评审协作策略 - 多Agent并行，结果通过评审达成共识

包含：
1. ReviewStrategy - 评审协作策略
2. ConsensusMechanism - 共识机制
"""

import asyncio
import logging
import time
from typing import Any, Dict, List

from core.multi_agent_v2.agents.base.base_agent import BaseAgent, Task
from core.multi_agent_v2.orchestration.context.global_context_center import TaskState

from .base import BaseCollaborationStrategy, CollaborationResult

logger = logging.getLogger(__name__)


class ReviewStrategy(BaseCollaborationStrategy):
    """评审协作策略 - 多Agent并行，结果通过评审达成共识"""

    async def execute(
        self,
        task: Task,
        agents: List[BaseAgent],
        execution_plan: List[Dict[str, Any]]
    ) -> CollaborationResult:
        """评审执行

        流程：
        1. 多个Worker Agent并行执行任务
        2. 各Worker提交结果
        3. 评审Agent对结果进行评审
        4. 如有分歧，进行多轮评审和讨论
        5. 达成共识后输出最终结果
        """
        start_time = time.time()
        worker_results = {}
        agent_results = {}

        # 分离Worker和Reviewer
        workers = []
        reviewers = []

        for plan in execution_plan:
            agent_id = plan.get("agent_id")
            role = plan.get("role", "worker")
            agent = next((a for a in agents if a.agent_id == agent_id), None)

            if not agent:
                continue

            if role == "reviewer" or plan.get("agent_type") == "reviewer":
                reviewers.append(agent)
            else:
                workers.append(agent)

        if not reviewers:
            logger.warning("未找到Reviewer，使用默认评审")
            reviewers = workers[:1] if workers else []
            workers = workers[1:] if len(workers) > 1 else workers

        logger.info(f"开始评审执行: {task.task_id}, Workers: {len(workers)}, Reviewers: {len(reviewers)}")

        # 更新任务状态
        await self.context_center.update_task_state(task.task_id, TaskState.RUNNING)

        # 第一轮：Worker并行执行
        subtasks = []
        for i, worker in enumerate(workers):
            subtask_id = f"{task.task_id}_work_{i}"

            subtasks.append(
                self._execute_agent_task(
                    worker,
                    subtask_id,
                    {
                        "type": "worker",
                        "description": f"执行评审任务 {i+1}",
                        "keywords": task.keywords,
                        "complexity": task.complexity
                    }
                )
            )

        # 等待Worker完成
        worker_task_results = await asyncio.gather(*subtasks, return_exceptions=True)

        # 收集Worker结果
        for result in worker_task_results:
            if isinstance(result, Exception):
                logger.error(f"Worker执行异常: {result}")
                continue

            subtask_id, action_result = result
            agent_results[subtask_id] = action_result

            if action_result.success:
                worker_results[subtask_id] = action_result.output

        logger.info(f"Worker执行完成，{len(worker_results)} 个成功")

        # 第二轮：评审
        review_results = await self._perform_review(reviewers, worker_results)

        # 第三轮：共识达成
        final_result = await self._reach_consensus(reviewers, worker_results, review_results)

        # 更新任务状态
        if final_result:
            await self.context_center.update_task_state(task.task_id, TaskState.COMPLETED)
        else:
            await self.context_center.update_task_state(task.task_id, TaskState.FAILED)

        execution_time = time.time() - start_time

        return CollaborationResult(
            task_id=task.task_id,
            success=final_result is not None,
            final_result=final_result,
            partial_results=worker_results,
            execution_time=execution_time,
            agent_results=agent_results
        )

    async def _perform_review(self, reviewers: List[BaseAgent], worker_results: Dict[str, Any]) -> Dict[str, Any]:
        """执行评审"""
        review_results = {}

        for i, reviewer in enumerate(reviewers):
            review_task = Task(
                task_id=f"review_{i}",
                type="review",
                description="评审执行结果",
                keywords=[],
                complexity=0.5
            )

            thought = await reviewer.think(review_task)

            # 评审逻辑（简化）
            review_result = {
                "approved": len(worker_results) > 0,
                "comments": f"评审 {i+1} 完成",
                "suggestions": []
            }

            review_results[f"reviewer_{i}"] = review_result

        return review_results

    async def _reach_consensus(
        self,
        reviewers: List[BaseAgent],
        worker_results: Dict[str, Any],
        review_results: Dict[str, Any]
    ) -> Any:
        """达成共识"""
        # 简单实现：多数评审通过即成功
        approved_count = sum(1 for r in review_results.values() if r.get("approved"))

        if approved_count >= len(reviewers) / 2:
            # 返回所有worker结果的综合
            successful = [r for r in worker_results.values() if r is not None]
            return {"consensus": True, "results": successful}

        return None


class ConsensusMechanism:
    """共识机制"""

    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold

    async def reach_consensus(
        self,
        agents: List[str],
        question: str,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """达成共识"""
        results = await self._collect_votes(agents, question, timeout)

        if not results:
            return {"success": False, "reason": "无响应"}

        # 统计投票
        vote_counts = {}
        for result in results:
            answer = result.get("answer")
            vote_counts[answer] = vote_counts.get(answer, 0) + 1

        # 检查是否达成共识
        total_votes = len(results)
        max_votes = max(vote_counts.values())
        consensus_ratio = max_votes / total_votes

        if consensus_ratio >= self.threshold:
            consensus_answer = max(vote_counts, key=vote_counts.get)
            return {
                "success": True,
                "consensus": consensus_answer,
                "confidence": consensus_ratio,
                "votes": vote_counts,
                "total_voters": total_votes
            }
        else:
            return {
                "success": False,
                "reason": "未达成共识",
                "votes": vote_counts,
                "consensus_ratio": consensus_ratio,
                "total_voters": total_votes
            }

    async def _collect_votes(self, agents: List[str], question: str, timeout: int) -> List[Dict]:
        """收集投票"""
        results = []

        async def vote(agent_id):
            try:
                await asyncio.sleep(1)  # 模拟投票延迟
                results.append({
                    "agent_id": agent_id,
                    "answer": self._simulate_answer(question)
                })
            except Exception as e:
                logger.error(f"Agent {agent_id} 投票失败: {e}")

        tasks = [vote(agent) for agent in agents]
        await asyncio.gather(*tasks)

        return results

    def _simulate_answer(self, question: str) -> str:
        """模拟回答"""
        if "是" in question or "否" in question:
            return "是" if hash(question) % 2 == 0 else "否"
        return "同意" if hash(question) % 3 == 0 else "反对"
