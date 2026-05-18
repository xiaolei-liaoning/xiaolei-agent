"""内部处理器函数模块 - 兼容层

此文件保持向后兼容性，将所有功能重新导出到 core.handlers 命名空间。

新的模块结构：
- context_memory: BFS上下文记忆管理
- persistence: 数据持久化
- workflow_handler: 工作流处理
- task_utils: 任务处理工具函数
- chat_handler: 闲聊处理
- single_step_handler: 单步任务处理
- multi_step_handler: 多步任务处理
- code_fallback: 代码生成降级
"""

from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)

# 全局状态引用（由 main.py 注入）
_dispatcher: Optional[Any] = None
_processor: Optional[Any] = None
_planner: Optional[Any] = None
_db_initialized: bool = False


def set_global_refs(
    dispatcher: Any,
    processor: Any,
    planner: Any,
    db_initialized: bool
) -> None:
    """设置全局引用，由 main.py 在初始化后调用。
    
    Args:
        dispatcher: SkillDispatcher 实例
        processor: ConcurrentTaskProcessor 实例
        planner: TaskPlanner 实例
        db_initialized: 数据库是否已初始化
    """
    global _dispatcher, _processor, _planner, _db_initialized
    _dispatcher = dispatcher
    _processor = processor
    _planner = planner
    _db_initialized = db_initialized


def _check_global_refs() -> None:
    """检查全局引用是否已初始化
    
    Raises:
        RuntimeError: 如果全局引用未初始化
    """
    if _dispatcher is None:
        raise RuntimeError(
            "系统尚未初始化完成，请确保 main.py 已启动并完成初始化。"
            "如果问题持续存在，请检查 SkillDispatcher 是否正确初始化。"
        )


def get_dispatcher():
    """获取全局 dispatcher"""
    return _dispatcher


def get_processor():
    """获取全局 processor"""
    return _processor


def get_planner():
    """获取全局 planner"""
    return _planner


def is_db_initialized() -> bool:
    """检查数据库是否已初始化"""
    return _db_initialized


# 从子模块导入所有功能
from .context_memory import (
    bfs_processor,
    short_term_memory,
    add_to_context_memory,
    get_context_for_llm,
    search_context_by_keywords,
)

from .persistence import (
    save_chat_history,
    save_task_log,
    get_system_prompt,
)

from .workflow_handler import handle_automation_workflow
from .code_fallback import try_code_generation as _try_code_generation
from .task_utils import convert_action_to_natural_language, process_task_with_processor
from .chat_handler import handle_chat
from .single_step_handler import handle_single_step
from .multi_step_handler import handle_multi_step, handle_multi_step_streaming

# 为了向后兼容，提供一些内部函数的别名
_convert_action_to_natural_language = convert_action_to_natural_language
_process_task_with_processor = process_task_with_processor

__all__ = [
    # 全局状态
    "set_global_refs",
    "_check_global_refs",
    "get_dispatcher",
    "get_processor",
    "get_planner",
    "is_db_initialized",
    "_dispatcher",
    "_processor",
    "_planner",
    "_db_initialized",
    
    # 上下文记忆
    "bfs_processor",
    "short_term_memory",
    "add_to_context_memory",
    "get_context_for_llm",
    "search_context_by_keywords",
    
    # 持久化
    "save_chat_history",
    "save_task_log",
    "get_system_prompt",
    
    # 处理器
    "handle_automation_workflow",
    "handle_chat",
    "handle_single_step",
    "handle_multi_step",
    "handle_multi_step_streaming",
    
    # 工具函数
    "_try_code_generation",
    "_convert_action_to_natural_language",
    "_process_task_with_processor",
]
