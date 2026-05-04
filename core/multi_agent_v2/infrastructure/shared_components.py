"""
SharedComponents - 多Agent系统共享组件
避免每个Agent都重复初始化核心组件
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
import sys

logger = logging.getLogger(__name__)


class SharedComponents:
    """共享组件 - 所有Agent共用
    
    单例模式，只初始化一次
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化（只执行一次）"""
        if self._initialized:
            return
        
        logger.info("Initializing SharedComponents...")
        
        # 这里只初始化占位符，真正的组件按需加载
        # 避免启动时加载所有依赖
        self._llm_facade = None
        self._tool_gateway = None
        self._redis_storage = None
        self._observability = None
        
        self._init_stats = {
            "llm_facade_initialized": False,
            "tool_gateway_initialized": False,
            "redis_storage_initialized": False,
            "observability_initialized": False,
        }
        
        self._initialized = True
        logger.info("SharedComponents initialized (lazy mode)")
    
    @property
    def llm_facade(self):
        """LLM统一接口 - 按需初始化"""
        if self._llm_facade is None:
            logger.info("Lazy initializing LLMFacade...")
            try:
                from core.multi_agent_v2.infrastructure.llm.llm_facade import LLMFacade
                self._llm_facade = LLMFacade()
                self._init_stats["llm_facade_initialized"] = True
            except Exception as e:
                logger.warning(f"Failed to init LLMFacade: {e}")
                self._llm_facade = MockLLMFacade()
        return self._llm_facade
    
    @property
    def tool_gateway(self):
        """工具网关 - 按需初始化"""
        if self._tool_gateway is None:
            logger.info("Lazy initializing ToolGateway...")
            try:
                from core.multi_agent_v2.infrastructure.tools.tool_gateway import ToolGateway
                self._tool_gateway = ToolGateway()
                self._init_stats["tool_gateway_initialized"] = True
            except Exception as e:
                logger.warning(f"Failed to init ToolGateway: {e}")
                self._tool_gateway = MockToolGateway()
        return self._tool_gateway
    
    @property
    def redis_storage(self):
        """Redis存储 - 按需初始化"""
        if self._redis_storage is None:
            logger.info("Lazy initializing RedisStorage...")
            try:
                from core.multi_agent_v2.infrastructure.persistence.redis_storage import RedisStorage
                self._redis_storage = RedisStorage()
                self._init_stats["redis_storage_initialized"] = True
            except Exception as e:
                logger.warning(f"Failed to init RedisStorage: {e}")
                self._redis_storage = MockRedisStorage()
        return self._redis_storage
    
    @property
    def observability(self):
        """可观测性 - 按需初始化"""
        if self._observability is None:
            logger.info("Lazy initializing ObservabilityManager...")
            try:
                from core.multi_agent_v2.infrastructure.observability.observability_manager import ObservabilityManager
                self._observability = ObservabilityManager()
                self._init_stats["observability_initialized"] = True
            except Exception as e:
                logger.warning(f"Failed to init ObservabilityManager: {e}")
                self._observability = MockObservability()
        return self._observability
    
    def get_init_stats(self) -> Dict[str, Any]:
        """获取初始化统计"""
        return self._init_stats.copy()
    
    def get_memory_usage(self) -> Dict[str, int]:
        """获取内存占用估算"""
        # 估算各组件的内存占用
        return {
            "llm_facade_mb": 50 if self._init_stats["llm_facade_initialized"] else 0,
            "tool_gateway_mb": 30 if self._init_stats["tool_gateway_initialized"] else 0,
            "redis_storage_mb": 20 if self._init_stats["redis_storage_initialized"] else 0,
            "observability_mb": 10 if self._init_stats["observability_initialized"] else 0,
            "total_mb": sum([
                50 if self._init_stats["llm_facade_initialized"] else 0,
                30 if self._init_stats["tool_gateway_initialized"] else 0,
                20 if self._init_stats["redis_storage_initialized"] else 0,
                10 if self._init_stats["observability_initialized"] else 0,
            ])
        }


# Mock实现 - 当真实组件加载失败时使用
class MockLLMFacade:
    """Mock LLM Facade"""
    async def generate(self, prompt):
        return {"text": "Mock LLM response"}


class MockToolGateway:
    """Mock Tool Gateway"""
    async def execute(self, tool_name, params):
        return {"status": "success", "tool": tool_name}


class MockRedisStorage:
    """Mock Redis Storage"""
    async def get(self, key):
        return None
    async def set(self, key, value, ttl=None):
        pass
    async def delete(self, key):
        pass


class MockObservability:
    """Mock Observability"""
    def record_metric(self, name, value):
        pass
    def record_event(self, name, data):
        pass


# 快捷获取函数
def get_shared() -> SharedComponents:
    """获取共享组件实例"""
    return SharedComponents()


# 内存计算器
class MemoryCalculator:
    """计算内存占用"""
    
    @staticmethod
    def estimate_object_size(obj) -> int:
        """估算对象内存占用（字节）"""
        import sys
        try:
            return sys.getsizeof(obj)
        except:
            return 0
    
    @staticmethod
    def format_size(bytes_size: int) -> str:
        """格式化字节大小为可读字符串"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024:
                return f"{bytes_size:.2f}{unit}"
            bytes_size /= 1024
        return f"{bytes_size:.2f}TB"
