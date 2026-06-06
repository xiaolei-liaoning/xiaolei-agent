"""
协作策略包 - 实现不同的多Agent协作模式

通过子模块按类别组织策略类，保证向后兼容的导入路径:
    from core.multi_agent_v2.orchestration.collaboration.strategies import StrategyName

子模块:
    base          - 基础数据类、基类、共享工具
    pipeline      - 流水线策略、递归分解、LLM反思

注意：以下类已废弃（[DEPRECATED]），仅保留向后兼容：
  - BaseCollaborationStrategy  -> 请使用具体策略类
  - PipelineStrategy          -> 请使用 AdaptivePipelineWithReflection
  - HybridStrategy            -> 动态策略选择由 select_strategy_with_llm 接管
"""

from .base import (
    # 基础数据类
    CollaborationResult,
    CollaborationMode,
    # 策略基类
    BaseCollaborationStrategy,  # [DEPRECATED]
    # 知识共享
    KnowledgeSharing,
    # 结果聚合
    AggregationStrategy,
    PartialResult,
    AggregationConfig,
    AggregationResult,
    SimpleAggregator,
    WeightedVoteAggregator,
    HierarchicalAggregator,
    LLMAggregator,
    ResultAggregator,
    MasterAgentAggregator,
    # 混合策略
    HybridStrategy,             # [DEPRECATED]
    # LLM动态策略选择
    select_strategy_with_llm,
)

from .pipeline import (
    PipelineStrategy,           # [DEPRECATED]
    RecursiveTaskDecomposer,
    ReflectionDecision,
    StepResult,
    ReflectionPrompt,
    ReflectionResult,
    ReflectionTriggerConfig,
    ReflectionTrigger,
    LLMReflection,
    AdaptivePipelineWithReflection,
)

__all__ = [
    # base
    "CollaborationResult",
    "CollaborationMode",
    "BaseCollaborationStrategy",  # [DEPRECATED]
    "KnowledgeSharing",
    "AggregationStrategy",
    "PartialResult",
    "AggregationConfig",
    "AggregationResult",
    "SimpleAggregator",
    "WeightedVoteAggregator",
    "HierarchicalAggregator",
    "LLMAggregator",
    "ResultAggregator",
    "MasterAgentAggregator",
    "HybridStrategy",             # [DEPRECATED]
    "select_strategy_with_llm",
    # pipeline
    "PipelineStrategy",            # [DEPRECATED]
    "RecursiveTaskDecomposer",
    "ReflectionDecision",
    "StepResult",
    "ReflectionPrompt",
    "ReflectionResult",
    "ReflectionTriggerConfig",
    "ReflectionTrigger",
    "LLMReflection",
    "AdaptivePipelineWithReflection",
]
