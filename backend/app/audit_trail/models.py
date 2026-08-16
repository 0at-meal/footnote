"""
Data models for the Audit Trail stage (Feature 6).

Enforces CONSTITUTION §1.1, §1.3, §2.3, §3.4:
- Fully typed Pydantic models for the audit trail lookup pipeline boundary.
- Preserves canonical frozen field names: value, label, page, bbox, source_file.
- Read-only data representations for source chain resolution.
"""

from pydantic import BaseModel, Field


class SourceComponent(BaseModel):
    """
    Representation of a single contributing source item in the resolved source chain.

    Preserves canonical frozen field names: value, label, page, bbox, source_file
    (CONSTITUTION §2.3, NFR7).
    """

    component_id: str = Field(
        ...,
        description="Unique identifier of the source component or review item",
    )
    source_file: str = Field(
        ...,
        description="Source PDF filename (UTF-8, unmodified)",
    )
    page: int = Field(
        ...,
        ge=1,
        description="1-indexed page number in the source PDF",
    )
    bbox: dict[str, float] = Field(
        ...,
        description="W3C Web Annotation bounding box coordinates in 0-1000 space: {x0, y0, x1, y1}",
    )
    value: str = Field(
        ...,
        description="Extracted or user-edited value string from the source",
    )
    label: str = Field(
        ...,
        description="Original structural label from extraction",
    )
    normalized_label: str | None = Field(
        default=None,
        description="Normalized standardized taxonomy label",
    )
    review_status: str = Field(
        ...,
        description="Current review status from Feature 5 (locked, flagged, auto_accepted, needs_review, manual_required, pending_taxonomy_confirmation, or source_record_missing)",
    )
    is_missing: bool = Field(
        default=False,
        description="True if this contributing record was missing from the backend store (EC-1)",
    )
    provenance_id: str | None = Field(
        default=None,
        description="Canonical W3C Web Annotation ID associated with this leaf component",
    )


class SourceChainResponse(BaseModel):
    """
    Structured response model for full source chain resolution (FR8, AC-1, AC-2, AC-6, AC-7).
    """

    job_id: str = Field(
        ...,
        description="Originating job UUID",
    )
    sheet_name: str | None = Field(
        default=None,
        description="Worksheet name if queried by cell reference",
    )
    cell_coord: str | None = Field(
        default=None,
        description="A1-style cell coordinate if queried by cell reference",
    )
    provenance_id: str | None = Field(
        default=None,
        description="Canonical W3C Web Annotation URN ID",
    )
    node_id: str | None = Field(
        default=None,
        description="Formula tree node ID associated with the queried cell/annotation",
    )
    is_formula: bool = Field(
        default=False,
        description="True if the resolved cell is formula-driven or calculated",
    )
    formula_expression: str | None = Field(
        default=None,
        description="Formula expression or calculation representation if formula-driven",
    )
    is_found: bool = Field(
        default=True,
        description="True if a valid provenance record was found for the query",
    )
    components: list[SourceComponent] = Field(
        default_factory=list,
        description="Ordered sequence of contributing source components",
    )
    error_detail: str | None = Field(
        default=None,
        description="Diagnostic or explanatory message when provenance is not found or partial",
    )
