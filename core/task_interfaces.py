"""任务执行接口层 - 解耦循环依赖

提供 ITaskExecutor 和 ITaskHandler 接口

依赖关系：
- multi_agent_system.py → task_interfaces.py
- handlers.py → task_interfaces.py
"""
from typing import Dict, Any, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod


@dataclass
class TaskContext:
    """任务上下文"""
    user_id: int
    agent_id: Optional[str] = None
    skill_name: Optional[str] = None
    metadata: Dict[str, Any] = None


class ITaskHandler(ABC):
    """任务处理器接口"""
    
    @abstractmethod
    async def execute(self, message: str, context: TaskContext) -> Dict[str, Any]:
        """执行任务"""
        pass


class ITaskExecutor(ABC):
    """任务执行器接口"""
    
    @abstractmethod
    async def execute_agent(self, message: str, user_id: int) -> Dict[str, Any]:
        """执行Agent任务"""
        pass


# 全局注册中心
_task_handlers: Dict[str, ITaskHandler] = {}
_task_executor: Optional[ITaskExecutor] = None


def register_handler(name: str, handler: ITaskHandler):
    """注册任务处理器"""
    _task_handlers[name] = handler


def get_handler(name: str) -> Optional[ITaskHandler]:
    """获取任务处理器"""
    return _task_handlers.get(name)


def register_executor(executor: ITaskExecutor):
    """注册任务执行器"""
    global _task_executor
    _task_executor = executor


def get_executor() -> Optional[ITaskExecutor]:
    """获取任务执行器"""
    return _task_executor