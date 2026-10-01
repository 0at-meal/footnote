"""
Data models for HTML and iXBRL Extraction (FN-021).
"""

from pydantic import BaseModel, Field

from app.extraction.models import ExtractedRecord


class HtmlCell(BaseModel):
    """A cell within an extracted HTML table."""

    row_idx: int
    col_idx: int
    text: str
    cleaned_value: str = ""
    numeric_value: float | None = None
    colspan: int = 1
    rowspan: int = 1
    is_header: bool = False
    period: str | None = None
    xpath: str = ""
    char_range: tuple[int, int] | None = None


class HtmlTable(BaseModel):
    """An extracted HTML table with structural metadata."""

    index: int
    title: str = ""
    xpath: str = ""
    is_reconciliation: bool = False
    reconciliation_score: float = 0.0
    cells: list[HtmlCell] = Field(default_factory=list)
    row_headers: dict[int, str] = Field(default_factory=dict)
    col_headers: dict[int, str] = Field(default_factory=dict)


class IxbrlFact(BaseModel):
    """An authoritative XBRL/iXBRL fact extracted from inline tags."""

    concept: str = Field(..., description="US GAAP concept name, e.g. 'us-gaap:NetIncomeLoss'")
    value: float = Field(..., description="Fact numerical value")
    context_period: str = Field(..., description="Reporting period end date or date range")
    scale: int = Field(default=0, description="Scale power of 10 (e.g. 6 for millions)")
    sign: int = Field(default=1, description="Sign multiplier (1 or -1)")
    unit: str = Field(default="USD", description="Unit currency or measurement")
    decimals: str | int | None = Field(default=None, description="Decimals accuracy attribute")


class HtmlExtractionResult(BaseModel):
    """Complete result of extracting an EDGAR HTML / iXBRL document."""

    status: str = Field(..., description="'success' or 'not_found' per Invariant I3")
    not_found_reason: str | None = Field(default=None, description="Explicit failure reason when not found (I3)")
    records: list[ExtractedRecord] = Field(default_factory=list, description="Extracted records with HtmlLocator")
    ixbrl_facts: list[IxbrlFact] = Field(default_factory=list, description="Authoritative GAAP facts")
    tables_scanned: int = 0
    duration_seconds: float = 0.0
