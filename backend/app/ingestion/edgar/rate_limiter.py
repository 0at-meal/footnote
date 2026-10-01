"""
Thread-safe Token Bucket Rate Limiter for SEC EDGAR (FN-020).

SEC fair-access guidance restricts automated tools to no more than 10 requests per second.
This implementation provides a strict token bucket to enforce this limit.
"""

import threading
import time

from app.ingestion.edgar.models import EdgarRateLimitError


class TokenBucketRateLimiter:
    """
    Thread-safe Token Bucket rate limiter.
    
    Default rate is 10.0 requests per second with capacity of 10 tokens.
    """

    def __init__(self, rate: float = 10.0, capacity: float = 10.0) -> None:
        """
        Args:
            rate: Tokens added per second.
            capacity: Maximum burst capacity in tokens.
        """
        self.rate = float(rate)
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.last_update = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now

    def acquire(self, tokens: float = 1.0, timeout: float | None = 5.0) -> bool:
        """
        Acquires tokens from the bucket, sleeping if necessary up to `timeout` seconds.

        Args:
            tokens: Number of tokens to acquire (default 1.0).
            timeout: Maximum seconds to block waiting for tokens. If None, blocks indefinitely.
                     If 0.0, non-blocking check.

        Returns:
            True if tokens were acquired.

        Raises:
            EdgarRateLimitError: If timeout expires before tokens are available.
        """
        start = time.monotonic()
        while True:
            with self._lock:
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True
                
                deficit = tokens - self.tokens
                wait_time = deficit / self.rate

            # Check timeout
            if timeout is not None:
                elapsed = time.monotonic() - start
                if elapsed + wait_time > timeout:
                    raise EdgarRateLimitError(
                        f"Rate limit exceeded: waiting {wait_time:.2f}s exceeds timeout {timeout:.2f}s"
                    )

            # Sleep outside lock for wait_time
            sleep_step = min(wait_time, 0.05) if timeout is not None else wait_time
            time.sleep(sleep_step)

    def try_acquire(self, tokens: float = 1.0) -> bool:
        """Non-blocking token acquisition. Returns True if acquired, False otherwise."""
        with self._lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
