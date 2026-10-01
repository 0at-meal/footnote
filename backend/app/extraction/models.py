"""
Data models for the layout-aware extraction pipeline (Feature 2).

Scope (Step 1):
    DoclingBbox  ← Docling-native bounding box coordinates (points).
    DoclingItem  ← Intermediate representation of a parsed table cell/value.

Note:
    ExtractedRecord (the frozen 5-field schema per spec.md) will be introduced in Step 3.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel


class DoclingBbox(BaseModel):
    """
    Docling-native bounding box coordinates (in PDF points, page-relative).

    Coordinates are relative to the top-left or bottom-left depending on Docling's
    coordinate space prior to PyMuPDF 0-1000 normalization (Feature 2 Step 2).
    """

    x0: float
    y0: float
    x1: float
    y1: float


class DoclingItem(BaseModel):
    """
    Raw output of the Docling structural parse for a single value / table cell.

    This is an intermediate representation produced by Step 1 before coordinate
    normalization (Step 2) and record assembly (Step 3).
    """

    value: str
    """Literal text string of the cell contents (unmodified, EC-5 parentheses preserved)."""

    label: str
    """Hierarchical structural label path (e.g. 'Operating Expenses / Stock-based compensation')."""

    page: int
    """1-indexed page number where the item appears in the source PDF."""

    bbox: DoclingBbox
    """Docling-native bounding box prior to PyMuPDF normalization."""

    source_file: str
    """Original filename string as uploaded (UTF-8, stored as-is — EC-8 contract)."""

    table_name: str | None = None
    """Enclosing table or section title extracted from the document."""

    is_error: bool = False
    """Flag indicating whether an error occurred during Docling cell-level parsing."""

    error_detail: str | None = None
    """Description of the parse error if is_error is True."""

    is_reconciliation_candidate: bool = False
    """Flag indicating whether this item belongs to a reconciliation candidate table."""

    parser_used: Literal["docling", "pymupdf"] = "docling"
    """Which parser produced this item. Controls Y-axis coordinate space in the normalizer."""

    footnote_type: str | None = None
    """Type of footnote if extracted from a footnote section (e.g. 'debt')."""


class NormalizedBbox(BaseModel):
    """
    W3C Web Annotation-style bounding box, normalized to 0-1000 coordinate space.

    Coordinates are clamped to [0.0, 1000.0] and rounded to 2 decimal places.
    """

    x0: float
    y0: float
    x1: float
    y1: float


class NormalizedItem(BaseModel):
    """
    Intermediate representation of an extracted item after PyMuPDF coordinate normalization (Step 2).
    """

    value: str
    label: str
    page: int
    bbox: NormalizedBbox
    source_file: str
    table_name: str | None = None
    is_error: bool = False
    error_detail: str | None = None
    is_reconciliation_candidate: bool = False
    footnote_type: str | None = None


from pydantic import Field, model_validator

from app.extraction.locator import (
    HtmlLocator,
    Locator,
    PdfLocator,
)


class ExtractedRecord(BaseModel):
    """
    Canonical frozen schema for an extracted line item (spec.md FR2, AC-3, FN-023).

    Field names (value, label, page, bbox, source_file) are preserved for the project lifetime
    (CONSTITUTION §2.3, NFR7). Supports discriminated Locator union (PdfLocator | HtmlLocator).
    """

    value: str
    """Raw text string as extracted from the document (unmodified)."""

    label: str
    """Raw structural label path from document structure."""

    page: int = 1
    """1-indexed page number in the source PDF."""

    bbox: dict[str, float] = Field(
        default_factory=lambda: {"x0": 0.0, "y0": 0.0, "x1": 1000.0, "y1": 1000.0}
    )
    """W3C Web Annotation-style bounding box in 0-1000 space: {x0, y0, x1, y1}."""

    source_file: str = ""
    """Original filename string as uploaded (UTF-8, unmodified)."""

    locator: Locator | None = None
    """Discriminated union locator: PdfLocator or HtmlLocator (FN-023)."""

    is_reconciliation_candidate: bool = False
    """Flag indicating whether this item belongs to a reconciliation candidate table."""

    footnote_type: str | None = None
    """Type of footnote if extracted from a footnote section (e.g. 'debt')."""

    @model_validator(mode="after")
    def _sync_locator_and_legacy_fields(self) -> "ExtractedRecord":
        if self.locator is None:
            if self.page >= 1 and self.source_file:
                try:
                    self.locator = PdfLocator(
                        page=self.page,
                        bbox=self.bbox,
                        source_file=self.source_file,
                    )
                except Exception:  # noqa: BLE001, S110
                    pass
        elif isinstance(self.locator, PdfLocator):
            self.page = self.locator.page
            self.bbox = self.locator.bbox
            self.source_file = self.locator.source_file
        elif isinstance(self.locator, HtmlLocator) and not self.source_file:
            self.source_file = self.locator.document or self.locator.accession
        return self


class ConfidenceBand(str, Enum):
    """
    Confidence routing band assigned to an extracted record based on structural score.
    """

    auto_accepted = "auto_accepted"
    """Score >= 0.95: Auto-accept without mandatory human review."""

    needs_review = "needs_review"
    """0.65 <= Score < 0.95: Queued for human review in Feature 5 UI."""

    manual_required = "manual_required"
    """Score < 0.65: Low confidence, mandatory manual entry / review required."""


class ScoredRecord(BaseModel):
    """
    An ExtractedRecord with structural confidence score, routing band, and diagnostic flags attached.
    """

    record: ExtractedRecord
    confidence_score: float
    confidence_band: ConfidenceBand
    flags: list[str]
    table_name: str | None = None
    status: Literal["ok", "extraction_error"] = "ok"
    error_detail: str | None = None
    is_reconciliation_candidate: bool = False
    footnote_type: str | None = None


class ExtractionSummary(BaseModel):
    """
    Aggregate summary statistics and flagging breakdown for a completed extraction job.
    """

    total_items: int
    auto_accepted_count: int
    needs_review_count: int
    manual_required_count: int
    extraction_error_count: int = 0
    image_only_page_count: int = 0
    flagged_count: int
    flagged_percentage: float
    passed_threshold: bool
    filtered_non_reconciliation_count: int = 0
    parser_used: Literal["docling", "pymupdf", "mixed", "ixbrl_html"] = "docling"
    target_metric_found: bool = True
