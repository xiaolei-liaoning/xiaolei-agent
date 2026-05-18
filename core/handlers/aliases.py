"""Handlers 兼容层 - 修复导入路径"""

# 修复类名不匹配问题
from .context_memory import ShortTermMemoryManager as ShortTermMemory
from .context_memory import get_bfs_processor
from .code_fallback import try_code_generation

# 重导出
__all__ = [
    'ShortTermMemory',  # 别名
    'ShortTermMemoryManager',
    'get_bfs_processor',
    'try_code_generation',
]
