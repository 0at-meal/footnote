"""
Data models for Narrative Delta Tracking & Diffing (Feature 10, Step G).

Adheres to:
- CONSTITUTION §1.1: mypy --strict compliance.
- CONSTITUTION §3.8: Modular domain models.
"""

from typing import Literal

from pydantic import BaseModel, Field

DiffTokenType = Literal["equal", "insert", "delete"]


class NarrativeSection(BaseModel):
    """
    Extracted textual narrative section from SEC filing (e.g. Item 7 MD&A or Item 1A Risk Factors).
    """

    job_id: str = Field(..., description="Job identifier")
    item_number: str = Field(
        ..., description="Item designation (e.g. 'Item 7', 'Item 2', 'Item 1A')"
    )
    title: str = Field(..., description="Full heading / title of section")
    text: str = Field(..., description="Extracted narrative text body")
    page_start: int = Field(default=1, ge=1, description="Starting page in PDF")
    page_end: int = Field(default=1, ge=1, description="Ending page in PDF")


class NarrativeDiffToken(BaseModel):
    """
    Individual word or chunk token in a narrative diff.
    """

    type: DiffTokenType = Field(
        ..., description="Diff operation: 'equal', 'insert' (added), 'delete' (removed)"
    )
    text: str = Field(..., description="Token text content")


class NarrativeDiff(BaseModel):
    """
    Compiled token-level word-diff between consecutive narrative sections.
    """

    company_id: str | None = Field(
        default=None, description="Company identifier if associated"
    )
    item_number: str = Field(
        default="Item 7", description="Section item compared (e.g. 'Item 7')"
    )
    earlier_job_id: str = Field(..., description="Prior period job ID")
    later_job_id: str = Field(..., description="Later / current period job ID")
    tokens: list[NarrativeDiffToken] = Field(
        default_factory=list, description="Ordered token-level diff sequence"
    )
    added_tokens: int = Field(default=0, description="Count of added tokens")
    removed_tokens: int = Field(default=0, description="Count of removed tokens")
    unchanged_tokens: int = Field(default=0, description="Count of unchanged tokens")
    similarity_ratio: float = Field(
        default=1.0,
        description="SequenceMatcher similarity ratio between earlier and later text (0.0 - 1.0)",
    )


class NarrativeDiffRequest(BaseModel):
    """
    Payload for POST /narrative/{company_id}/diff.
    """

    earlier_job_id: str
    later_job_id: str
    item_number: str = "Item 7"


class RiskFactor(BaseModel):
    """
    Individual risk factor extracted from Item 1A.
    """

    heading: str = Field(..., description="Risk factor header / summary statement")
    body_text: str = Field(default="", description="Detailed risk disclosure body text")


class RiskFactorChange(BaseModel):
    """
    Detected modification, insertion, or deletion of a risk factor between periods.
    """

    heading: str = Field(..., description="Risk factor heading")
    change_type: Literal["added", "removed", "modified"] = Field(
        ..., description="Type of change"
    )
    severity_score: float = Field(
        default=0.0,
        description="Severity score (0.0-1.0) indicating magnitude of delta",
    )
    added_text: str = Field(default="", description="New or expanded text disclosures")
    removed_text: str = Field(default="", description="Deleted or removed disclosures")


class RiskFactorRedline(BaseModel):
    """
    Compiled risk factor redline report across consecutive filings.
    """

    company_id: str | None = Field(default=None, description="Company identifier")
    earlier_job_id: str = Field(..., description="Prior period job ID")
    later_job_id: str = Field(..., description="Later period job ID")
    changes: list[RiskFactorChange] = Field(
        default_factory=list,
        description="List of risk factor changes sorted by severity",
    )
    added_count: int = Field(default=0, description="Count of newly added risks")
    removed_count: int = Field(default=0, description="Count of discontinued risks")
    modified_count: int = Field(default=0, description="Count of modified risks")


class RiskFactorRedlineRequest(BaseModel):
    """
    Payload for POST /narrative/{company_id}/risk-redline.
    """

    earlier_job_id: str
    later_job_id: str
