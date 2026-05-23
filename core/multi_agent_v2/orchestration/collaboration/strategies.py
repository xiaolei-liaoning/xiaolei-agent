"""
协作策略 - 实现不同的多Agent协作模式 (Facade)

此模块已拆分为 strategies/ 包。本文件作为向后兼容的 facade，
保留原有的导入路径:
    from core.multi_agent_v2.orchestration.collaboration.strategies import StrategyName
"""

from .strategies import *  # noqa: F401, F403

from .strategies import (  # noqa: F401, F811
    # base
    CollaborationResult,
    CollaborationMode,
    BaseCollaborationStrategy,
    KnowledgeSharing,
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
    HybridStrategy,
    select_strategy_with_llm,
    # pipeline
    PipelineStrategy,
    RecursiveTaskDecomposer,
    ReflectionDecision,
    StepResult,
    ReflectionPrompt,
    ReflectionResult,
    ReflectionTriggerConfig,
    ReflectionTrigger,
    LLMReflection,
    AdaptivePipelineWithReflection,
    # master_worker
    MasterSlaveStrategy,
    # review
    ReviewStrategy,
    ConsensusMechanism,
    # auction
    AuctionStrategy,
    TeamMember,
    Team,
    Bid,
    AuctionResult,
    DynamicTeamForming,
    TaskAuction,
    ComplexCollaborationEngine,
)
