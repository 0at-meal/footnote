"""
Canonical extracted line-item record.

Every extracted value carries a provenance ``Locator`` (PDF page/bbox or SEC
EDGAR HTML element). The legacy ``page``/``bbox``/``source_file`` fields are
kept in sync with the locator for backward-compatible serialization.
"""

from pydantic import BaseModel, Field, model_validator

from app.extraction.locator import (
    HtmlLocator,
    Locator,
    PdfLocator,
)


class ExtractedRecord(BaseModel):
    """
    Canonical schema for an extracted line item.

    Field names (value, label, page, bbox, source_file) are persisted; do not rename
    them without a migration. Provenance lives in the discriminated ``locator``.
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
    """Discriminated union locator: PdfLocator or HtmlLocator."""

    is_reconciliation_candidate: bool = False
    """Flag indicating whether this item belongs to a reconciliation candidate table."""

    footnote_type: str | None = None
    """Type of footnote if extracted from a footnote section (e.g. 'debt')."""

    @model_validator(mode="after")
    def _sync_locator_and_legacy_fields(self) -> "ExtractedRecord":
        if self.locator is None:
            if self.page >= 1 and self.source_file:
                self.locator = PdfLocator(
                    page=self.page,
                    bbox=self.bbox,
                    source_file=self.source_file,
                )
        elif isinstance(self.locator, PdfLocator):
            self.page = self.locator.page
            self.bbox = self.locator.bbox
            self.source_file = self.locator.source_file
        elif isinstance(self.locator, HtmlLocator) and not self.source_file:
            self.source_file = self.locator.document or self.locator.accession
        return self
