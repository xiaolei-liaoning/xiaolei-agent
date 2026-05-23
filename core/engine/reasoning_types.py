"""深度思考引擎 - 类型定义与共享工具

包含枚举类型和全局单例辅助函数。
"""
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class ThinkingDepth(Enum):
    """思考深度级别枚举"""
    QUICK = "quick"          # Level 1: 快速模式
    STANDARD = "standard"    # Level 2: 标准模式
    DEEP = "deep"            # Level 3: 深度模式


class TaskComplexity(Enum):
    """任务复杂度级别"""
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class ImpactLevel(Enum):
    """影响程度级别"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# 全局单例
_rag_engine = None
_short_term_memory = None


def _get_rag_engine():
    global _rag_engine
    if _rag_engine is None:
        try:
            from ..search.rag_search_engine import get_rag_engine
            _rag_engine = get_rag_engine()
        except Exception as e:
            logger.warning("RAG引擎初始化失败: %s", e)
    return _rag_engine


def _get_short_term_memory():
    global _short_term_memory
    if _short_term_memory is None:
        try:
            from ..handlers import short_term_memory
            _short_term_memory = short_term_memory
        except Exception as e:
            logger.warning("短时记忆管理器初始化失败: %s", e)
    return _short_term_memory
