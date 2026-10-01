"""
Data models and exceptions for SEC EDGAR Client (FN-020).

Enforces:
- Typed FilingRef schema per FN-020 spec: (cik, accession, form, period, filed_at, primary_url, exhibits).
- Invariant I3: Foreign filers return explicit unsupported error.
"""

from pydantic import BaseModel, Field


class FilingExhibit(BaseModel):
    """Metadata representing an exhibit attached to an SEC EDGAR filing."""

    exhibit_number: str = Field(..., description="Exhibit identifier (e.g. 'EX-99.1', 'EX-21.1')")
    filename: str = Field(..., description="Exhibit document filename (e.g. 'ex99-1.htm')")
    description: str | None = Field(default=None, description="Document description string")
    url: str | None = Field(default=None, description="Full SEC EDGAR URL to the exhibit")


class FilingRef(BaseModel):
    """
    Authoritative reference to an SEC filing from EDGAR Submissions API (FN-020).
    """

    cik: str = Field(..., description="10-digit zero-padded CIK string")
    accession: str = Field(..., description="SEC accession number (e.g. '0000320193-23-000106')")
    form: str = Field(..., description="SEC form type (e.g. '10-K', '10-Q', '10-K/A', '8-K')")
    period: str | None = Field(default=None, description="Report period end date (YYYY-MM-DD)")
    filed_at: str = Field(..., description="Filing acceptance/filing date (YYYY-MM-DD)")
    primary_url: str = Field(..., description="Full SEC EDGAR URL to primary document")
    primary_document: str = Field(..., description="Primary document filename")
    exhibits: list[FilingExhibit] = Field(default_factory=list, description="List of exhibits")
    is_amendment: bool = Field(default=False, description="True if form is an amendment (/A)")
    filing_year: int | None = Field(default=None, description="Filing or report calendar year")


class FilingDocument(BaseModel):
    """Raw content and metadata for a fetched EDGAR document."""

    accession: str
    document_name: str
    content: bytes
    content_type: str = "text/html"
    url: str


class EdgarClientError(Exception):
    """Base exception for SEC EDGAR API operations."""


class EdgarCompanyNotFoundError(EdgarClientError):
    """Raised when a ticker or CIK cannot be found on EDGAR."""


class EdgarFilingNotFoundError(EdgarClientError):
    """Raised when a specific filing or document is not found."""


class EdgarRateLimitError(EdgarClientError):
    """Raised when rate limiter token bucket is exhausted or SEC returns 429."""


class ForeignFilerUnsupportedError(EdgarClientError):
    """Raised when encountering foreign filers (Forms 20-F, 40-F, 6-K) per Invariant I3."""


class EdgarCircuitBreakerOpenError(EdgarClientError):
    """Raised when EDGAR client circuit breaker is open due to repeated upstream failures."""
