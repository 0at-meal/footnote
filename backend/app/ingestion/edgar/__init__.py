"""
SEC EDGAR ingestion package (FN-020).
"""

from app.ingestion.edgar.circuit_breaker import CircuitBreaker, CircuitState
from app.ingestion.edgar.client import EdgarClient
from app.ingestion.edgar.models import (
    EdgarCircuitBreakerOpenError,
    EdgarClientError,
    EdgarCompanyNotFoundError,
    EdgarFilingNotFoundError,
    EdgarRateLimitError,
    FilingDocument,
    FilingExhibit,
    FilingRef,
    ForeignFilerUnsupportedError,
)
from app.ingestion.edgar.rate_limiter import TokenBucketRateLimiter

__all__ = [
    "CircuitBreaker",
    "CircuitState",
    "EdgarCircuitBreakerOpenError",
    "EdgarClient",
    "EdgarClientError",
    "EdgarCompanyNotFoundError",
    "EdgarFilingNotFoundError",
    "EdgarRateLimitError",
    "FilingDocument",
    "FilingExhibit",
    "FilingRef",
    "ForeignFilerUnsupportedError",
    "TokenBucketRateLimiter",
]
