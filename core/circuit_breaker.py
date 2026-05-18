"""统一三态熔断器 — 共享实现

被以下模块引用（全部 import）：
  core/tasks/task_scheduler.py
  core/tasks/concurrent_processor.py

  core/security/error_handler.py

  agent_group_executor.py
"""

import time
import logging
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CircuitBreakerStrategy(Enum):
    """熔断策略"""
    COUNT_BASED = "count_based"   # 基于失败次数（默认）
    RATE_BASED = "rate_based"     # 基于失败率
    TIME_BASED = "time_based"     # 基于时间窗口


class CircuitBreaker:
    """三态熔断器：CLOSED / OPEN / HALF_OPEN

    支持三种熔断策略：
    - COUNT_BASED: 连续失败 N 次后打开
    - RATE_BASED:  失败率达到阈值后打开
    - TIME_BASED:  时间窗口内失败 N 次后打开

    用法：
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout=30)
        if cb.is_allowed():
            try:    ...; cb.record_success()
            except: cb.record_failure()
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0,
                 name: str = "",
                 strategy: CircuitBreakerStrategy = CircuitBreakerStrategy.COUNT_BASED,
                 failure_rate_threshold: float = 0.5):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_rate_threshold = failure_rate_threshold
        self.name = name or ""
        self.strategy = strategy

        self._state: str = self.CLOSED
        self._failures: int = 0
        self._successes: int = 0
        self._last_failure_time: float = 0.0
        self._last_success_time: float = 0.0
        self._half_open_calls: int = 0
        self.half_open_max_calls: int = 3

    # ── 状态管理 ──────────────────────────────────────────────────────

    @property
    def state(self) -> str:
        """获取当前状态，自动触发 CLOSED → HALF_OPEN 转换"""
        if self._state == self.OPEN:
            if time.time() - self._last_failure_time > self.recovery_timeout:
                self._state = self.HALF_OPEN
                self._half_open_calls = 0
                logger.info("熔断器 %s 进入半开状态", self.name)
        return self._state

    def get_state(self) -> Dict[str, Any]:
        """获取熔断器状态快照"""
        return {
            "is_open": self._state == self.OPEN,
            "state": self._state,
            "failure_count": self._failures,
            "success_count": self._successes,
            "last_failure_time": self._last_failure_time,
            "last_success_time": self._last_success_time,
            "half_open_attempts": self._half_open_calls,
            "strategy": self.strategy.value,
        }

    # ── 接口A: is_allowed() — task_scheduler / agent_group_executor ──

    def is_allowed(self) -> bool:
        """检查是否允许请求通过"""
        if self.state == self.OPEN:
            return False
        if self._state == self.HALF_OPEN:
            if self._half_open_calls >= self.half_open_max_calls:
                return False
            self._half_open_calls += 1
            return True
        return True

    # ── 接口B: is_open() — concurrent_processor / intelligent_scheduler ──

    @property
    def is_open(self) -> bool:
        """熔断器是否打开（属性访问）"""
        return not self.is_allowed()

    def is_open_method(self, tool_name: str = "") -> bool:
        """熔断器是否打开（方法调用，兼容 tool_gateway 接口）"""
        return not self.is_allowed()

    def can_execute(self, tool_name: str = "") -> bool:
        return self.is_allowed()

    # ── 记录接口 ──────────────────────────────────────────────────────

    def record_success(self, tool_name: str = "") -> None:
        """记录一次成功"""
        self._successes += 1
        self._last_success_time = time.time()

        if self._state == self.HALF_OPEN:
            self._half_open_calls -= 1
            if self._half_open_calls <= 0:
                self._state = self.CLOSED
                self._failures = 0
                logger.info("熔断器 %s 已关闭", self.name)
        else:
            self._state = self.CLOSED
            self._failures = 0

    def record_failure(self, tool_name: str = "") -> None:
        """记录一次失败，根据策略决定是否打开熔断器"""
        self._failures += 1
        self._last_failure_time = time.time()
        self._successes = 0

        if self.strategy == CircuitBreakerStrategy.COUNT_BASED:
            self._check_count_based()
        elif self.strategy == CircuitBreakerStrategy.RATE_BASED:
            self._check_rate_based()
        elif self.strategy == CircuitBreakerStrategy.TIME_BASED:
            self._check_time_based()

    def _check_count_based(self):
        if self._failures >= self.failure_threshold:
            self._state = self.OPEN
            logger.warning("熔断器 %s 打开 (失败 %d/%d)",
                          self.name, self._failures, self.failure_threshold)

    def _check_rate_based(self):
        total = self._failures + self._successes
        if total >= self.failure_threshold:
            rate = self._failures / total
            if rate >= self.failure_rate_threshold:
                self._state = self.OPEN
                logger.warning("熔断器 %s 打开 (失败率 %.0f%%)",
                              self.name, rate * 100)

    def _check_time_based(self):
        window = 60.0
        if time.time() - self._last_failure_time < window:
            if self._failures >= self.failure_threshold:
                self._state = self.OPEN
                logger.warning("熔断器 %s 打开 (%.0fs 内失败 %d 次)",
                              self.name, window, self._failures)

    def reset(self) -> None:
        """重置熔断器为关闭状态"""
        self._state = self.CLOSED
        self._failures = 0
        self._successes = 0
        self._last_failure_time = 0.0
        self._last_success_time = 0.0
        self._half_open_calls = 0
