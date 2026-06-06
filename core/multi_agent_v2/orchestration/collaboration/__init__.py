"""
协作策略模块 - 多Agent协作模式

注意：以下类已废弃（[DEPRECATED]），仅保留向后兼容：
  - BaseCollaborationStrategy  -> 请使用具体策略类
  - PipelineStrategy          -> 请使用 AdaptivePipelineWithReflection
  - HybridStrategy            -> 动态策略选择由 select_strategy_with_llm 接管
"""

from .strategies import (
    CollaborationResult,
    CollaborationMode,
    BaseCollaborationStrategy,  # [DEPRECATED]
    PipelineStrategy,           # [DEPRECATED]
    HybridStrategy,             # [DEPRECATED]
    LLMReflection,
    ReflectionTrigger,
    ReflectionDecision,
    ReflectionResult,
    ReflectionPrompt,
    AdaptivePipelineWithReflection,
    ResultAggregator,
    PartialResult,
    AggregationStrategy,
    KnowledgeSharing,
    SimpleAggregator,
    WeightedVoteAggregator,
    HierarchicalAggregator,
    LLMAggregator,
    MasterAgentAggregator,
)

__all__ = [
    "CollaborationResult",
    "CollaborationMode",
    "BaseCollaborationStrategy",  # [DEPRECATED]
    "PipelineStrategy",           # [DEPRECATED]
    "HybridStrategy",             # [DEPRECATED]
    "LLMReflection",
    "ReflectionTrigger",
    "ReflectionDecision",
    "ReflectionResult",
    "ReflectionPrompt",
    "AdaptivePipelineWithReflection",
    "ResultAggregator",
    "PartialResult",
    "AggregationStrategy",
    "KnowledgeSharing",
    "SimpleAggregator",
    "WeightedVoteAggregator",
    "HierarchicalAggregator",
    "LLMAggregator",
    "MasterAgentAggregator",
]
