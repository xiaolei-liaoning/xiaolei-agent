"""Circuit breaker for compaction — MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3.

V1→V2: V1 熔断器。由 ContextCompactor._circuit_breaker 持有，在 compact()
  每次调用时检查 is_tripped()，成功后 record_success()，失败后 record_failure()。
  V2 的 ContextBudgetManager 通过 ContextCompactor 间接使用此熔断器。

保留原因: 防止上下文超限不可恢复时不断进行压缩尝试。V2 的 entry-level 压缩
  (tool_results 选择+摘要) 没有自己的熔断器，依赖 V1 的此熔断器来保护
  message-level 压缩不陷入死循环。

Prevents hammering the API with doomed compaction attempts when context
is irrecoverably over the limit. Resets on success.

Ponytail: standalone class instead of inline in react_compact or l3,
because both ReactCompact and L3 use it (DRY).
"""

import logging
import time

logger = logging.getLogger(__name__)

MAX_CONSECUTIVE_FAILURES = 3
COOLDOWN_SECONDS = 300  # 5min cooldown before retrying after trip


class CircuitBreaker:
    def __init__(self, max_failures: int = MAX_CONSECUTIVE_FAILURES):
        self._max_failures = max_failures
        self._consecutive_failures = 0
        self._tripped_at: float | None = None
        self._total_failures = 0

    def is_tripped(self) -> bool:
        if self._consecutive_failures >= self._max_failures:
            if self._tripped_at is None:
                self._tripped_at = time.time()
            elapsed = time.time() - self._tripped_at
            if elapsed > COOLDOWN_SECONDS:
                logger.debug("Circuit breaker: cooldown elapsed, resetting")
                self._consecutive_failures = 0
                self._tripped_at = None
                return False
            return True
        return False

    def record_success(self) -> None:
        was_tripped = self._consecutive_failures >= self._max_failures
        self._consecutive_failures = 0
        self._tripped_at = None
        if was_tripped:
            logger.info("Circuit breaker: reset after success")

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        self._total_failures += 1
        if self._consecutive_failures >= self._max_failures:
            logger.warning(
                "Circuit breaker: tripped (%d consecutive failures)",
                self._consecutive_failures,
            )

    def sync_record_success(self) -> None:
        """同步别名 — 与 core/circuit_breaker.py 接口对齐（f3a1905 引入了 sync_ 前缀但漏了这份）"""
        self.record_success()

    def sync_record_failure(self) -> None:
        """同步别名 — 与 core/circuit_breaker.py 接口对齐"""
        self.record_failure()

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def get_stats(self) -> dict:
        return {
            "consecutive_failures": self._consecutive_failures,
            "total_failures": self._total_failures,
            "is_tripped": self.is_tripped(),
            "max_failures": self._max_failures,
        }
