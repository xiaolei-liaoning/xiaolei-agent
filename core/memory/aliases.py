"""记忆系统兼容层 - 修复导入路径"""

# 创建别名以兼容旧的导入方式
from .short_term_memory import ShortTermMemoryManager as ShortTermMemory
from .vector_memory import VectorMemoryStore as VectorMemory
from .memory_optimizer import MemoryOptimizer

# 重导出所有内容
__all__ = [
    'ShortTermMemory',  # 别名
    'ShortTermMemoryManager',
    'VectorMemory',  # 别名
    'VectorMemoryStore',
    'MemoryOptimizer',
]
