"""共享枚举定义

统一管理系统中使用的枚举类型，避免重复定义
"""

# ⚠️ DEPRECATED: 此模块未被核心流程使用


from enum import Enum


class TaskComplexity(Enum):
    """任务复杂度等级"""
    TRIVIAL = "trivial"          # 琐碎任务：单agent，单步
    SIMPLE = "simple"            # 简单任务（单步骤，低资源）
    MODERATE = "moderate"        # 中等任务（多步骤，中等资源）
    COMPLEX = "complex"          # 复杂任务（多步骤，高资源）
    VERY_COMPLEX = "very_complex" # 极复杂任务：5+个agent，强协作
    CRITICAL = "critical"        # 关键任务（高优先级，紧急处理）


class ResourceType(Enum):
    """资源类型"""
    CPU = "cpu"
    MEMORY = "memory"
    NETWORK = "network"
    STORAGE = "storage"
    API_QUOTA = "api_quota"


class ExecutionMode(Enum):
    """执行模式"""
    SINGLE = "single"            # 单agent执行
    PARALLEL = "parallel"        # 并发执行
    COLLABORATIVE = "collaborative"  # 协作执行
    HYBRID = "hybrid"           # 混合模式（先并发后协作）


class CollaborationStrategy(Enum):
    """协作策略"""
    SEQUENTIAL = "sequential"      # 顺序协作
    PARALLEL = "parallel"          # 并行协作
    HIERARCHICAL = "hierarchical"  # 分层协作
    CIRCULAR = "circular"          # 循环协作


class TaskPhase(Enum):
    """任务阶段"""
    ANALYSIS = "analysis"
    PLANNING = "planning"
    EXECUTION = "execution"
    REVIEW = "review"
    INTEGRATION = "integration"


