"""工作流兼容层 - 修复导入路径"""

from .bfs_processor import BFSTextProcessor as BFSProcessor

__all__ = [
    'BFSProcessor',
]