"""
Circuit Breaker for SEC EDGAR Client (FN-020).

Prevents cascading failures and respects upstream downtime when SEC EDGAR experiences outages.
"""

import threading
import time
from collections.abc import Callable
from enum import Enum
from typing import TypeVar

from app.ingestion.edgar.models import EdgarCircuitBreakerOpenError

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """
    Thread-safe Circuit Breaker.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: float = 0.0
        self.state: CircuitState = CircuitState.CLOSED
        self._lock = threading.Lock()

    def get_state(self) -> CircuitState:
        with self._lock:
            if self.state == CircuitState.OPEN and time.monotonic() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
            return self.state

    def before_request(self) -> None:
        """Checks if a request is allowed. Raises EdgarCircuitBreakerOpenError if OPEN."""
        with self._lock:
            now = time.monotonic()
            if self.state == CircuitState.OPEN:
                if now - self.last_failure_time >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                else:
                    remaining = self.recovery_timeout - (now - self.last_failure_time)
                    raise EdgarCircuitBreakerOpenError(
                        f"Circuit breaker is OPEN. Upstream recovery remaining: {remaining:.1f}s"
                    )

    def record_success(self) -> None:
        """Records a successful call."""
        with self._lock:
            self.failure_count = 0
            self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Records a failed call."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()
            if self.state == CircuitState.HALF_OPEN or self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN

    def call(self, fn: Callable[..., T], *args: object, **kwargs: object) -> T:
        """Executes fn wrapped with circuit breaker protection."""
        self.before_request()
        try:
            result = fn(*args, **kwargs)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise
