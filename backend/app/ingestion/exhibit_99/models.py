"""
Data models for 8-K EX-99.1 Earnings Release Support (FN-022).
"""

from enum import Enum

from pydantic import BaseModel, Field

from app.extraction.locator import Locator
from app.extraction.models import ExtractedRecord


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
    exhibit_number: str = "EX-99.1"
    exhibit_filename: str | None = None
    exhibit_url: str | None = None
    format: ExhibitFormat = ExhibitFormat.HTML


class DiffItem(BaseModel):
    """Line-item comparison between earnings release (8-K) and periodic filing (10-Q/10-K)."""

    metric_name: str
    period: str
    release_value: float | None = None
    filing_value: float | None = None
    difference: float | None = None
    is_match: bool = True
    status: str = "match"  # 'match', 'discrepancy', 'release_only', 'filing_only'
    notes: str = ""
    release_locator: Locator | None = None
    filing_locator: Locator | None = None


class BridgeDiffReport(BaseModel):
    """Structured diff report comparing 8-K press release and official 10-Q/10-K."""

    cik: str
    period: str
    release_accession: str
    filing_accession: str
    items: list[DiffItem] = Field(default_factory=list)
    has_discrepancies: bool = False
    summary: str = ""


class CanonicalBridgeResult(BaseModel):
    """Result of canonical reconciliation bridge extraction with dual provenance and diffing."""

    canonical_records: list[ExtractedRecord] = Field(
        default_factory=list,
        description="Authoritative records with 'latest filed wins' precedence",
    )
    guidance_records: list[ExtractedRecord] = Field(
        default_factory=list,
        description="Forward-looking / guidance reconciliations tagged separately",
    )
    diff_report: BridgeDiffReport | None = None
