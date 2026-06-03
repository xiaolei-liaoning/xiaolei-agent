"""
CircuitBreaker — 熔断器

3 态状态机：CLOSED → OPEN（失败次数超限）→ HALF_OPEN（恢复超时）→ CLOSED
防止故障扩散，保护 LLM provider 和后端服务。

3 种策略：
- COUNT_BASED: 基于连续失败次数
- RATE_BASED: 基于失败率（滑动窗口）
- TIME_BASED: 基于响应时间超阈值
"""

import time
import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"         # 正常运行
    OPEN = "open"             # 熔断打开
    HALF_OPEN = "half_open"   # 半开，允许试探


class TripStrategy(Enum):
    COUNT_BASED = "count"     # 连续失败次数
    RATE_BASED = "rate"       # 失败率（滑动窗口）
    TIME_BASED = "time"       # 响应时间超阈值


class CircuitBreaker:
    """熔断器

    用法:
        cb = CircuitBreaker(name="glm_api", threshold=5, recovery_timeout=60)
        if await cb.can_execute():
            try:
                result = await call_api()
                cb.record_success()
            except Exception as e:
                cb.record_failure()
        else:
            # 走降级逻辑
    """

    def __init__(
        self,
        name: str = "default",
        strategy: TripStrategy = TripStrategy.COUNT_BASED,
        threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3,
        rate_threshold: float = 0.5,
        time_threshold_ms: float = 10000.0,
        window_seconds: float = 60.0,
    ):
        self.name = name
        self.strategy = strategy
        self.threshold = threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.rate_threshold = rate_threshold
        self.time_threshold_ms = time_threshold_ms
        self.window_seconds = window_seconds

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.half_open_calls = 0

        # 滑动窗口记录
        self._window: list = []  # (timestamp, success: bool, duration_ms: float)

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    async def can_execute(self) -> bool:
        """判断是否可以执行"""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # 检查是否超过恢复超时
            if self.last_failure_time and (time.time() - self.last_failure_time > self.recovery_timeout):
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                logger.info("熔断器 %s OPEN → HALF_OPEN", self.name)
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            return self.half_open_calls < self.half_open_max_calls

        return False

    def record_success(self, duration_ms: float = 0) -> None:
        """记录成功"""
        self._window.append((time.time(), True, duration_ms))
        self._prune_window()

        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max_calls:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                logger.info("熔断器 %s HALF_OPEN → CLOSED（恢复）", self.name)
        elif self.state == CircuitState.CLOSED:
            self.failure_count = max(0, self.failure_count - 1)  # 成功一次减少一次失败计数

    def record_failure(self, duration_ms: float = 0) -> None:
        """记录失败"""
        self._window.append((time.time(), False, duration_ms))
        self._prune_window()
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            # 半开状态下失败立即回到 OPEN
            self.state = CircuitState.OPEN
            logger.warning("熔断器 %s HALF_OPEN → OPEN（试探失败）", self.name)
            return

        self.failure_count += 1
        if self._should_trip():
            self.state = CircuitState.OPEN
            logger.warning("熔断器 %s CLOSED → OPEN（%s策略触发）",
                          self.name, self.strategy.value)

    def _should_trip(self) -> bool:
        """判断是否应该熔断"""
        if self.strategy == TripStrategy.COUNT_BASED:
            return self.failure_count >= self.threshold

        elif self.strategy == TripStrategy.RATE_BASED:
            total = len(self._window)
            if total < self.threshold:
                return False
            failures = sum(1 for _, s, _ in self._window if not s)
            rate = failures / total if total > 0 else 0
            return rate >= self.rate_threshold

        elif self.strategy == TripStrategy.TIME_BASED:
            slow = sum(1 for _, _, d in self._window if d > self.time_threshold_ms)
            total = len(self._window)
            if total < self.threshold:
                return False
            return (slow / total) >= self.rate_threshold

        return False

    def _prune_window(self) -> None:
        """清理窗口外的旧记录"""
        now = time.time()
        self._window = [(t, s, d) for t, s, d in self._window
                       if now - t < self.window_seconds]

    def get_stats(self) -> dict:
        """获取统计"""
        total = len(self._window)
        failures = sum(1 for _, s, _ in self._window if not s)
        return {
            "name": self.name,
            "state": self.state.value,
            "strategy": self.strategy.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "half_open_calls": self.half_open_calls,
            "window_total": total,
            "window_failures": failures,
            "last_failure_time": self.last_failure_time,
            "is_open": self.is_open,
        }

    def reset(self) -> None:
        """重置熔断器"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.half_open_calls = 0
        self._window.clear()


class CircuitBreakerRegistry:
    """熔断器注册表 — 统一管理所有熔断器"""

    _instance: Optional["CircuitBreakerRegistry"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._breakers: dict = {}

    def get_or_create(self, name: str, **kwargs) -> CircuitBreaker:
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name=name, **kwargs)
        return self._breakers[name]

    def get(self, name: str) -> Optional[CircuitBreaker]:
        return self._breakers.get(name)

    def get_all_stats(self) -> dict:
        return {n: cb.get_stats() for n, cb in self._breakers.items()}

    def reset_all(self) -> None:
        for cb in self._breakers.values():
            cb.reset()


def get_circuit_breaker(name: str = "default", **kwargs) -> CircuitBreaker:
    return CircuitBreakerRegistry().get_or_create(name, **kwargs)
