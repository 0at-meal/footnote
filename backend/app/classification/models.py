"""
Data models for the classification & normalization pipeline (Feature 3).

Enforces CONSTITUTION §1.2, §1.3, §6.2, §6.5:
- Outbound payload contains ONLY label and structural context (no value, bbox, or raw file content).
- Return schema structurally contains ONLY textual label and confidence score (no numeric or computed fields).
- ClassifiedRecord preserves the underlying ExtractedRecord byte-identically (AC-6, NFR7).
"""

from enum import Enum

from pydantic import BaseModel, Field

from app.extraction.models import ScoredRecord


class ClassifierInputPayload(BaseModel):
    """
    Sanitized input payload dispatched to the Groq classifier.

    Contains exclusively the structural label and optional context.
    Strictly excludes the extracted numeric value, page, bbox, and filename (CONSTITUTION §6.5).
    """

    label: str = Field(..., min_length=1, description="Raw structural label from extraction")
    structural_context: str | None = Field(
        default=None,
        description="Surrounding structural context (e.g. adjacent headers)",
    )


class ClassifierRawResponse(BaseModel):
    """
    Response schema produced by the Groq classifier.

    Structurally cannot carry a numeric return field (CONSTITUTION §1.2, §6.2).
    """

    label: str = Field(..., min_length=1, description="Taxonomy classification candidate label")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Classifier confidence score in the range [0.0, 1.0]",
    )


class ClassificationItemResult(BaseModel):
    """
    Per-item result of classifier dispatch.
    """

    record_index: int = Field(..., description="Index of the record in the original batch")
    payload: ClassifierInputPayload = Field(..., description="Sanitized input sent to classifier")
    raw_response: ClassifierRawResponse | None = Field(
        default=None,
        description="Parsed classifier response if successful",
    )
    is_error: bool = Field(default=False, description="True if a classification error occurred")
    error_detail: str | None = Field(
        default=None,
        description="Error message or reason for classification failure",
    )


class ClassificationBatchResult(BaseModel):
    """
    Aggregate result of a batch classification dispatch.
    """

    results: list[ClassificationItemResult]
    total_dispatched: int
    success_count: int
    error_count: int
    skipped_count: int


class TaxonomyStatus(str, Enum):
    """
    Taxonomy verification status for a classified label (spec.md §3, §4).
    """

    matched = "matched"
    """Candidate label matches an active seed taxonomy entry by exact string match."""

    pending_taxonomy_confirmation = "pending_taxonomy_confirmation"
    """Candidate label does not match taxonomy; queued for explicit human review."""


class TaxonomyCheckResult(BaseModel):
    """
    Result of evaluating a candidate label against the active taxonomy.
    """

    candidate_label: str = Field(..., description="Candidate label returned by classifier")
    status: TaxonomyStatus = Field(..., description="Match status (matched or pending_taxonomy_confirmation)")
    matched_entry: str | None = Field(
        default=None,
        description="Exact matched taxonomy entry if matched, otherwise None",
    )
    is_matched: bool = Field(
        default=False,
        description="Convenience boolean indicating whether exact match was found",
    )


class ClassifiedRecord(BaseModel):
    """
    An extraction record with classification and taxonomy normalization metadata attached (Feature 3).

    Strictly preserves the underlying ExtractedRecord and ScoredRecord fields (AC-6, NFR7).
    """

    record: ScoredRecord = Field(..., description="Underlying scored extraction record")
    normalized_label: str | None = Field(
        default=None,
        description="Confirmed standardized taxonomy label if matched/confirmed; None if pending (AC-6)",
    )
    taxonomy_status: TaxonomyStatus = Field(
        default=TaxonomyStatus.pending_taxonomy_confirmation,
        description="Taxonomy verification status",
    )
    classifier_confidence: float | None = Field(
        default=None,
        description="Confidence score returned by Groq classifier",
    )
    is_confirmed: bool = Field(
        default=False,
        description="True if normalized_label is confirmed and matched against active taxonomy",
    )
