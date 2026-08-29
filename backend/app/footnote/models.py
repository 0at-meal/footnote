"""
Data models for Debt Schedule Footnote Extraction (Feature 8, Step E).

Adheres to:
- CONSTITUTION §1.1: mypy --strict compliance.
- CONSTITUTION §2.3: Preserves provenance coordinates (page, bbox).
- CONSTITUTION §3.8: Modular domain models.
"""

from pydantic import BaseModel, Field


class DebtTranche(BaseModel):
    """
    An individual debt instrument/tranche extracted from Note 8 (Debt Schedule).
    """

    id: str = Field(..., description="Unique identifier for the tranche")
    instrument_name: str = Field(
        ..., description="Name or description of debt instrument"
    )
    principal_amount: float | None = Field(
        default=None, description="Extracted principal amount in reporting units"
    )
    principal_text: str = Field(
        default="", description="Raw string value extracted from filing"
    )
    interest_rate: float | None = Field(
        default=None,
        description="Annual coupon or effective rate percentage (e.g. 5.25)",
    )
    rate_text: str = Field(
        default="", description="Raw rate string (e.g. '5.250%' or 'SOFR + 2.50%')"
    )
    maturity_year: int | None = Field(
        default=None, description="Maturity year (e.g. 2028)"
    )
    senior_subordinated: str = Field(
        default="Senior",
        description="Seniority category (Senior, Subordinated, Secured, etc.)",
    )
    is_floating: bool = Field(
        default=False, description="True if interest rate is variable/floating"
    )
    spread: float | None = Field(
        default=None, description="Floating spread in percentage points (e.g. 2.50)"
    )
    benchmark: str | None = Field(
        default=None, description="Floating benchmark index (e.g. SOFR, LIBOR)"
    )
    page: int = Field(default=1, ge=1, description="1-indexed source PDF page number")
    bbox: dict[str, float] = Field(
        default_factory=lambda: {"x0": 0.0, "y0": 0.0, "x1": 0.0, "y1": 0.0},
        description="W3C Web Annotation-style bounding box in 0-1000 space",
    )


class DebtSchedule(BaseModel):
    """
    Extracted Debt Schedule compiled from footnote tables.
    """

    job_id: str = Field(..., description="Job identifier")
    company_id: str | None = Field(default=None, description="Associated company ID")
    filing_year: int | None = Field(default=None, description="Filing fiscal year")
    footnote_title: str = Field(
        default="Note 8. Debt", description="Footnote section title"
    )
    tranches: list[DebtTranche] = Field(
        default_factory=list, description="Extracted debt tranches"
    )
    total_debt: float | None = Field(
        default=None, description="Sum of all tranche principal amounts"
    )
    weighted_avg_rate: float | None = Field(
        default=None, description="Weighted average interest rate percentage"
    )
    is_confirmed: bool = Field(
        default=False, description="True if confirmed by analyst review"
    )


class DebtScheduleConfirmRequest(BaseModel):
    """
    Payload for POST /footnote/{job_id}/debt/confirm.
    """

    tranches: list[DebtTranche]
