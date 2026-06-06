"""
协作策略包 - 实现不同的多Agent协作模式

通过子模块按类别组织策略类，保证向后兼容的导入路径:
    from core.multi_agent_v2.orchestration.collaboration.strategies import StrategyName

子模块:
    base          - 基础数据类、基类、共享工具
    pipeline      - 流水线策略、递归分解、LLM反思
    master_worker - 主从策略
    review        - 评审策略、共识机制
    auction       - 拍卖策略、团队组建、复杂协作引擎
"""

from .base import (
    # 基础数据类
    CollaborationResult,
    CollaborationMode,
    # 策略基类
    BaseCollaborationStrategy,
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
    HybridStrategy,
    # LLM动态策略选择
    select_strategy_with_llm,
)

from .pipeline import (
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
)

from .master_worker import (
    MasterSlaveStrategy,
)

from .review import (
    ReviewStrategy,
    ConsensusMechanism,
)

from .auction import (
    AuctionStrategy,
    TeamMember,
    Team,
    Bid,
    AuctionResult,
    DynamicTeamForming,
    TaskAuction,
    ComplexCollaborationEngine,
)

__all__ = [
    # base
    "CollaborationResult",
    "CollaborationMode",
    "BaseCollaborationStrategy",
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
    "HybridStrategy",
    "select_strategy_with_llm",
    # pipeline
    "PipelineStrategy",
    "RecursiveTaskDecomposer",
    "ReflectionDecision",
    "StepResult",
    "ReflectionPrompt",
    "ReflectionResult",
    "ReflectionTriggerConfig",
    "ReflectionTrigger",
    "LLMReflection",
    "AdaptivePipelineWithReflection",
    # master_worker
    "MasterSlaveStrategy",
    # review
    "ReviewStrategy",
    "ConsensusMechanism",
    # auction
    "AuctionStrategy",
    "TeamMember",
    "Team",
    "Bid",
    "AuctionResult",
    "DynamicTeamForming",
    "TaskAuction",
    "ComplexCollaborationEngine",
]
