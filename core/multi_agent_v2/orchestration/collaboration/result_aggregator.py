"""
LLM辅助结果聚合模块 - 多源信息的智能整合与归纳

功能：
1. 收集多个Agent的执行结果
2. 使用LLM进行智能整合
3. 生成结构化的最终报告
4. 支持多种聚合策略
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import time

logger = logging.getLogger(__name__)


class AggregationStrategy(Enum):
    """聚合策略"""
    SIMPLE_MERGE = "simple_merge"           # 简单合并
    WEIGHTED_VOTE = "weighted_vote"       # 加权投票
    HIERARCHICAL = "hierarchical"           # 层次聚合
    LLM_SUMMARIZE = "llm_summarize"        # LLM总结


@dataclass
class PartialResult:
    """部分结果"""
    source: str                           # 结果来源（Agent ID）
    result_type: str                       # 结果类型
    content: Any                          # 结果内容
    confidence: float = 1.0              # 置信度
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AggregationConfig:
    """聚合配置"""
    strategy: AggregationStrategy = AggregationStrategy.LLM_SUMMARIZE
    max_results: int = 10                 # 最大结果数
    confidence_threshold: float = 0.5    # 置信度阈值
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
