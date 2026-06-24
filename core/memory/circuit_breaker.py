"""Circuit breaker for compaction — MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3.

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
