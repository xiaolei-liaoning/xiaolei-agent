"""
协作策略 - 基础共享模块

包含：
- 基础数据类和枚举
- BaseCollaborationStrategy 抽象基类
- 共享工具类和函数
- 结果聚合相关类
- LLM动态策略选择函数
"""

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from core.multi_agent_v2.agents.base.base_agent import (
    BaseAgent, Task, ActionResult
)
from core.multi_agent_v2.orchestration.context.global_context_center import (
    GlobalContextCenter, TaskState
)

logger = logging.getLogger(__name__)


# =============================================================================
# 基础数据类
# =============================================================================

@dataclass
class CollaborationResult:
    """协作结果"""
    task_id: str
    success: bool
    final_result: Any
    partial_results: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    agent_results: Dict[str, ActionResult] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


class CollaborationMode(Enum):
    """协作模式"""
    PIPELINE = "pipeline"           # 流水线
    MASTER_SLAVE = "master_slave"   # 主从
    REVIEW = "review"               # 评审
    AUCTION = "auction"             # 拍卖
    CONSENSUS = "consensus"         # 共识
    MARKET = "market"               # 市场
    RECURSIVE = "recursive"         # 递归


# =============================================================================
# 策略基类
# =============================================================================

class BaseCollaborationStrategy(ABC):
    """协作策略基类"""

    def __init__(self, context_center: GlobalContextCenter):
        self.context_center = context_center

    @abstractmethod
    async def execute(
        self,
        task: Task,
        agents: List[BaseAgent],
        execution_plan: List[Dict[str, Any]]
    ) -> CollaborationResult:
        """执行协作"""
        pass

    async def _execute_agent_task(
        self,
        agent: BaseAgent,
        subtask_id: str,
        task_data: Dict[str, Any]
    ) -> Tuple[str, ActionResult]:
        """执行单个Agent任务"""
        start_time = time.time()

        try:
            # 创建子任务
            subtask = Task(
                task_id=subtask_id,
                type=task_data.get("type", "subtask"),
                description=task_data.get("description", ""),
                keywords=task_data.get("keywords", []),
                complexity=task_data.get("complexity", 0.5)
            )

            # Agent思考
            thought = await agent.think(subtask)

            # Agent执行（传递 LLM 选择的 tool_calls）
            result = await agent.act(thought.plan, getattr(thought, 'tool_calls', None))

            # Agent反思
            await agent.reflect(result)

            # 记录成功
            execution_time = time.time() - start_time
            await self.context_center.context_center.update_agent_state(
                agent.agent_id, "idle"
            )

            return subtask_id, result

        except Exception as e:
            logger.error(f"Agent {agent.agent_id} 执行任务 {subtask_id} 失败: {e}")

            return subtask_id, ActionResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time
            )


# =============================================================================
# 知识共享机制
# =============================================================================

