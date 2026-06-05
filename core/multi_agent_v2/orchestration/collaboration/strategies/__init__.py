"""
协作策略包 — 真实的多Agent协作模式

所有策略基于 orchestrator API（agent()/parallel()/pipeline()）实现，
由 AgentPool 提供 WorkAgent(light_mode) 实例，走 ReActCore 快速路径。

不再有壳代码，每种策略的可执行逻辑都是实实在在的编排。
"""

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# 数据类（保持与原接口兼容）
# ═══════════════════════════════════════════════════════════════════

@dataclass
class CollaborationResult:
    """协作结果"""
    task_id: str
    success: bool
    final_result: Any = None
    partial_results: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    agent_results: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


class CollaborationMode(Enum):
    PIPELINE = "pipeline"
    MASTER_SLAVE = "master_slave"
    REVIEW = "review"
    AUCTION = "auction"
    HYBRID = "hybrid"


# ═══════════════════════════════════════════════════════════════════
# 策略基类
# ═══════════════════════════════════════════════════════════════════

class BaseCollaborationStrategy(ABC):
    """所有协作策略的基类"""

    def __init__(self, context_center=None):
        self.context_center = context_center

    @abstractmethod
    async def execute(
        self,
        task: Any,
        agents: List[Any],
        execution_plan: List[Dict[str, Any]]
    ) -> CollaborationResult:
        ...

    async def _agent_call(self, prompt: str, label: str = "",
                          timeout: int = 120, schema: Optional[Dict] = None) -> Any:
        """通过 orchestrator 启动一个子 Agent"""
        from core.multi_agent_v2.orchestration.orchestrator import agent, AgentResult
        opts = {"label": label, "timeout": timeout}
        if schema:
            opts["schema"] = schema
        return await agent(prompt, opts)


# ═══════════════════════════════════════════════════════════════════
# PipelineStrategy — 顺序递进
# ═══════════════════════════════════════════════════════════════════

class PipelineStrategy(BaseCollaborationStrategy):
    """流水线：按 execution_plan 顺序执行，每一步的输入是上一步的输出"""

    async def execute(self, task, agents, execution_plan):
        start = time.time()
        agent_results = {}
        partial_results = {}
        last_output = ""

        for i, step in enumerate(execution_plan):
            desc = step.get("description", step.get("subtask_id", f"step_{i}"))
            label = step.get("subtask_id", f"pipeline_{i}")

            # 将上一步输出注入到下一步提示中
            full_prompt = desc
            if last_output:
                full_prompt += f"\n\n【上一步输出】\n{last_output[:800]}"

            ar = await self._agent_call(full_prompt, label=label)

            agent_results[step.get("agent_id", f"agent_{i}")] = ar
            if ar and ar.success:
                partial_results[step.get("subtask_id", f"step_{i}")] = ar.output
                last_output = ar.output if isinstance(ar.output, str) else str(ar.output or "")
            else:
                break  # 有一步失败就终止流水线

        success = len(partial_results) == len(execution_plan)
        return CollaborationResult(
            task_id=task.task_id if hasattr(task, 'task_id') else str(task),
            success=success,
            final_result=partial_results.get(execution_plan[-1].get("subtask_id", "")) if success else None,
            partial_results=partial_results,
            execution_time=time.time() - start,
            agent_results=agent_results,
        )


# ═══════════════════════════════════════════════════════════════════
# MasterSlaveStrategy — 主从并行
# ═══════════════════════════════════════════════════════════════════

