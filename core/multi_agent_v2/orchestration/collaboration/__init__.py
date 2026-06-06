"""
协作策略模块 - 多Agent协作模式
"""

from .strategies import (
    CollaborationResult,
    CollaborationMode,
    BaseCollaborationStrategy,
    PipelineStrategy,
    HybridStrategy,
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
    "BaseCollaborationStrategy",
    "PipelineStrategy",
    "HybridStrategy",
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
