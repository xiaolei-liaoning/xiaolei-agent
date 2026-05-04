"""性能优化工具模块

包含：
- 超时和重试装饰器
- 资源监控（内存、CPU）
- 延迟加载装饰器
- 任务进度追踪
"""

import logging
import asyncio
import time
import os
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, Dict
from datetime import datetime

T = TypeVar('T')
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 超时和重试装饰器
# ---------------------------------------------------------------------------

class RetryConfig:
    """重试配置"""
    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 10.0,
        backoff_factor: float = 2.0
    ):
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor


def async_retry(config: Optional[RetryConfig] = None):
    """异步函数重试装饰器"""
    if config is None:
        config = RetryConfig()
    
    def decorator(func: Callable[..., T]):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            delay = config.initial_delay
            
            for attempt in range(config.max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(
                        f"函数 {func.__name__} 第 {attempt + 1}/{config.max_attempts} 次尝试失败: {e}"
                    )
                    
                    if attempt < config.max_attempts - 1:
                        await asyncio.sleep(delay)
                        delay = min(delay * config.backoff_factor, config.max_delay)
            
            raise last_exception
        return wrapper
    return decorator


def async_with_timeout(timeout: float = 30.0):
    """异步函数超时装饰器"""
    def decorator(func: Callable[..., T]):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
            except asyncio.TimeoutError:
                logger.error(f"函数 {func.__name__} 执行超时 ({timeout}s)")
                raise
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# 资源监控
# ---------------------------------------------------------------------------

class ResourceMonitor:
    """资源监控器"""
    
    def __init__(self):
        self.enabled = os.getenv("ENABLE_RESOURCE_MONITOR", "true").lower() == "true"
        self.memory_warning_threshold = float(os.getenv("MEMORY_WARNING_THRESHOLD", "0.8"))
        self.cpu_warning_threshold = float(os.getenv("CPU_WARNING_THRESHOLD", "0.9"))
        self._last_check = time.time()
        self._check_interval = 60  # 每秒检查一次
    
    def check_resources(self) -> Dict[str, Any]:
        """检查资源使用情况"""
        if not self.enabled:
            return {"status": "ok", "monitor": "disabled"}
        
        now = time.time()
        if now - self._last_check < self._check_interval:
            return {"status": "ok", "message": "throttled"}
        
        self._last_check = now
        
        result = {"status": "ok", "timestamp": datetime.now().isoformat()}
        
        # 检查内存
        try:
            import psutil
            process = psutil.Process()
            mem_info = process.memory_info()
            mem_percent = process.memory_percent()
            
            result["memory"] = {
                "rss_mb": mem_info.rss / (1024 * 1024),
                "percent": mem_percent,
                "status": "warning" if mem_percent > self.memory_warning_threshold * 100 else "ok"
            }
            
            if mem_percent > self.memory_warning_threshold * 100:
                logger.warning(f"内存使用率过高: {mem_percent:.1f}%")
        
        except ImportError:
            logger.debug("psutil 未安装，跳过资源检查")
        except Exception as e:
            logger.debug(f"资源检查失败: {e}")
        
        return result


# ---------------------------------------------------------------------------
# 延迟加载
# ---------------------------------------------------------------------------

class LazyLoader:
    """延迟加载器"""
    
    def __init__(self):
        self._cache = {}
        self._lock = asyncio.Lock()
    
    async def get_or_load(self, key: str, loader: Callable[..., T]) -> T:
        """获取或加载资源"""
        async with self._lock:
            if key in self._cache:
                return self._cache[key]
            
            value = await loader() if asyncio.iscoroutinefunction(loader) else loader()
            self._cache[key] = value
            return value
    
    def clear(self, key: Optional[str] = None):
        """清除缓存"""
        if key:
            self._cache.pop(key, None)
        else:
            self._cache.clear()


# ---------------------------------------------------------------------------
# 进度追踪
# ---------------------------------------------------------------------------

class ProgressTracker:
    """进度追踪器（用于用户反馈）"""
    
    def __init__(self):
        self._callbacks = []
    
    def add_callback(self, callback: Callable[[str, str, int, int], None]):
        """添加进度回调函数"""
        self._callbacks.append(callback)
    
    async def update_progress(
        self,
        phase: str,
        message: str,
        current: int,
        total: int
    ):
        """更新进度"""
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(phase, message, current, total)
                else:
                    callback(phase, message, current, total)
            except Exception as e:
                logger.error(f"进度回调失败: {e}")


# ---------------------------------------------------------------------------
# 全局实例
# ---------------------------------------------------------------------------

_resource_monitor = ResourceMonitor()
_lazy_loader = LazyLoader()
_progress_tracker = ProgressTracker()


def get_resource_monitor() -> ResourceMonitor:
    return _resource_monitor

def get_lazy_loader() -> LazyLoader:
    return _lazy_loader

def get_progress_tracker() -> ProgressTracker:
    return _progress_tracker

