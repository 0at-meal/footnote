"""
Unit tests for Audit Report data models (Feature 8 Step 1).

Enforces:
- CONSTITUTION §1.1, §1.3, §2.3: Fully typed Pydantic models, frozen field validation.
"""

from app.audit_report.models import (
    ClassifierAuditEntry,
    ClassifierAuditSummary,
    CompiledAuditDataset,
    DriftAuditSummary,
    ManualOverrideItem,
    ProvenanceMatrixItem,
    ReconciliationSummaryItem,
    ReportMetadata,
)
from app.audit_trail.models import SourceComponent


def test_report_metadata_creation() -> None:
    meta = ReportMetadata(
        job_id="job-123",
        entity="Acme Corp",
        filing_filename="acme_2024_10k.pdf",
        filing_year=2024,
        target_metric="Adjusted EBITDA",
        generated_at="2026-08-17T12:00:00Z",
        total_cells=25,
        automated_count=20,
        verified_count=4,
        flagged_count=1,
        override_count=2,
    )
    assert meta.job_id == "job-123"
    assert meta.entity == "Acme Corp"
    assert meta.filing_year == 2024
    assert meta.total_cells == 25
    assert meta.override_count == 2


def test_reconciliation_summary_item() -> None:
    item = ReconciliationSummaryItem(
        sheet_name="Model_Summary",
        cell_coord="B5",
        label="Operating Income",
        normalized_label="Operating Income",
        formula_expression="=SUM(B2:B4)",
        computed_value="$125,000",
        is_formula=True,
        is_hardcode=False,
    )
    assert item.cell_coord == "B5"
    assert item.is_formula is True
    assert item.computed_value == "$125,000"


def test_provenance_matrix_item_with_components() -> None:
    comp = SourceComponent(
        component_id="job-123_0",
        source_file="acme_2024_10k.pdf",
        page=42,
        bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 250.0},
        value="50000",
        label="Stock-based compensation",
        normalized_label="Stock-Based Compensation",
        review_status="locked",
        is_missing=False,
        provenance_id="urn:footnote:provenance:job-123:leaf_0_sbc",
    )
    matrix_item = ProvenanceMatrixItem(
        sheet_name="Model_Summary",
        cell_coord="B3",
        node_id="leaf_0_sbc",
        label="Stock-based compensation",
        normalized_label="Stock-Based Compensation",
        computed_value="50000",
        is_formula=False,
        components=[comp],
    )
    assert matrix_item.cell_coord == "B3"
    assert len(matrix_item.components) == 1
    assert matrix_item.components[0].page == 42
    assert matrix_item.components[0].bbox["x0"] == 100.0


def test_manual_override_item() -> None:
    override = ManualOverrideItem(
        item_id="job-123_1",
        source_file="acme_2024_10k.pdf",
        page=15,
        bbox={"x0": 50.0, "y0": 100.0, "x1": 200.0, "y1": 150.0},
        override_type="user_edit",
        original_value="3500",
        final_value="35000",
        original_label="Lease adjustment",
        final_label="Operating Lease Expense",
        review_status="locked",
        confidence_band="needs_review",
        flags=["unparseable_value"],
        error_detail=None,
        confirmation_timestamp="2026-08-17T12:05:00Z",
        is_hardcode=False,
    )
    assert override.override_type == "user_edit"
    assert override.original_value == "3500"
    assert override.final_value == "35000"
    assert override.original_label == "Lease adjustment"
    assert override.final_label == "Operating Lease Expense"
    assert override.flags == ["unparseable_value"]
    assert override.confirmation_timestamp == "2026-08-17T12:05:00Z"


def test_classifier_governance_summary() -> None:
    entry = ClassifierAuditEntry(
        record_index=0,
        timestamp="2026-08-17T12:00:00Z",
        input_label="SBC expense",
        structural_context="Note 12",
        output_label="Stock-Based Compensation",
        confidence=0.98,
        taxonomy_status="matched",
        resulting_state="confirmed",
        error_detail=None,
    )
    summary = ClassifierAuditSummary(
        total_calls=1,
        matched_count=1,
        pending_count=0,
        error_count=0,
        is_strictly_numeric_free=True,
        entries=[entry],
    )
    assert summary.total_calls == 1
    assert summary.is_strictly_numeric_free is True
    assert summary.entries[0].output_label == "Stock-Based Compensation"


def test_drift_audit_summary() -> None:
    drift = DriftAuditSummary(
        is_evaluated=True,
        is_baseline=False,
        has_discrepancy=True,
        filing_year=2024,
        added_labels=["Litigation Settlement"],
        removed_labels=[],
        prior_node_id="acme_Adjusted EBITDA_2023",
        summary_text="Metric Redefinition Detected: 1 component(s) added, 0 removed.",
    )
    assert drift.has_discrepancy is True
    assert drift.added_labels == ["Litigation Settlement"]


def test_compiled_audit_dataset_roundtrip() -> None:
    meta = ReportMetadata(
        job_id="job-999",
        entity="Beta Corp",
        filing_filename="beta_2024.pdf",
        filing_year=2024,
        target_metric="Adjusted EBITDA",
        generated_at="2026-08-17T12:00:00Z",
        total_cells=10,
        automated_count=10,
        verified_count=0,
        flagged_count=0,
        override_count=0,
    )
    dataset = CompiledAuditDataset(
        job_id="job-999",
        metadata=meta,
        reconciliation_summary=[],
        provenance_matrix=[],
        manual_overrides=[],
        has_manual_overrides=False,
        classifier_governance=ClassifierAuditSummary(),
        drift_summary=DriftAuditSummary(),
    )
    dumped = dataset.model_dump_json()
    reloaded = CompiledAuditDataset.model_validate_json(dumped)
    assert reloaded.job_id == "job-999"
    assert reloaded.has_manual_overrides is False
    assert reloaded.metadata.entity == "Beta Corp"
