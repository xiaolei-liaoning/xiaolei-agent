"""任务执行接口层 - 解耦循环依赖

提供抽象接口，避免 handlers.py 和 multi_agent_system.py 之间的直接依赖
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


# 全局引用存储
_text_analyzer_agent: Optional[Any] = None
_handle_multi_step: Optional[Any] = None
_handle_single_step: Optional[Any] = None


# =============================================================================
# 抽象接口定义
# =============================================================================

class ITextAnalyzerAgent(ABC):
    """文本分析Agent接口"""
    
    @abstractmethod
    async def execute(self, message: str, user_id: int) -> Dict[str, Any]:
        """执行文本分析任务"""
        pass


class ITaskHandler(ABC):
    """任务处理器接口"""
    
    @abstractmethod
    async def handle_multi_step(self, message: str, user_id: int) -> Dict[str, Any]:
        """处理多步任务"""
        pass
    
    @abstractmethod
    async def handle_single_step(self, message: str, user_id: int, skill_name: str, agent_id: str) -> Dict[str, Any]:
        """处理单步任务"""
        pass


# =============================================================================
# 全局引用注入和获取
# =============================================================================

def set_task_handlers(
    text_analyzer_agent: Any,
    handle_multi_step_fn: Any,
    handle_single_step_fn: Any
) -> None:
    """注入全局引用
    
    Args:
        text_analyzer_agent: TextAnalyzerAgent 实例或类
        handle_multi_step_fn: handle_multi_step 函数
        handle_single_step_fn: handle_single_step 函数
    """
    global _text_analyzer_agent, _handle_multi_step, _handle_single_step
    _text_analyzer_agent = text_analyzer_agent
    _handle_multi_step = handle_multi_step_fn
    _handle_single_step = handle_single_step_fn
    logger.info("任务执行接口引用已注入")


def get_text_analyzer_agent() -> Any:
    """获取 TextAnalyzerAgent 引用"""
    if _text_analyzer_agent is None:
        raise RuntimeError("TextAnalyzerAgent 未初始化，请先调用 set_task_handlers()")
    return _text_analyzer_agent


def get_handle_multi_step() -> Any:
    """获取 handle_multi_step 函数"""
    if _handle_multi_step is None:
        raise RuntimeError("handle_multi_step 未初始化，请先调用 set_task_handlers()")
    return _handle_multi_step


def get_handle_single_step() -> Any:
    """获取 handle_single_step 函数"""
    if _handle_single_step is None:
        raise RuntimeError("handle_single_step 未初始化，请先调用 set_task_handlers()")
    return _handle_single_step


# =============================================================================
# 便捷函数（向后兼容）
# =============================================================================

async def execute_text_analyzer(message: str, user_id: int) -> Dict[str, Any]:
    """执行文本分析（便捷函数）"""
    agent = get_text_analyzer_agent()
    if hasattr(agent, 'execute'):
        return await agent.execute(message, user_id)
    elif callable(agent):
        return await agent(message, user_id)
    else:
        raise TypeError("TextAnalyzerAgent 既不是可调用对象也没有 execute 方法")


async def execute_multi_step(message: str, user_id: int) -> Dict[str, Any]:
    """执行多步任务（便捷函数）"""
    handler = get_handle_multi_step()
    return await handler(message, user_id)


async def execute_single_step(message: str, user_id: int, skill_name: str, agent_id: str) -> Dict[str, Any]:
    """执行单步任务（便捷函数）"""
    handler = get_handle_single_step()
    return await handler(message, user_id, skill_name, agent_id)
