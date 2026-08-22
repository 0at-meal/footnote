"""
Data models for the review stage (Feature 5).

Governed by CONSTITUTION §2.3 (frozen fields), §3.9 (review stage boundaries).
"""

from enum import Enum

from pydantic import BaseModel, Field

from app.extraction.models import ConfidenceBand


class ReviewStatus(str, Enum):
    """
    Review-layer status for an extracted item in the Review UI.
    """

    auto_accepted = "auto_accepted"
    needs_review = "needs_review"
    manual_required = "manual_required"
    extraction_error = "extraction_error"
    pending_taxonomy_confirmation = "pending_taxonomy_confirmation"
    flagged = "flagged"
    locked = "locked"


class ReviewItem(BaseModel):
    """
    Projection of an extracted/classified record for the review UI.

    Preserves canonical frozen field names: value, label, page, bbox, source_file
    (CONSTITUTION §2.3, NFR7).
    """

    id: str = Field(..., description="Unique review item identifier within the job")
    value: str = Field(..., description="Displayed value text (unmodified or user-edited)")
    label: str = Field(..., description="Structural label path")
    page: int = Field(..., ge=1, description="1-indexed page number in the source PDF")
    bbox: dict[str, float] = Field(
        ...,
        description="W3C Web Annotation-style bounding box in 0-1000 space: {x0, y0, x1, y1}",
    )
    source_file: str = Field(..., description="Original filename string as uploaded")
    confidence_band: ConfidenceBand = Field(
        ...,
        description="Extraction confidence band from Feature 2",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Structural confidence score from Feature 2",
    )
    normalized_label: str | None = Field(
        default=None,
        description="Standardized taxonomy label from Feature 3 if classified",
    )
    taxonomy_status: str | None = Field(
        default=None,
        description="Taxonomy match status from Feature 3 if classified",
    )
    status: ReviewStatus = Field(
        ...,
        description="Current review-layer status",
    )
    flags: list[str] = Field(
        default_factory=list,
        description="Diagnostic flags attached during extraction",
    )
    is_target_metric_candidate: bool = Field(
        default=True,
        description="True if item belongs to target metric reconciliation bridge",
    )
    table_name: str | None = Field(
        default=None,
        description="Enclosing table or section title",
    )
    error_detail: str | None = Field(
        default=None,
        description="Details of extraction or parse error if applicable",
    )


class ReviewItemsResponse(BaseModel):
    """
    Response model for GET /review/{job_id}/items.
    """

    job_id: str
    items: list[ReviewItem]
    total_items: int


class ReviewItemEditRequest(BaseModel):
    """
    Payload for PATCH /review/{job_id}/items/{item_id}/edit.

    Frozen fields (page, bbox, source_file) cannot be modified (CONSTITUTION §2.3, spec AC-9).
    """

    value: str | None = Field(default=None, description="Corrected value text")
    label: str | None = Field(default=None, description="Corrected label text")


class ReviewItemConfirmRequest(BaseModel):
    """
    Payload for POST /review/{job_id}/items/{item_id}/confirm.
    """

    add_to_taxonomy: bool = Field(
        default=False,
        description="Whether to confirm adding an unrecognized label to the taxonomy seed list (EC-5)",
    )


class ReviewBatchConfirmRequest(BaseModel):
    """
    Request payload for POST /review/{job_id}/confirm-batch (Ticket 4.1).
    """

    target_candidates_only: bool = Field(
        default=True,
        description="If True, confirms all items where is_target_metric_candidate is True and status is not extraction_error",
    )
    item_ids: list[str] | None = Field(
        default=None,
        description="Optional explicit list of item IDs to confirm and lock",
    )
    auto_add_pending_taxonomy: bool = Field(
        default=True,
        description="If True, adds pending taxonomy labels to active taxonomy repository",
    )


class ReviewBatchConfirmResponse(BaseModel):
    """
    Response model for POST /review/{job_id}/confirm-batch (Ticket 4.1).
    """

    job_id: str
    total_locked: int
    locked_item_ids: list[str]
    items: list[ReviewItem]

