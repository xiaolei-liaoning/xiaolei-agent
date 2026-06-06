"""
Infrastructure — 基础设施层

包含项目支撑性基础设施模块：
- WorktreeManager: git worktree 隔离管理器
"""
from .worktree_manager import WorktreeManager

__all__ = ["WorktreeManager"]
