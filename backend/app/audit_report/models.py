"""
Data models for the Audit Report stage (Feature 8).

Enforces CONSTITUTION §1.1, §1.3, §2.3:
- Fully typed Pydantic models for the audit report stage.
- Preserves canonical frozen field names: value, label, page, bbox, source_file.
- Read-only data representations for compiled audit datasets and report rendering.
"""

from pydantic import BaseModel, Field

from app.audit_trail.models import SourceComponent


class ReportMetadata(BaseModel):
    """
    Header and summary metadata for an audit report.
    """

    job_id: str = Field(..., description="UUID of the originating job")
    entity: str = Field(..., description="Entity identifier (e.g. company name/ticker)")
    filing_filename: str = Field(..., description="Original filename of the filing PDF")
    filing_year: int | None = Field(default=None, description="Filing year if identified")
    target_metric: str = Field(..., description="Target financial metric (e.g. Adjusted EBITDA)")
    generated_at: str = Field(..., description="ISO 8601 UTC timestamp of report compilation")
    total_cells: int = Field(default=0, ge=0, description="Total cells generated in the workbook")
    automated_count: int = Field(default=0, ge=0, description="Count of auto-accepted inputs")
    verified_count: int = Field(default=0, ge=0, description="Count of human-verified/locked inputs")
    flagged_count: int = Field(default=0, ge=0, description="Count of flagged inputs")
    override_count: int = Field(default=0, ge=0, description="Count of manual overrides/edits")


class ReconciliationSummaryItem(BaseModel):
    """
    Line item row in the high-level financial reconciliation summary.
    """

    sheet_name: str = Field(..., description="Worksheet containing this reconciliation item")
    cell_coord: str = Field(..., description="A1-style cell reference (e.g. 'B2', 'B8')")
    label: str = Field(..., description="Original or display line item label")
    normalized_label: str | None = Field(default=None, description="Standardized taxonomy label")
    formula_expression: str | None = Field(default=None, description="Formula representation")
    computed_value: str = Field(..., description="Formatted or computed value string")
    is_formula: bool = Field(default=False, description="True if cell contains a dynamic formula")
    is_hardcode: bool = Field(default=False, description="True if tagged as a manual hardcode")


class ProvenanceMatrixItem(BaseModel):
    """
    Row in the comprehensive provenance matrix mapping a cell to its resolved source chain.
    """

    sheet_name: str = Field(..., description="Worksheet name")
    cell_coord: str = Field(..., description="A1-style cell coordinate")
    node_id: str = Field(..., description="Formula tree node ID")
    label: str = Field(..., description="Line item label")
    normalized_label: str | None = Field(default=None, description="Standardized taxonomy label")
    computed_value: str = Field(..., description="Computed value or raw extracted value")
    is_formula: bool = Field(default=False, description="True if formula-driven")
    components: list[SourceComponent] = Field(
        default_factory=list,
        description="Resolved contributing source components from Feature 6",
    )


class ManualOverrideItem(BaseModel):
    """
    Detail of a manual override, user edit, hardcode, or resolved error (spec §3, AC-3).
    """

    item_id: str = Field(..., description="Unique review item ID or coordinate reference")
    source_file: str = Field(..., description="Source PDF filename (UTF-8)")
    page: int = Field(..., ge=1, description="1-indexed source PDF page")
    bbox: dict[str, float] = Field(
        ...,
        description="Bounding box coordinates in 0-1000 space: {x0, y0, x1, y1}",
    )
    override_type: str = Field(
        default="user_edit",
        description="Category: 'user_edit', 'extraction_error_recovery', 'manual_required_entry', or 'manual_hardcode'",
    )
    original_value: str | None = Field(default=None, description="Original value before human edit")
    final_value: str = Field(..., description="Final confirmed/locked value")
    original_label: str | None = Field(default=None, description="Original label before human edit")
    final_label: str = Field(..., description="Final confirmed/locked label")
    review_status: str = Field(..., description="Review status (e.g. locked, manual_required)")
    confidence_band: str | None = Field(default=None, description="Extraction confidence band")
    flags: list[str] = Field(default_factory=list, description="Diagnostic extraction flags")
    error_detail: str | None = Field(default=None, description="Error detail if recovered from error")
    confirmation_timestamp: str | None = Field(default=None, description="Human confirmation timestamp if recorded")
    is_hardcode: bool = Field(default=False, description="True if generated as manual hardcode")


class ClassifierAuditEntry(BaseModel):
    """
    Audit record for a single LLM classifier invocation proving numeric-free operation.
    """

    record_index: int = Field(..., description="Index of the classified record")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp of classification")
    input_label: str = Field(..., description="Sanitized input label dispatched to LLM")
    structural_context: str | None = Field(default=None, description="Structural context sent")
    output_label: str | None = Field(default=None, description="Candidate label returned")
    confidence: float | None = Field(default=None, description="Confidence score returned")
    taxonomy_status: str = Field(..., description="Taxonomy matching status")
    resulting_state: str = Field(..., description="Resulting pipeline state")
    error_detail: str | None = Field(default=None, description="Error detail if failed")


class ClassifierAuditSummary(BaseModel):
    """
    Governance proof verifying that the LLM operated strictly as a classifier.
    """

    total_calls: int = Field(default=0, ge=0, description="Total classifier calls made")
    matched_count: int = Field(default=0, ge=0, description="Count of matched taxonomy labels")
    pending_count: int = Field(default=0, ge=0, description="Count of unrecognized labels")
    error_count: int = Field(default=0, ge=0, description="Count of classifier call errors")
    is_strictly_numeric_free: bool = Field(
        default=True,
        description="True if all classifier responses contained zero numeric fields",
    )
    entries: list[ClassifierAuditEntry] = Field(
        default_factory=list,
        description="List of audited classifier call records",
    )


class DriftAuditSummary(BaseModel):
    """
    Summary of Feature 7 cross-year drift detection for the target metric.
    """

    is_evaluated: bool = Field(default=False, description="True if drift detection was run")
    is_baseline: bool = Field(default=False, description="True if baseline initialization year")
    has_discrepancy: bool = Field(default=False, description="True if redefinition detected")
    filing_year: int | None = Field(default=None, description="Filing year evaluated")
    added_labels: list[str] = Field(
        default_factory=list,
        description="Normalized component labels added in this filing",
    )
    removed_labels: list[str] = Field(
        default_factory=list,
        description="Normalized component labels removed in this filing",
    )
    prior_node_id: str | None = Field(default=None, description="Prior-year graph node ID compared against")
    summary_text: str = Field(default="", description="Human-readable drift status summary")


class CompiledAuditDataset(BaseModel):
    """
    Unified dataset containing all compiled audit data for report rendering (spec §1).
    """

    job_id: str = Field(..., description="UUID of the job")
    metadata: ReportMetadata
    reconciliation_summary: list[ReconciliationSummaryItem] = Field(default_factory=list)
    provenance_matrix: list[ProvenanceMatrixItem] = Field(default_factory=list)
    manual_overrides: list[ManualOverrideItem] = Field(default_factory=list)
    has_manual_overrides: bool = Field(default=False, description="True if manual overrides exist")
    classifier_governance: ClassifierAuditSummary
    drift_summary: DriftAuditSummary
