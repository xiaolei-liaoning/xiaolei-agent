"""服务接口定义"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class ServiceInterface(ABC):
    """服务接口基类"""
    
    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass
    
    @abstractmethod
    async def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        pass


class ISandboxExecutor(ABC):
    """沙箱执行器接口"""
    
    @abstractmethod
    async def execute(self, code: str, language: str = "python") -> Dict[str, Any]:
        """执行代码"""
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """清理资源"""
        pass


class IClarificationService(ABC):
    """澄清服务接口"""
    
    @abstractmethod
    async def request_clarification(self, question: str, context: Dict[str, Any]) -> Optional[str]:
        """请求澄清"""
        pass
    
    @abstractmethod
    async def get_clarification_status(self, request_id: str) -> Dict[str, Any]:
        """获取澄清状态"""
        pass


class CacheService(ServiceInterface):
    """缓存服务接口"""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        pass


class QueueService(ServiceInterface):
    """队列服务接口"""
    
    @abstractmethod
    async def enqueue(self, queue_name: str, message: Dict[str, Any]) -> bool:
        pass
    
    @abstractmethod
    async def dequeue(self, queue_name: str) -> Optional[Dict[str, Any]]:
        pass
