"""
Data models for 8-K Item 2.02 / EX-99.1 earnings release exhibits.
"""

from enum import Enum

from pydantic import BaseModel


class ExhibitFormat(str, Enum):
    HTML = "html"
    PDF = "pdf"
    IMAGE = "image"
    UNSUPPORTED = "unsupported"


class EarningsReleaseMetadata(BaseModel):
    """Metadata for an 8-K filing containing earnings release exhibits."""

    accession: str
    filing_date: str
    period: str | None = None
    has_item_2_02: bool = False
    exhibit_number: str | None = None
    """Exhibit type as listed in the filing index; None if no exhibit was found."""
    exhibit_filename: str | None = None
    exhibit_url: str | None = None
    format: ExhibitFormat | None = None
    """Exhibit file format; None if no exhibit was found."""