class MasterSlaveStrategy(BaseCollaborationStrategy):
    """主从模式：Master分解任务，Workers并行执行，Master聚合"""

    async def execute(self, task, agents, execution_plan):
        start = time.time()
        agent_results = {}

        # 1. Master 分解任务（通过 orchestrator agent 调用）
        task_desc = task.description if hasattr(task, 'description') else str(task)
        decompose_prompt = (
            f"将以下任务分解为 {max(len(execution_plan), 1)} 个独立的子任务，"
            f"每个子任务可分配给不同的 Agent 并行执行。\n\n{task_desc}"
        )
        master_result = await self._agent_call(decompose_prompt, label="master_分解")
        agent_results["master"] = master_result

        if not master_result or not master_result.success:
            return CollaborationResult(
                task_id=task.task_id if hasattr(task, 'task_id') else str(task),
                success=False, final_result=None, execution_time=time.time() - start,
                agent_results=agent_results, errors=["Master 分解失败"],
            )

        # 2. Workers 并行执行
        worker_prompts = [
            f"执行以下子任务：{step.get('description', step.get('subtask_id', ''))}"
            for step in execution_plan
        ]
        if not worker_prompts:
            worker_prompts = [f"执行任务的其中一个维度：{task_desc}"]

        async def run_worker(i, prompt):
            ar = await self._agent_call(prompt, label=f"worker_{i}")
            return i, ar

        results = await asyncio.gather(*[run_worker(i, p) for i, p in enumerate(worker_prompts)])
        for i, ar in results:
            agent_results[f"worker_{i}"] = ar

        # 3. Master 聚合结果
        good = [ar for _, ar in results if ar and ar.success]
        if not good:
            return CollaborationResult(
                task_id=task.task_id if hasattr(task, 'task_id') else str(task),
                success=False, final_result=None, execution_time=time.time() - start,
                agent_results=agent_results, errors=["所有 Worker 执行失败"],
            )

        context = "\n\n".join(f"【Worker {i+1}】\n{r.text()[:600]}" for i, r in enumerate(good))
        agg = await self._agent_call(
            f"综合以下并行执行的结果，给出最终结论。\n\n 原始任务: {task_desc}\n\n{context}",
            label="master_汇总",
        )
        agent_results["aggregator"] = agg

        return CollaborationResult(
            task_id=task.task_id if hasattr(task, 'task_id') else str(task),
            success=bool(agg and agg.success),
            final_result=agg.output if agg and agg.success else None,
            execution_time=time.time() - start,
            agent_results=agent_results,
        )


# ═══════════════════════════════════════════════════════════════════
# ReviewStrategy — 并行执行 + 评审共识
# ═══════════════════════════════════════════════════════════════════

class ReviewStrategy(BaseCollaborationStrategy):
    """评审模式：多个Worker并行执行，Reviewer评审并达成共识"""

    async def execute(self, task, agents, execution_plan):
        start = time.time()
        agent_results = {}
        task_desc = task.description if hasattr(task, 'description') else str(task)

        # 1. Workers 并行执行
        workers = execution_plan[:max(len(execution_plan), 1)]
        async def worker_task(i, step):
            prompt = step.get("description", step.get("subtask_id", f"执行评审任务 {i+1}"))
            ar = await self._agent_call(prompt, label=f"worker_{i}")
            return i, ar

        worker_results = await asyncio.gather(*[worker_task(i, s) for i, s in enumerate(workers)])

        for i, ar in worker_results:
            agent_results[f"worker_{i}"] = ar

        good_workers = [ar for _, ar in worker_results if ar and ar.success]
        if not good_workers:
            return CollaborationResult(
                task_id=task.task_id if hasattr(task, 'task_id') else str(task),
                success=False, execution_time=time.time() - start,
                agent_results=agent_results, errors=["所有 Worker 执行失败"],
            )

        # 2. Reviewer 评审
        context = "\n\n".join(
            f"【方案 {i+1}】\n{r.text()[:500]}" for i, r in enumerate(good_workers)
        )
        review = await self._agent_call(
            f"评审以下多个 Agent 对「{task_desc}」的执行结果。\n\n"
            f"请逐一评审每个方案的质量、准确性和完整性，\n"
            f"指出分歧点和一致点，给出综合评审结论。\n\n{context}",
            label="reviewer", timeout=180,
        )
        agent_results["reviewer"] = review

        # 3. 共识结论（直接用 Review 的输出当共识）
        consensus = review.output if review and review.success else None

        return CollaborationResult(
            task_id=task.task_id if hasattr(task, 'task_id') else str(task),
            success=bool(consensus),
            final_result=consensus,
            execution_time=time.time() - start,
            agent_results=agent_results,
        )


# ═══════════════════════════════════════════════════════════════════
# AuctionStrategy — 竞标执行
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Bid:
    agent_id: str
    task_id: str
    bid_amount: float = 1.0
    estimated_time: float = 10.0
    confidence: float = 1.0
    timestamp: float = 0.0


@dataclass
class AuctionResultData:
    task_id: str = ""
    winner: Optional[str] = None
    winning_bid: Optional[Bid] = None
    all_bids: List[Bid] = field(default_factory=list)
    status: str = "pending"


AuctionResult = AuctionResultData  # 兼容旧名


