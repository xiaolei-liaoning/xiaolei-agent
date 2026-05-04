"""
协作策略模块 - 多Agent协作模式
"""

from .strategies import (
    CollaborationResult,
    BaseCollaborationStrategy,
    PipelineStrategy,
    MasterSlaveStrategy,
    ReviewStrategy,
    AuctionStrategy,
    HybridStrategy
)
from .llm_reflection import LLMReflection, ReflectionTrigger, ReflectionDecision
from .result_aggregator import ResultAggregator, PartialResult, AggregationStrategy
from .complex_collaboration import ComplexCollaborationEngine, CollaborationMode

__all__ = [
    "CollaborationResult",
    "BaseCollaborationStrategy",
    "PipelineStrategy",
    "MasterSlaveStrategy",
    "ReviewStrategy",
    "AuctionStrategy",
    "HybridStrategy",
    "LLMReflection",
    "ReflectionTrigger",
    "ReflectionDecision",
    "ResultAggregator",
    "PartialResult",
    "AggregationStrategy",
    "ComplexCollaborationEngine",
    "CollaborationMode"
]