class KnowledgeSharing:
    """知识共享机制"""

    def __init__(self):
        self.knowledge_base: Dict[str, Dict[str, Any]] = {}

    async def share_knowledge(self, agent_id: str, knowledge: Dict[str, Any]):
        """共享知识"""
        knowledge_id = f"knowledge_{int(time.time())}"
        self.knowledge_base[knowledge_id] = {
            "agent_id": agent_id,
            "knowledge": knowledge,
            "timestamp": time.time(),
            "access_count": 0
        }
        logger.info(f"Agent {agent_id} 共享了知识: {knowledge_id}")

    async def query_knowledge(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """查询知识"""
        results = []

        for knowledge_id, data in self.knowledge_base.items():
            if self._match(query, data["knowledge"]):
                data["access_count"] += 1
                results.append({
                    "knowledge_id": knowledge_id,
                    "agent_id": data["agent_id"],
                    "knowledge": data["knowledge"],
                    "timestamp": data["timestamp"]
                })

        return sorted(results, key=lambda x: x["timestamp"], reverse=True)[:max_results]

    def _match(self, query: str, knowledge: Dict[str, Any]) -> bool:
        """检查匹配"""
        query_lower = query.lower()
        knowledge_str = str(knowledge).lower()
        return query_lower in knowledge_str

    def get_popular_knowledge(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取热门知识"""
        sorted_items = sorted(
            self.knowledge_base.items(),
            key=lambda x: x[1]["access_count"],
            reverse=True
        )

        return [
            {
                "knowledge_id": k,
                "access_count": v["access_count"],
                "agent_id": v["agent_id"]
            }
            for k, v in sorted_items[:limit]
        ]


# =============================================================================
# 结果聚合模块
# =============================================================================

class AggregationStrategy(Enum):
    """聚合策略"""
    SIMPLE_MERGE = "simple_merge"           # 简单合并
    WEIGHTED_VOTE = "weighted_vote"         # 加权投票
    HIERARCHICAL = "hierarchical"           # 层次聚合
    LLM_SUMMARIZE = "llm_summarize"         # LLM总结


@dataclass
class PartialResult:
    """部分结果"""
    source: str                           # 结果来源（Agent ID）
    result_type: str                       # 结果类型
    content: Any                          # 结果内容
    confidence: float = 1.0               # 置信度
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AggregationConfig:
    """聚合配置"""
    strategy: AggregationStrategy = AggregationStrategy.LLM_SUMMARIZE
    max_results: int = 10                 # 最大结果数
    confidence_threshold: float = 0.5     # 置信度阈值
    use_llm_fallback: bool = True         # LLM失败时回退
    llm_model: str = "gpt-3.5-turbo"     # 使用的LLM模型


@dataclass
class AggregationResult:
    """聚合结果"""
    success: bool
    final_output: Any
    summary: str                          # LLM生成的总结
    metadata: Dict[str, Any] = field(default_factory=dict)
    aggregation_time: float = 0.0
    strategy_used: str = ""


class SimpleAggregator:
    """简单聚合器 - 合并多个结果"""

    def aggregate(self, results: List[PartialResult]) -> AggregationResult:
        """简单合并所有结果"""
        start_time = time.time()

        if not results:
            return AggregationResult(
                success=True,
                final_output=[],
                summary="无结果可聚合"
            )

        successful_results = [r for r in results if r.confidence >= 0.5]

        if not successful_results:
            return AggregationResult(
                success=True,
                final_output=results,
                summary=f"所有{len(results)}个结果置信度都低于阈值"
            )

        return AggregationResult(
            success=True,
            final_output=successful_results,
            summary=f"成功聚合{len(successful_results)}个结果",
            aggregation_time=time.time() - start_time
        )


class WeightedVoteAggregator:
    """加权投票聚合器"""

    def aggregate(self, results: List[PartialResult]) -> AggregationResult:
        """加权投票聚合"""
        start_time = time.time()

        if not results:
            return AggregationResult(
                success=True,
                final_output=[],
                summary="无结果可聚合"
            )

        # 按结果类型分组
        grouped = {}
        for result in results:
            result_type = result.result_type
            if result_type not in grouped:
                grouped[result_type] = []
            grouped[result_type].append(result)

        # 计算每组的加权分数
        aggregated = {}
        for result_type, type_results in grouped.items():
            total_weight = sum(r.confidence for r in type_results)
            weighted_output = {
                "type": result_type,
                "count": len(type_results),
                "total_confidence": total_weight,
                "results": [r.content for r in type_results],
                "avg_confidence": total_weight / len(type_results)
            }
            aggregated[result_type] = weighted_output

        return AggregationResult(
            success=True,
            final_output=aggregated,
            summary=f"加权聚合了{len(grouped)}种类型的结果",
            aggregation_time=time.time() - start_time
        )


class HierarchicalAggregator:
    """层次聚合器 - 先子任务聚合，再总体聚合"""

    def aggregate(self, results: List[PartialResult]) -> AggregationResult:
        """层次聚合"""
        start_time = time.time()

        if not results:
            return AggregationResult(
                success=True,
                final_output={},
                summary="无结果可聚合"
            )

        # 按来源分组
        by_source = {}
        for result in results:
            source = result.source
            if source not in by_source:
                by_source[source] = []
            by_source[source].append(result)

        # 第一层：每个来源内部聚合
        source_aggregates = {}
        for source, source_results in by_source.items():
            source_aggregates[source] = {
                "count": len(source_results),
                "avg_confidence": sum(r.confidence for r in source_results) / len(source_results),
                "results": [r.content for r in source_results],
                "success_rate": len([r for r in source_results if r.confidence >= 0.5]) / len(source_results)
            }

        # 第二层：总体聚合
        total_confidence = sum(v["avg_confidence"] for v in source_aggregates.values())
        overall_quality = total_confidence / len(source_aggregates) if source_aggregates else 0

        final_output = {
            "sources": source_aggregates,
            "overall": {
                "source_count": len(source_aggregates),
                "total_results": len(results),
                "overall_confidence": overall_quality,
                "success_rate": len([r for r in results if r.confidence >= 0.5]) / len(results)
            }
        }

        return AggregationResult(
            success=True,
            final_output=final_output,
            summary=f"层次聚合了{len(source_aggregates)}个来源的{len(results)}个结果",
            aggregation_time=time.time() - start_time
        )


class LLMAggregator:
    """LLM辅助聚合器 - 使用LLM生成总结"""

    def __init__(self, llm_facade: Optional[Any] = None):
        self.llm_facade = llm_facade

    async def aggregate(
        self,
        results: List[PartialResult],
        task_description: str = ""
    ) -> AggregationResult:
        """使用LLM聚合结果"""
        start_time = time.time()

        if not results:
            return AggregationResult(
                success=True,
                final_output=[],
                summary="无结果可聚合"
            )

        # 构建LLM prompt
        prompt = self._build_aggregation_prompt(results, task_description)

        try:
            # 调用LLM
            if self.llm_facade:
                response = await self.llm_facade.generate(prompt)
                summary = response if isinstance(response, str) else response.get("content", "")
            else:
                # 无LLM时使用简单总结
                summary = self._simple_summary(results)

            successful_results = [r for r in results if r.confidence >= 0.5]

            return AggregationResult(
                success=True,
                final_output=successful_results,
                summary=summary,
                metadata={
                    "total_results": len(results),
                    "successful_results": len(successful_results),
                    "llm_used": self.llm_facade is not None
                },
                aggregation_time=time.time() - start_time
            )

        except Exception as e:
            logger.error(f"LLM聚合失败: {e}")
            # 回退到简单聚合
            simple = SimpleAggregator()
            result = simple.aggregate(results)
            result.strategy_used = "llm_fallback"
            return result

    def _build_aggregation_prompt(
        self,
        results: List[PartialResult],
        task_description: str
    ) -> Dict[str, Any]:
        """构建聚合Prompt"""
        # 构建结果列表
        results_text = []
        for i, r in enumerate(results, 1):
            results_text.append(f"""
结果{i} [来源: {r.source}, 类型: {r.result_type}, 置信度: {r.confidence:.2f}]:
{r.content}
""")

        system_prompt = """你是一个专业的报告生成专家。你的任务是将多个Agent的执行结果整合成一个清晰、简洁的最终报告。

要求：
1. 总结各结果的核心内容
2. 识别结果之间的一致性和差异
3. 提供整体结论和建议
4. 使用清晰的结构化格式
5. 突出关键信息和重要发现

输出格式：
- 执行摘要（一段话概括整体情况）
- 详细结果（按类型分组）
- 关键发现（3-5个要点）
- 建议和结论"""

        user_prompt = f"""## 任务描述
{task_description or '无特定任务描述'}

## 待聚合结果
{"".join(results_text)}

请生成最终报告。"""

        return {
            "prompt": system_prompt + "\n\n" + user_prompt,
            "metadata": {
                "task_type": "aggregation",
                "requirements": ["summary", "structured_output"]
            }
        }

    def _simple_summary(self, results: List[PartialResult]) -> str:
        """简单总结（无LLM时使用）"""
        if not results:
            return "无结果"

        total = len(results)
        successful = len([r for r in results if r.confidence >= 0.5])
        types = set(r.result_type for r in results)

        return f"聚合了{total}个结果，其中{successful}个置信度较高，涉及{len(types)}种类型：{', '.join(types)}"


class ResultAggregator:
    """结果聚合器 - 统一接口"""

    def __init__(self, config: Optional[AggregationConfig] = None, llm_facade: Optional[Any] = None):
        self.config = config or AggregationConfig()
        self.llm_facade = llm_facade

        # 初始化各种聚合器
        self.simple_aggregator = SimpleAggregator()
        self.weighted_aggregator = WeightedVoteAggregator()
        self.hierarchical_aggregator = HierarchicalAggregator()
        self.llm_aggregator = LLMAggregator(llm_facade)

    async def aggregate(
        self,
        results: List[PartialResult],
        task_description: str = ""
    ) -> AggregationResult:
        """聚合多个结果"""
        strategy = self.config.strategy

        logger.info(f"开始聚合，使用策略: {strategy.value}")

        if strategy == AggregationStrategy.SIMPLE_MERGE:
            result = self.simple_aggregator.aggregate(results)
            result.strategy_used = strategy.value
            return result

        elif strategy == AggregationStrategy.WEIGHTED_VOTE:
            result = self.weighted_aggregator.aggregate(results)
            result.strategy_used = strategy.value
            return result

        elif strategy == AggregationStrategy.HIERARCHICAL:
            result = self.hierarchical_aggregator.aggregate(results)
            result.strategy_used = strategy.value
            return result

        elif strategy == AggregationStrategy.LLM_SUMMARIZE:
            return await self.llm_aggregator.aggregate(results, task_description)

        else:
            # 默认使用简单聚合
            result = self.simple_aggregator.aggregate(results)
            result.strategy_used = "default"
            return result

    def aggregate_sync(
        self,
        results: List[PartialResult],
        task_description: str = ""
    ) -> AggregationResult:
        """同步聚合（不使用LLM）"""
        if self.config.strategy == AggregationStrategy.LLM_SUMMARIZE:
            # 回退到层次聚合
            result = self.hierarchical_aggregator.aggregate(results)
            result.strategy_used = "hierarchical_fallback"
            return result

        return asyncio.run(self.aggregate(results, task_description))

    def set_strategy(self, strategy: AggregationStrategy) -> None:
        """设置聚合策略"""
        self.config.strategy = strategy
        logger.info(f"聚合策略已更新: {strategy.value}")


class MasterAgentAggregator:
    """MasterAgent专用的结果聚合器"""

    def __init__(self, llm_facade: Optional[Any] = None):
        self.aggregator = ResultAggregator(
            config=AggregationConfig(
                strategy=AggregationStrategy.LLM_SUMMARIZE
            ),
            llm_facade=llm_facade
        )

    async def aggregate_master_results(
        self,
        subtask_results: Dict[str, Any],
        task_goal: str
    ) -> AggregationResult:
        """聚合MasterAgent的子任务结果

        Args:
            subtask_results: 子任务ID -> 结果 的字典
            task_goal: 原始任务目标

        Returns:
            聚合结果
        """
        # 转换为PartialResult列表
        partial_results = []
        for subtask_id, result in subtask_results.items():
            partial_results.append(PartialResult(
                source=result.get("agent_id", subtask_id),
                result_type=result.get("type", "unknown"),
                content=result.get("output"),
                confidence=result.get("confidence", 0.8),
                metadata=result
            ))

        # 聚合
        return await self.aggregator.aggregate(partial_results, task_goal)


# =============================================================================
# LLM动态策略选择
# =============================================================================

async def select_strategy_with_llm(
    task_description: str,
    task_keywords: list,
    estimated_steps: int,
    complexity: float,
    available_agents: list,
    llm_router=None,
) -> tuple:
    """调用 LLM 选择协作策略，返回 (mode, params)

    Args:
        task_description: 任务描述
        task_keywords: 任务关键词
        estimated_steps: 预估步骤数
        complexity: 复杂度 (0-1)
        available_agents: 可用Agent列表
        llm_router: LLM路由实例

    Returns:
        (mode_str: str, params: dict) — 例如 ("pipeline", {"parallelism": 3})
        失败时返回硬编码规则的兜底结果
    """
    # 兜底：硬编码规则
    def fallback() -> tuple:
        if complexity > 0.8:
            return "review", {"reviewers": max(1, len(available_agents)//2)}
        if estimated_steps > 2 and estimated_steps <= len(available_agents):
            return "pipeline", {"parallelism": min(estimated_steps, len(available_agents))}
        if complexity > 0.5:
            return "master_slave", {"slaves": max(1, len(available_agents)-1)}
        if len(task_keywords) > 3:
            return "auction", {}  # 多技能需求 -> 拍卖
        return "hybrid", {}

    # 没有 LLM 时直接走兜底
    if not llm_router:
        return fallback()

    from core.engine.llm_backend import GLMBackend

    # 构建 prompt
    agents_summary = "\n".join([
        f"- {getattr(a, 'agent_name', 'unknown')} "
        f"(type: {getattr(a, 'agent_type', '?')}, "
        f"capabilities: {[c.name for c in getattr(a, 'capabilities', [])][:3]})"
        for a in available_agents[:10]
    ]) if available_agents else "无可用Agent信息"

    prompt = f"""根据以下任务信息，选择最合适的多Agent协作策略。

任务描述: {task_description}
关键词: {task_keywords}
预估步骤数: {estimated_steps}
复杂度: {complexity}

可用Agent:\n{agents_summary}

可选策略:\n- pipeline: 流水线顺序执行，每阶段专注特定任务\n- master_slave: 主从模式，主Agent分解，从Agent并行执行\n- review: 评审模式，多Agent并行 + 评审达成共识\n- auction: 拍卖模式，任务发布后最合适的Agent竞标执行\n- hybrid: 混合模式，动态组合多种策略\n\n请只输出JSON格式，不要其他内容:\n{{"mode": "策略名", "params": {{"并行度": 数字, "重试次数": 数字, "评审阈值": 0-1}}}}\n"""

    try:
        messages = [
            {"role": "system", "content": "你是一个多Agent协作策略专家，根据任务特征选择最优策略。"},
            {"role": "user", "content": prompt}
        ]
        if hasattr(llm_router, "chat"):
            response = await llm_router.chat(messages, temperature=0.3, max_tokens=300)
        else:
            return fallback()

        # 尝试解析JSON
        result = json.loads(response.strip().strip("```json").strip("```").strip())
        mode = result.get("mode", "hybrid")
        params = result.get("params", {})
        if mode not in ("pipeline", "master_slave", "review", "auction", "hybrid"):
            return fallback()
        return mode, params

    except Exception as e:
        logger.warning(f"LLM策略选择失败，使用兜底规则: {e}")
        return fallback()


# =============================================================================
# HybridStrategy — 使用延迟导入以避免循环依赖
# =============================================================================

class HybridStrategy(BaseCollaborationStrategy):
    """混合协作策略 - 根据任务特征动态组合多种模式"""

    async def execute(
        self,
        task: Task,
        agents: List[BaseAgent],
        execution_plan: List[Dict[str, Any]]
    ) -> CollaborationResult:
        """混合执行 - 根据任务特征选择最合适的策略"""

        # 根据任务复杂度选择策略
        if task.complexity < 0.3:
            # 简单任务：直接执行
            return await self._execute_simple_task(task, agents)
        elif task.complexity < 0.6:
            # 中等复杂度：主从模式
            from .master_worker import MasterSlaveStrategy
            strategy = MasterSlaveStrategy(self.context_center)
            return await strategy.execute(task, agents, execution_plan)
        else:
            # 复杂任务：评审模式
            from .review import ReviewStrategy
            strategy = ReviewStrategy(self.context_center)
            return await strategy.execute(task, agents, execution_plan)

    async def _execute_simple_task(self, task: Task, agents: List[BaseAgent]) -> CollaborationResult:
        """执行简单任务"""
        start_time = time.time()

        # 直接选择第一个可用Agent
        agent = agents[0] if agents else None

        if not agent:
            return CollaborationResult(
                task_id=task.task_id,
                success=False,
                final_result=None,
                errors=["没有可用Agent"]
            )

        subtask_id, result = await self._execute_agent_task(
            agent,
            task.task_id,
            {
                "type": "simple",
                "description": task.description,
                "keywords": task.keywords,
                "complexity": task.complexity
            }
        )

        await self.context_center.update_task_state(
            task.task_id,
            TaskState.COMPLETED if result.success else TaskState.FAILED
        )

        return CollaborationResult(
            task_id=task.task_id,
            success=result.success,
            final_result=result.output,
            execution_time=time.time() - start_time,
            agent_results={agent.agent_id: result}
        )
