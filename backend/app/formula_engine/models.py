"""
Data models for the formula engine input stage (Feature 4 Step 1).

Enforces CONSTITUTION §1.1, §1.3, §1.4, §2.3:
- Fully typed Pydantic models for pipeline stage boundary.
- Pure in-memory representations (no I/O, no random, no clock).
- Preserves frozen schema field names (value, label, page, bbox, source_file).
"""

from pydantic import BaseModel, Field


class FormulaInputNode(BaseModel):
    """
    Authoritative in-memory input node representing a single confirmed line item.

    Each node binds the confirmed normalized taxonomy label to its raw extracted value
    and W3C Web Annotation provenance fields (0-1000 normalized space).
    """

    node_id: str = Field(
        ...,
        description="Unique deterministic node identifier within the formula input set",
    )
    normalized_label: str = Field(
        ...,
        min_length=1,
        description="Confirmed standardized taxonomy label from Feature 3",
    )
    value: str = Field(
        ...,
        description="Raw extracted numeric or text string from source document (unmodified)",
    )
    label: str = Field(
        ...,
        description="Original structural label from Feature 2 extraction",
    )
    page: int = Field(
        ...,
        ge=1,
        description="1-indexed page number in the source PDF",
    )
    bbox: dict[str, float] = Field(
        ...,
        description="W3C Web Annotation bounding box in 0-1000 space: {x0, y0, x1, y1}",
    )
    source_file: str = Field(
        ...,
        min_length=1,
        description="Original filename string as uploaded (UTF-8, unmodified)",
    )
    record_index: int = Field(
        ...,
        ge=0,
        description="Zero-based index of originating extraction record in the job batch",
    )
    is_hardcode: bool = Field(
        default=False,
        description="Explicit flag for manual hardcode overrides per NFR2",
    )


class FormulaInputError(BaseModel):
    """
    Error record indicating a validation or provenance failure during formula input extraction.
    """

    record_index: int = Field(
        ...,
        ge=0,
        description="Zero-based index of the affected record in the input batch",
    )
    reason: str = Field(
        ...,
        min_length=1,
        description="Explanation of the validation or provenance failure",
    )
    label: str | None = Field(
        default=None,
        description="Structural or normalized label if available",
    )
    source_file: str | None = Field(
        default=None,
        description="Source file name if available",
    )


class FormulaInputBatch(BaseModel):
    """
    Container for the batch of valid formula input nodes and any encountered errors.
    """

    nodes: list[FormulaInputNode] = Field(
        default_factory=list,
        description="List of valid confirmed formula input nodes",
    )
    errors: list[FormulaInputError] = Field(
        default_factory=list,
        description="List of validation/provenance errors surfaced during filtering",
    )
    total_records_received: int = Field(
        ...,
        ge=0,
        description="Total count of ClassifiedRecord objects provided to the reader",
    )
    confirmed_count: int = Field(
        ...,
        ge=0,
        description="Count of records with confirmed normalized labels",
    )
    excluded_count: int = Field(
        ...,
        ge=0,
        description="Count of records excluded (pending confirmation, manual required, or errors)",
    )
    error_message: str | None = Field(
        default=None,
        description="Top-level error message if batch cannot proceed to tree generation (e.g. EC-5)",
    )
