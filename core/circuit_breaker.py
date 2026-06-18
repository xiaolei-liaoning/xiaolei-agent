"""熔断器模块 - 服务降级保护"""

import asyncio
import time
import logging
from enum import Enum
from typing import Optional, Callable, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"      # 正常
    OPEN = "open"          # 熔断
    HALF_OPEN = "half_open"  # 半开


@dataclass
class CircuitBreaker:
    """熔断器
    
    Args:
        failure_threshold: 失败阈值，达到后打开熔断器
        recovery_timeout: 恢复超时（秒），熔断器打开后多久尝试半开
        expected_exception: 期望的异常类型
    """
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    expected_exception: type = Exception
    
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: Optional[float] = field(default=None, init=False)
    _success_count: int = field(default=0, init=False)
    
    @property
    def state(self) -> CircuitState:
        """获取当前状态"""
        if self._state == CircuitState.OPEN:
            if self._last_failure_time and time.time() - self._last_failure_time > self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                logger.info("熔断器进入半开状态")
        return self._state
    
    def record_success(self) -> None:
        """记录成功"""
        self._failure_count = 0
        self._success_count += 1
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            logger.info("熔断器关闭")
    
    def record_failure(self) -> None:
        """记录失败"""
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(f"熔断器打开，失败次数: {self._failure_count}")
    
    def can_execute(self) -> bool:
        """是否可以执行"""
        return self.state != CircuitState.OPEN
    
    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """执行函数，带熔断保护"""
        if not self.can_execute():
            raise Exception("熔断器打开，拒绝执行")
        
        try:
            result = await func(*args, **kwargs)
            self.record_success()
            return result
        except self.expected_exception as e:
            self.record_failure()
            raise
