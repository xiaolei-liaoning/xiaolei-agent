"""
ExpertAgent - 专家Agent

负责领域知识、专业建议
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
class ExpertAdvice:
    """专家建议"""
    domain: str
    advice: str
    confidence: float
    references: List[str]
    alternatives: List[str]


class ExpertAgent(BaseAgent):
    """ExpertAgent - 负责领域知识和专业建议"""

    def __init__(
        self,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        description: str = "专家Agent，负责领域知识和专业建议",
        domain: Optional[str] = None
    ):
        super().__init__(
            agent_id=agent_id,
            agent_type=AgentType.EXPERT,
            name=name,
            description=description
        )

        self.domain = domain or "general"

        # 定义ExpertAgent的能力
        self.capabilities = self._initialize_capabilities()

        # 知识库
        self.knowledge_base: Dict[str, Any] = {}

        # 建议历史
        self.advice_history: List[ExpertAdvice] = []

        logger.info(f"ExpertAgent初始化完成: {self.agent_id} (domain={self.domain})")

    def _initialize_capabilities(self) -> List[Capability]:
        """初始化能力"""
        capabilities = []

        if self.domain == "security":
            capabilities = [
                Capability(
                    name="security_analysis",
                    description="安全分析能力",
                    keywords=["安全", "漏洞", "风险", "防护"],
                    expertise_level=0.95,
                    max_concurrent_tasks=2,
                    avg_execution_time=15.0,
                    success_rate=0.92
                ),
                Capability(
                    name="threat_detection",
                    description="威胁检测能力",
                    keywords=["威胁", "检测", "攻击"],
                    expertise_level=0.9,
                    max_concurrent_tasks=3,
                    avg_execution_time=10.0,
                    success_rate=0.9
                )
            ]
        elif self.domain == "performance":
            capabilities = [
                Capability(
                    name="performance_optimization",
                    description="性能优化能力",
                    keywords=["性能", "优化", "加速"],
                    expertise_level=0.9,
                    max_concurrent_tasks=2,
                    avg_execution_time=20.0,
                    success_rate=0.88
                ),
                Capability(
                    name="bottleneck_analysis",
                    description="瓶颈分析能力",
                    keywords=["瓶颈", "分析", "问题"],
                    expertise_level=0.85,
                    max_concurrent_tasks=3,
                    avg_execution_time=15.0,
                    success_rate=0.85
                )
            ]
        elif self.domain == "architecture":
            capabilities = [
                Capability(
                    name="architecture_design",
                    description="架构设计能力",
                    keywords=["架构", "设计", "规划"],
                    expertise_level=0.9,
                    max_concurrent_tasks=1,
                    avg_execution_time=30.0,
                    success_rate=0.9
                ),
                Capability(
                    name="pattern_recommendation",
                    description="模式推荐能力",
                    keywords=["模式", "推荐", "最佳实践"],
                    expertise_level=0.85,
                    max_concurrent_tasks=3,
                    avg_execution_time=10.0,
                    success_rate=0.88
                )
            ]
        else:
            # 通用专家能力
            capabilities = [
                Capability(
                    name="expert_consultation",
                    description="专家咨询能力",
                    keywords=["咨询", "建议", "专家"],
                    expertise_level=0.8,
                    max_concurrent_tasks=3,
                    avg_execution_time=10.0,
                    success_rate=0.85
                ),
                Capability(
                    name="knowledge_retrieval",
                    description="知识检索能力",
                    keywords=["知识", "检索", "查询"],
                    expertise_level=0.85,
                    max_concurrent_tasks=5,
                    avg_execution_time=5.0,
                    success_rate=0.9
                )
            ]

        return capabilities

    async def execute(self, task: Task) -> ActionResult:
        """执行专家咨询任务"""
        logger.info(f"ExpertAgent开始执行任务: {task.task_id}")

        try:
            # 1. 思考
            thought = await self.think(task)
            logger.info(f"思考完成: {thought.reasoning}")

            # 2. 提供专家建议
            advice = await self._provide_advice(task)

            # 3. 反思
            reflection = await self.reflect(
                ActionResult(
                    success=True,
                    output=advice
                )
            )

            # 记录建议历史
            self.advice_history.append(advice)

            return ActionResult(
                success=True,
                output=advice,
                execution_time=5.0
            )

        except Exception as e:
            logger.error(f"ExpertAgent执行失败: {e}")
            return ActionResult(
                success=False,
                error=str(e)
            )

    async def _provide_advice(self, task: Task) -> ExpertAdvice:
        """提供专家建议（使用LLM进行智能建议生成）"""
        logger.info(f"提供专家建议: {task.description}")

        # 先尝试使用LLM生成专家建议
        try:
            llm_advice = await self._provide_advice_with_llm(task)
            if llm_advice:
                return llm_advice
        except Exception as e:
            logger.warning(f"LLM专家建议生成失败，使用默认建议: {e}")

        # 降级到模拟建议
        return await self._provide_advice_simulated(task)

    async def _provide_advice_with_llm(self, task: Task) -> Optional[ExpertAdvice]:
        """使用LLM生成专家建议"""
        from core.llm_backend import get_llm_router
        from core.multi_agent_v2.agents.prompts.agent_prompts import get_prompt_manager
        
        llm_router = get_llm_router()
        prompt_manager = get_prompt_manager()
        
        if not llm_router.is_available():
            return None

        prompt = prompt_manager.get_prompt("expert")
        if not prompt:
            return None

        # 构建专家建议提示词
        system_prompt = prompt.system_prompt.format(
            domain=self.domain,
            capabilities=", ".join([c.name for c in self.capabilities])
        )

        task_prompt = prompt.task_prompt.format(
            problem_description=task.description,
            context=f"领域: {self.domain}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task_prompt}
        ]

        response = await llm_router.chat(messages, temperature=0.5, max_tokens=2000)
        
        # 解析LLM响应
        return self._parse_llm_advice(response)

    def _parse_llm_advice(self, response: str) -> ExpertAdvice:
        """解析LLM响应为专家建议"""
        # 提取建议内容
        advice_text = response
        
        # 尝试提取结构化信息
        references = []
        alternatives = []
        
        lines = response.split('\n')
        for line in lines:
            line = line.strip()
            if "参考" in line or "文献" in line or "资料" in line:
                refs = [r.strip() for r in line.split('：')[-1].split('、') if r.strip()]
                references.extend(refs)
            elif "替代" in line or "其他" in line:
                alts = [a.strip() for a in line.split('：')[-1].split('、') if a.strip()]
                alternatives.extend(alts)
        
        # 如果没有提取到，使用默认值
        if not references:
            references = ["领域知识", "最佳实践"]
        if not alternatives:
            alternatives = ["其他方案A", "其他方案B"]

        return ExpertAdvice(
            domain=self.domain,
            advice=advice_text,
            confidence=min(0.7 + len(response) / 3000, 0.95),
            references=references[:3],
            alternatives=alternatives[:3]
        )

    async def _provide_advice_simulated(self, task: Task) -> ExpertAdvice:
        """模拟专家建议生成（降级方案）"""
        await asyncio.sleep(1.0)

        if self.domain == "security":
            advice = ExpertAdvice(
                domain="security",
                advice="建议进行安全审计，检查常见漏洞如SQL注入、XSS等",
                confidence=0.9,
                references=["OWASP Top 10", "CWE"],
                alternatives=["使用安全框架", "进行渗透测试"]
            )
        elif self.domain == "performance":
            advice = ExpertAdvice(
                domain="performance",
                advice="建议进行性能分析，识别瓶颈并优化关键路径",
                confidence=0.85,
                references=["性能分析工具", "最佳实践"],
                alternatives=["使用缓存", "优化算法"]
            )
        elif self.domain == "architecture":
            advice = ExpertAdvice(
                domain="architecture",
                advice="建议采用模块化架构，关注可扩展性和可维护性",
                confidence=0.9,
                references=["设计模式", "架构原则"],
                alternatives=["微服务架构", "事件驱动架构"]
            )
        else:
            advice = ExpertAdvice(
                domain="general",
                advice=f"针对任务'{task.description}'，建议分步骤执行并持续验证",
                confidence=0.8,
                references=["最佳实践"],
                alternatives=["寻求其他专家意见", "参考类似案例"]
            )

        return advice

    async def analyze_problem(self, problem: str) -> Dict[str, Any]:
        """分析问题"""
        logger.info(f"分析问题: {problem}")

        # 模拟问题分析
        await asyncio.sleep(1.0)

        return {
            "problem": problem,
            "domain": self.domain,
            "analysis": f"从{self.domain}角度分析该问题",
            "root_causes": ["原因1", "原因2", "原因3"],
            "solutions": ["解决方案1", "解决方案2"],
            "risk_assessment": {
                "severity": "medium",
                "likelihood": "high",
                "impact": "medium"
            }
        }

    async def recommend_best_practice(self, context: str) -> Dict[str, Any]:
        """推荐最佳实践"""
        logger.info(f"推荐最佳实践: {context}")

        # 模拟最佳实践推荐
        await asyncio.sleep(0.5)

        return {
            "context": context,
            "domain": self.domain,
            "best_practice": f"{self.domain}领域的最佳实践",
            "benefits": ["好处1", "好处2", "好处3"],
            "considerations": ["考虑因素1", "考虑因素2"],
            "examples": ["示例1", "示例2"]
        }

    def get_advice_history(self, limit: int = 100) -> List[ExpertAdvice]:
        """获取建议历史"""
        return self.advice_history[-limit:]

    def get_domain(self) -> str:
        """获取专业领域"""
        return self.domain

    def set_knowledge(self, key: str, value: Any) -> None:
        """设置知识"""
        self.knowledge_base[key] = value
        logger.info(f"知识已更新: {key}")

    def get_knowledge(self, key: str) -> Optional[Any]:
        """获取知识"""
        return self.knowledge_base.get(key)
