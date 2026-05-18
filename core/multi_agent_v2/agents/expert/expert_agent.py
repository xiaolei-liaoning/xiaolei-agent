"""
ExpertAgent - 专家Agent

提供领域知识支持
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

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
class ExpertKnowledge:
    """专家知识条目"""
    domain: str
    topic: str
    content: str
    source: Optional[str] = None
    confidence: float = 0.9
    last_updated: str = ""


class ExpertAgent(BaseAgent):
    """ExpertAgent - 提供领域知识支持"""

    def __init__(
        self,
        domain: str = "general",
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        description: str = "专家Agent，提供领域知识支持"
    ):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.EXPERT,
            name=name or f"Expert-{domain}",
            description=description
        )

        self.domain = domain

        # 知识库
        self.knowledge_base: Dict[str, List[ExpertKnowledge]] = {}

        # 定义ExpertAgent的能力
        self.capabilities = self._initialize_capabilities()

        logger.info(f"ExpertAgent初始化完成: {self.agent_id} (领域: {self.domain})")

    def _initialize_capabilities(self) -> List[Capability]:
        """初始化能力"""
        return [
            Capability(
                name="domain_knowledge",
                description=f"{self.domain}领域知识",
                keywords=[self.domain, "知识", "咨询", "专家"],
                expertise_level=0.9,
                max_concurrent_tasks=5,
                avg_execution_time=3.0,
                success_rate=0.95
            ),
            Capability(
                name="problem_analysis",
                description="问题分析能力",
                keywords=["分析", "诊断", "问题", "原因"],
                expertise_level=0.85,
                max_concurrent_tasks=3,
                avg_execution_time=5.0,
                success_rate=0.9
            ),
            Capability(
                name="solution_proposal",
                description="解决方案生成能力",
                keywords=["方案", "建议", "解决", "优化"],
                expertise_level=0.8,
                max_concurrent_tasks=3,
                avg_execution_time=4.0,
                success_rate=0.88
            )
        ]

    async def execute(self, task: Task) -> ActionResult:
        """执行专家任务"""
        logger.info(f"ExpertAgent开始执行任务: {task.task_id}")

        try:
            # 1. 思考
            thought = await self.think(task)
            logger.info(f"思考完成: {thought.reasoning}")

            # 2. 提供专家知识
            result = await self._provide_expertise(task)

            # 3. 反思
            reflection = await self.reflect(
                ActionResult(
                    success=result.get("success", True),
                    output=result
                )
            )

            # ★ 激活：存储学习结果
            self._update_knowledge_from_reflection(reflection)

            return ActionResult(
                success=result.get("success", True),
                output=result,
                execution_time=result.get("execution_time", 3.0)
            )

        except Exception as e:
            logger.error(f"ExpertAgent执行失败: {e}")
            return ActionResult(
                success=False,
                error=str(e)
            )

    async def _provide_expertise(self, task: Task) -> Dict[str, Any]:
        """提供专家知识"""
        logger.info(f"提供{self.domain}领域专家知识: {task.description}")

        # 先查询知识库
        from_kb = self._query_knowledge_base(task.description)
        if from_kb:
            return {
                "type": "expertise",
                "source": "knowledge_base",
                "content": from_kb,
                "status": "success"
            }

        # 使用LLM获取专家知识
        try:
            llm_result = await self._get_expertise_with_llm(task)
            if llm_result:
                # 存储到知识库
                self._add_to_knowledge_base(task.description, llm_result)
                return llm_result
        except Exception as e:
            logger.warning(f"LLM获取专家知识失败: {e}")

        # 降级方案
        return self._simulate_expertise(task)

    async def _get_expertise_with_llm(self, task: Task) -> Optional[Dict[str, Any]]:
        """使用LLM获取专家知识"""
        from core.engine.llm_backend import get_llm_router
        from core.multi_agent_v2.agents.prompts.agent_prompts import get_prompt_manager

        llm_router = get_llm_router()
        prompt_manager = get_prompt_manager()

        if not llm_router.is_available():
            return None

        messages = [
            {"role": "system", "content": f"你是{self.domain}领域的专家，请提供专业、准确的知识和建议。"},
            {"role": "user", "content": f"请解答以下问题并提供详细的解释：{task.description}"}
        ]

        response = await llm_router.chat(messages, temperature=0.3, max_tokens=2000)

        return {
            "type": "expertise",
            "source": "llm",
            "content": response,
            "status": "success"
        }

    def _query_knowledge_base(self, query: str) -> Optional[str]:
        """查询知识库"""
        query_lower = query.lower()

        for topic, entries in self.knowledge_base.items():
            if topic.lower() in query_lower or query_lower in topic.lower():
                # 返回最新、最高置信度的知识
                sorted_entries = sorted(entries, key=lambda x: (x.last_updated, x.confidence), reverse=True)
                if sorted_entries:
                    return sorted_entries[0].content

        return None

    def _add_to_knowledge_base(self, topic: str, content: Dict[str, Any]) -> None:
        """添加知识到知识库"""
        from datetime import datetime

        if topic not in self.knowledge_base:
            self.knowledge_base[topic] = []

        knowledge = ExpertKnowledge(
            domain=self.domain,
            topic=topic,
            content=content.get("content", ""),
            confidence=0.8,
            last_updated=datetime.now().isoformat()
        )

        self.knowledge_base[topic].append(knowledge)
        logger.info(f"知识库已更新: {topic}")

    def _simulate_expertise(self, task: Task) -> Dict[str, Any]:
        """模拟专家知识"""
        return {
            "type": "expertise",
            "source": "simulated",
            "content": f"关于'{task.description}'的{self.domain}领域知识正在整理中...",
            "status": "partial"
        }

    def _update_knowledge_from_reflection(self, reflection) -> None:
        """从反思结果更新知识库"""
        if hasattr(reflection, 'lessons_learned') and reflection.lessons_learned:
            from datetime import datetime
            for lesson in reflection.lessons_learned:
                self._add_to_knowledge_base(
                    f"lesson-{len(self.knowledge_base)}",
                    {"content": lesson}
                )

    def get_knowledge_statistics(self) -> Dict[str, Any]:
        """获取知识库统计"""
        total_topics = len(self.knowledge_base)
        total_entries = sum(len(entries) for entries in self.knowledge_base.values())

        return {
            "domain": self.domain,
            "total_topics": total_topics,
            "total_entries": total_entries,
            "topics": list(self.knowledge_base.keys())[:10]
        }