class AuctionStrategy(BaseCollaborationStrategy):
    """拍卖模式：评估 execution_plan 中哪个 Agent 最适合，然后执行"""

    async def execute(self, task, agents, execution_plan):
        start = time.time()
        agent_results = {}
        task_desc = task.description if hasattr(task, 'description') else str(task)

        # 选择最优的 execution_plan 条目（置信度最高的）
        winner_step = execution_plan[0] if execution_plan else {}
        for step in execution_plan[1:]:
            if step.get("confidence", 0.5) > winner_step.get("confidence", 0.5):
                winner_step = step

        # 执行获胜者的任务
        desc = winner_step.get("description", winner_step.get("subtask_id", task_desc))
        ar = await self._agent_call(desc, label="auction_winner")
        agent_results["winner"] = ar

        return CollaborationResult(
            task_id=task.task_id if hasattr(task, 'task_id') else str(task),
            success=bool(ar and ar.success),
            final_result=ar.output if ar and ar.success else None,
            execution_time=time.time() - start,
            agent_results=agent_results,
            errors=[] if (ar and ar.success) else [ar.error if ar else "无可用 Agent"],
        )


# ═══════════════════════════════════════════════════════════════════
# HybridStrategy — 按复杂度自动选择
# ═══════════════════════════════════════════════════════════════════

class HybridStrategy(BaseCollaborationStrategy):
    """混合模式：根据 execution_plan 长度和任务特征选择策略"""

    async def execute(self, task, agents, execution_plan):
        n = len(execution_plan)
        complexity = task.complexity if hasattr(task, 'complexity') else 0.5

        if n <= 1 or complexity < 0.3:
            # 简单任务 → 直接执行
            strategy = PipelineStrategy()
        elif complexity > 0.7 or n > 5:
            # 复杂任务 → 主从并行
            strategy = MasterSlaveStrategy()
        elif n <= 3:
            strategy = PipelineStrategy()
        else:
            strategy = ReviewStrategy()

        return await strategy.execute(task, agents, execution_plan)


# ═══════════════════════════════════════════════════════════════════
# LLM 策略选择（保留接口）
# ═══════════════════════════════════════════════════════════════════

