"""Memory子系统 - 记忆管理

包含：
- 短期记忆
- 向量记忆
- 记忆优化
- 自我进化引擎
"""

from .short_term_memory import *
# V2 可直接 from core.memory.short_term_memory import ShortTermMemoryManager
# 向量记忆/自进化通过 memory_middleware 懒加载（Chromadb 启动较慢）