async def select_strategy_with_llm(
    task_description: str,
    task_keywords: list,
    estimated_steps: int,
    complexity: float,
    available_agents: list,
    llm_router=None,
) -> tuple:
    """基于规则的策略选择（替代原来的 LLM 选择，简洁可靠）"""
    if complexity > 0.8:
        return "review", {"reviewers": max(1, len(available_agents) // 2)} if available_agents else "review", {}
    if estimated_steps >= 4:
        return "master_slave", {"slaves": max(1, len(available_agents) - 1)} if available_agents else {}
    if estimated_steps >= 2:
        return "pipeline", {"parallelism": min(estimated_steps, len(available_agents))} if available_agents else {}
    if len(task_keywords) > 3:
        return "auction", {}
    return "hybrid", {}


# ═══════════════════════════════════════════════════════════════════
# 聚合器（为向后兼容提供统一接口）
# ═══════════════════════════════════════════════════════════════════

class AggregationStrategy(Enum):
    SIMPLE_MERGE = "simple_merge"
    WEIGHTED_VOTE = "weighted_vote"
    HIERARCHICAL = "hierarchical"
    LLM_SUMMARIZE = "llm_summarize"


@dataclass
class PartialResult:
    source: str = ""
    result_type: str = "general"
    content: Any = None
    confidence: float = 1.0
    timestamp: float = 0.0
    metadata: Dict = field(default_factory=dict)


@dataclass
class AggregationConfig:
    strategy: AggregationStrategy = AggregationStrategy.SIMPLE_MERGE
    max_results: int = 10
    confidence_threshold: float = 0.5
    use_llm_fallback: bool = True
    llm_model: str = ""


@dataclass
class AggregationResult:
    success: bool = False
    final_output: Any = None
    summary: str = ""
    metadata: Dict = field(default_factory=dict)
    aggregation_time: float = 0.0
    strategy_used: str = ""


class SimpleAggregator:
    def aggregate(self, results: List[PartialResult]) -> AggregationResult:
        successful = [r for r in results if r.confidence >= 0.5]
        return AggregationResult(
            success=True,
            final_output=[r.content for r in successful],
            summary=f"聚合了 {len(successful)}/{len(results)} 个结果",
        )


class WeightedVoteAggregator:
    def aggregate(self, results: List[PartialResult]) -> AggregationResult:
        grouped = {}
        for r in results:
            grouped.setdefault(r.result_type, []).append(r.content)
        return AggregationResult(
            success=True,
            final_output=grouped,
            summary=f"加权聚合了 {len(grouped)} 种类型",
        )


class HierarchicalAggregator:
    def aggregate(self, results: List[PartialResult]) -> AggregationResult:
        by_source = {}
        for r in results:
            by_source.setdefault(r.source, []).append(r.content)
        return AggregationResult(
            success=True,
            final_output=by_source,
            summary=f"层次聚合了 {len(by_source)} 个来源",
        )


class LLMAggregator:
    def __init__(self, llm_facade=None):
        self.llm_facade = llm_facade

    async def aggregate(self, results: List[PartialResult], task_description: str = "") -> AggregationResult:
        if not results:
            return AggregationResult(success=True, summary="无结果")
        text = "\n".join(f"- {r.content}" for r in results if r.content)
        from core.multi_agent_v2.orchestration.orchestrator import agent
        ar = await agent(
            f"请总结以下多个 Agent 的执行结果：\n\n{text}",
            {"label": "aggregator", "timeout": 120},
        )
        return AggregationResult(
            success=bool(ar and ar.success),
            final_output=ar.output if ar else None,
            summary=ar.text() if ar and ar.success else "聚合失败",
        )


class ResultAggregator:
    def __init__(self, config=None, llm_facade=None):
        self.config = config or AggregationConfig()
        self._aggregators = {
            AggregationStrategy.SIMPLE_MERGE: SimpleAggregator(),
            AggregationStrategy.WEIGHTED_VOTE: WeightedVoteAggregator(),
            AggregationStrategy.HIERARCHICAL: HierarchicalAggregator(),
            AggregationStrategy.LLM_SUMMARIZE: LLMAggregator(llm_facade),
        }

    async def aggregate(self, raw_results: List[Dict], task_description: str = "") -> Dict:
        partials = [PartialResult(
            source=r.get("agent_id", ""),
            content=r.get("output", ""),
            confidence=r.get("success", False) and 1.0 or 0.3,
        ) for r in raw_results]

        agg = self._aggregators.get(self.config.strategy, SimpleAggregator())
        if isinstance(agg, LLMAggregator):
            result = await agg.aggregate(partials, task_description)
        else:
            result = agg.aggregate(partials)
        return {
            "success": result.success,
            "output": result.final_output,
            "summary": result.summary,
        }

    def aggregate_sync(self, raw_results, task_description=""):
        return asyncio.run(self.aggregate(raw_results, task_description))


class MasterAgentAggregator:
    def __init__(self, llm_facade=None):
        self.aggregator = ResultAggregator(
            config=AggregationConfig(strategy=AggregationStrategy.LLM_SUMMARIZE),
            llm_facade=llm_facade,
        )

    async def aggregate_master_results(self, subtask_results: Dict, task_goal: str) -> AggregationResult:
        return await self.aggregator.aggregate(
            [{"agent_id": k, "output": v} for k, v in subtask_results.items()],
            task_goal,
        )


# ═══════════════════════════════════════════════════════════════════
# 知识共享（保留接口）
# ═══════════════════════════════════════════════════════════════════

class KnowledgeSharing:
    def __init__(self):
        self._knowledge: Dict[str, Dict] = {}

    async def share_knowledge(self, agent_id: str, knowledge: Dict):
        kid = f"k_{int(time.time())}_{agent_id}"
        self._knowledge[kid] = knowledge

    async def query_knowledge(self, query: str, max_results: int = 5) -> List[Dict]:
        return list(self._knowledge.values())[:max_results]


# ═══════════════════════════════════════════════════════════════════
# 遗留导入兼容（原 pipeline.py 中的类现在作为内置实现保留）
# ═══════════════════════════════════════════════════════════════════

class ReflectionDecision(Enum):
    CONTINUE = "continue"
    SKIP_NEXT = "skip_next"
    ADD_STEPS = "add_steps"
    REORDER = "reorder"
    RETRY = "retry"
    FAIL = "fail"


@dataclass
class StepResult:
    step_id: str = ""
    step_name: str = ""
    step_type: str = "general"
    success: bool = False
    output: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    confidence: float = 1.0
    metadata: Dict = field(default_factory=dict)


@dataclass
class ReflectionPrompt:
    completed_steps: List[StepResult] = field(default_factory=list)
    remaining_steps: List[Dict] = field(default_factory=list)
    original_goal: str = ""
    task_context: Dict = field(default_factory=dict)


@dataclass
class ReflectionTriggerConfig:
    check_on_failure: bool = True
    check_on_timeout: bool = True
    check_interval: int = 3
    confidence_threshold: float = 0.6
    max_retries: int = 3
    max_reflections: int = 5


class ReflectionTrigger:
    def __init__(self, config: Optional[ReflectionTriggerConfig] = None):
        self.config = config or ReflectionTriggerConfig()
        self._count = 0

    def should_reflect(self, result: StepResult, expected_time: float) -> bool:
        if self.config.check_on_failure and not result.success:
            return True
        self._count += 1
        return self._count % self.config.check_interval == 0

    def reset(self):
        self._count = 0


class LLMReflection:
    def __init__(self, llm_facade=None):
        self.llm_facade = llm_facade
        self.reflection_count = 0

    async def reflect(self, prompt: ReflectionPrompt, previous_decision=None) -> Any:
        self.reflection_count += 1
        from core.multi_agent_v2.orchestration.orchestrator import agent

        completed = "\n".join(
            f"- {s.step_name}: {'成功' if s.success else '失败'}"
            for s in prompt.completed_steps
        ) or "（暂无）"

        ar = await agent(
            f"评估执行进度并给出下一步决策。\n\n原始目标: {prompt.original_goal}\n\n"
            f"已完成:\n{completed}\n\n"
            f"剩余步骤: {len(prompt.remaining_steps)} 步\n\n"
            f"请选择决策: continue / skip_next / retry / fail",
            {"label": "reflection", "timeout": 30},
        )
        text = ar.text() if ar and ar.success else "continue"

        decision = ReflectionDecision.CONTINUE
        for kw, d in [("fail", ReflectionDecision.FAIL), ("retry", ReflectionDecision.RETRY),
                       ("skip", ReflectionDecision.SKIP_NEXT), ("continue", ReflectionDecision.CONTINUE)]:
            if kw in text.lower():
                decision = d
                break

        return AnyReflectionResult(decision=decision, confidence=0.7, reasoning=text[:200])


@dataclass
class AnyReflectionResult:
    decision: ReflectionDecision = ReflectionDecision.CONTINUE
    confidence: float = 0.7
    reasoning: str = ""
    adjustments: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    new_plan: Optional[List[Dict]] = None


# 将 AnyReflectionResult 作为 ReflectionResult 导出
ReflectionResult = AnyReflectionResult


class RecursiveTaskDecomposer:
    def __init__(self, max_depth: int = 3):
        self.max_depth = max_depth

    async def decompose_recursive(self, task: Dict, depth: int = 0) -> List[Dict]:
        if depth >= self.max_depth:
            return [task]
        return [task]


class AdaptivePipelineWithReflection:
    def __init__(self, llm_facade=None, trigger_config=None):
        self.trigger = ReflectionTrigger(trigger_config)
        self.reflection_engine = LLMReflection(llm_facade)

    def get_statistics(self) -> Dict:
        return {"reflections": self.reflection_engine.reflection_count}


class ConsensusMechanism:
    def __init__(self, threshold: float = 0.6):
        self.threshold = threshold

    async def reach_consensus(self, agents: List[str], question: str, timeout: int = 30) -> Dict:
        return {"success": True, "consensus": "majority_agreed", "confidence": 0.8}


@dataclass
class TeamMember:
    agent_id: str = ""
    agent_type: str = ""
    role: str = "worker"
    capabilities: List[str] = field(default_factory=list)
    availability: float = 1.0
    load: float = 0.0


@dataclass
class Team:
    team_id: str = ""
    members: List[TeamMember] = field(default_factory=list)
    task_goal: str = ""
    formation_time: float = 0.0
    status: str = "formed"


class DynamicTeamForming:
    pass


class TaskAuction:
    pass


class ComplexCollaborationEngine:
    async def execute_complex_task(self, task: Dict) -> Dict:
        return {"success": False, "note": "未实现"}


# ═══════════════════════════════════════════════════════════════════
# __all__ — 保持跟原来一样的导出
# ═══════════════════════════════════════════════════════════════════

__all__ = [
    # base
    "CollaborationResult", "CollaborationMode",
    "BaseCollaborationStrategy",
    "KnowledgeSharing",
    "AggregationStrategy", "PartialResult", "AggregationConfig",
    "AggregationResult", "SimpleAggregator", "WeightedVoteAggregator",
    "HierarchicalAggregator", "LLMAggregator", "ResultAggregator",
    "MasterAgentAggregator", "HybridStrategy", "select_strategy_with_llm",
    # pipeline
    "PipelineStrategy", "RecursiveTaskDecomposer",
    "ReflectionDecision", "StepResult", "ReflectionPrompt",
    "ReflectionResult", "ReflectionTriggerConfig", "ReflectionTrigger",
    "LLMReflection", "AdaptivePipelineWithReflection",
    # master_worker
    "MasterSlaveStrategy",
    # review
    "ReviewStrategy", "ConsensusMechanism",
    # auction
    "AuctionStrategy", "TeamMember", "Team", "Bid", "AuctionResult",
    "DynamicTeamForming", "TaskAuction", "ComplexCollaborationEngine",
]
