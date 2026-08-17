"""
Unit & integration tests for Audit Report Compiler (Feature 8 Step 1).

Enforces:
- spec.md §1, AC-1, AC-2, AC-3, AC-7, AC-8, AC-9, EC-1, EC-2, EC-3, EC-6, EC-7.
- Zero state mutation during compilation (AC-9).
"""

import json
from pathlib import Path

import pytest
from app.audit_report.compiler import (
    AuditReportCompiler,
    JobNotFoundError,
    ModelNotCompleteError,
    compile_audit_dataset,
)
from app.drift.models import DriftComparisonResult
from app.drift.repository import DriftRepository
from app.excel_export.models import (
    BoundingBoxCoordinates,
    W3CAnnotationRecord,
    W3CBody,
    W3CRefinedBy,
    W3CSelector,
    W3CTarget,
)
from app.excel_export.repository import ModelRepository
from app.extraction.models import (
    ConfidenceBand,
    ExtractedRecord,
    ScoredRecord,
)
from app.extraction.repository import ExtractionRepository
from app.ingestion.models import JobStatus
from app.ingestion.repository import JobRepository
from app.review.models import ReviewItem, ReviewStatus
from app.review.repository import ReviewRepository


def _make_w3c_record(
    job_id: str,
    sheet_name: str,
    cell_coord: str,
    node_id: str,
    value: str,
    label: str,
    original_label: str,
    page: int,
    bbox: tuple[float, float, float, float],
    is_formula: bool = False,
) -> W3CAnnotationRecord:
    coords = BoundingBoxCoordinates(
        x0=bbox[0],
        y0=bbox[1],
        x1=bbox[2],
        y1=bbox[3],
    )
    selector = W3CSelector(
        page=page,
        value=f"xywh=percent:{bbox[0]},{bbox[1]},{bbox[2]-bbox[0]},{bbox[3]-bbox[1]}",
        refinedBy=W3CRefinedBy(coordinates=coords),
    )
    target = W3CTarget(source=f"{job_id}.pdf", selector=selector)
    body = W3CBody(value=value, label=label, original_label=original_label)
    return W3CAnnotationRecord(
        id=f"urn:footnote:provenance:{job_id}:{node_id}",
        job_id=job_id,
        sheet_name=sheet_name,
        cell_coord=cell_coord,
        node_id=node_id,
        is_formula=is_formula,
        body=body,
        target=target,
    )


@pytest.fixture
def test_env(tmp_path: Path) -> dict[str, Path]:
    data_dir = tmp_path / "data"
    (data_dir / "uploads").mkdir(parents=True, exist_ok=True)
    (data_dir / "results").mkdir(parents=True, exist_ok=True)
    (data_dir / "models").mkdir(parents=True, exist_ok=True)
    return {"data_dir": data_dir}


def test_compile_raises_job_not_found(test_env: dict[str, Path]) -> None:
    compiler = AuditReportCompiler(data_dir=test_env["data_dir"])
    with pytest.raises(JobNotFoundError, match="Job 'missing-id' not found"):
        compiler.compile("missing-id")


def test_compile_raises_model_not_complete_when_provenance_missing(
    test_env: dict[str, Path],
) -> None:
    data_dir = test_env["data_dir"]
    job_repo = JobRepository(data_dir=data_dir)
    job_repo.save_job("test_2024.pdf", b"%PDF-1.4 dummy", "Adjusted EBITDA")
    jobs = job_repo.list_jobs()
    job_id = jobs[0].job_id

    compiler = AuditReportCompiler(data_dir=data_dir)
    with pytest.raises(ModelNotCompleteError, match="model generation not complete"):
        compiler.compile(job_id)


def test_compile_successful_with_full_provenance_and_zero_overrides(
    test_env: dict[str, Path],
) -> None:
    data_dir = test_env["data_dir"]
    job_repo = JobRepository(data_dir=data_dir)
    model_repo = ModelRepository(data_dir=data_dir)
    review_repo = ReviewRepository(data_dir=data_dir)
    extraction_repo = ExtractionRepository(data_dir=data_dir)

    job_rec = job_repo.save_job("Acme_2024_10K.pdf", b"%PDF-1.4 dummy", "Adjusted EBITDA")
    job_id = job_rec.job_id
    job_repo.update_job_status(job_id, JobStatus.done)

    # Scored records
    sr1 = ScoredRecord(
        record=ExtractedRecord(
            value="100000",
            label="Operating income",
            page=10,
            bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 250.0},
            source_file="Acme_2024_10K.pdf",
        ),
        confidence_score=0.99,
        confidence_band=ConfidenceBand.auto_accepted,
        flags=[],
    )
    extraction_repo.save_scored_records(job_id, [sr1])

    # Review state matching scored records (no edits)
    review_item = ReviewItem(
        id=f"{job_id}_0",
        value="100000",
        label="Operating income",
        page=10,
        bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 250.0},
        source_file="Acme_2024_10K.pdf",
        confidence_band=ConfidenceBand.auto_accepted,
        confidence_score=0.99,
        normalized_label="Operating Income",
        taxonomy_status="matched",
        status=ReviewStatus.auto_accepted,
    )
    review_repo.save_review_items(job_id, [review_item])

    # Provenance records
    rec1 = _make_w3c_record(
        job_id=job_id,
        sheet_name="Source_Inputs",
        cell_coord="B2",
        node_id="leaf_0_operating_income",
        value="100000",
        label="Operating Income",
        original_label="Operating income",
        page=10,
        bbox=(100.0, 200.0, 300.0, 250.0),
        is_formula=False,
    )
    rec2 = _make_w3c_record(
        job_id=job_id,
        sheet_name="Model_Summary",
        cell_coord="B2",
        node_id="root_adjusted_ebitda",
        value="=Source_Inputs!B2",
        label="Adjusted EBITDA",
        original_label="Adjusted EBITDA",
        page=10,
        bbox=(100.0, 200.0, 300.0, 250.0),
        is_formula=True,
    )
    model_repo.save_provenance_records(job_id, [rec1, rec2])

    compiler = AuditReportCompiler(data_dir=data_dir)
    dataset = compiler.compile(job_id)

    assert dataset.job_id == job_id
    assert dataset.metadata.entity == "Acme"
    assert dataset.metadata.filing_year == 2024
    assert dataset.metadata.total_cells == 2
    assert dataset.metadata.automated_count == 1
    assert dataset.has_manual_overrides is False
    assert len(dataset.manual_overrides) == 0
    assert len(dataset.provenance_matrix) == 2
    assert len(dataset.reconciliation_summary) == 1
    assert dataset.reconciliation_summary[0].cell_coord == "B2"


def test_compile_manual_overrides_and_hardcodes(
    test_env: dict[str, Path],
) -> None:
    data_dir = test_env["data_dir"]
    job_repo = JobRepository(data_dir=data_dir)
    model_repo = ModelRepository(data_dir=data_dir)
    review_repo = ReviewRepository(data_dir=data_dir)
    extraction_repo = ExtractionRepository(data_dir=data_dir)

    job_rec = job_repo.save_job("Delta_2023.pdf", b"%PDF-1.4 dummy", "Adjusted EBITDA")
    job_id = job_rec.job_id

    # Original scored record with bad extraction
    sr1 = ScoredRecord(
        record=ExtractedRecord(
            value="3500",
            label="Rent adj",
            page=15,
            bbox={"x0": 50.0, "y0": 100.0, "x1": 200.0, "y1": 150.0},
            source_file="Delta_2023.pdf",
        ),
        confidence_score=0.50,
        confidence_band=ConfidenceBand.manual_required,
        flags=["unparseable_value"],
        status="extraction_error",
        error_detail="Unparseable number format",
    )
    extraction_repo.save_scored_records(job_id, [sr1])

    # Review item edited and locked by human
    review_item = ReviewItem(
        id=f"{job_id}_0",
        value="35000",
        label="Rent Adjustment",
        page=15,
        bbox={"x0": 50.0, "y0": 100.0, "x1": 200.0, "y1": 150.0},
        source_file="Delta_2023.pdf",
        confidence_band=ConfidenceBand.manual_required,
        confidence_score=0.50,
        normalized_label="Operating Lease Adjustment",
        taxonomy_status="matched",
        status=ReviewStatus.locked,
    )
    review_repo.save_review_items(job_id, [review_item])

    rec1 = _make_w3c_record(
        job_id=job_id,
        sheet_name="Source_Inputs",
        cell_coord="B2",
        node_id="leaf_0_operating_lease_adjustment",
        value="35000",
        label="Operating Lease Adjustment",
        original_label="Rent Adjustment",
        page=15,
        bbox=(50.0, 100.0, 200.0, 150.0),
        is_formula=False,
    )
    # Hardcoded record
    rec_hardcode = _make_w3c_record(
        job_id=job_id,
        sheet_name="Source_Inputs",
        cell_coord="B3",
        node_id="hardcode_tax_rate",
        value="0.21",
        label="Tax Rate Hardcode",
        original_label="Tax Rate Hardcode",
        page=1,
        bbox=(0.0, 0.0, 1000.0, 1000.0),
        is_formula=False,
    )
    model_repo.save_provenance_records(job_id, [rec1, rec_hardcode])

    dataset = compile_audit_dataset(job_id, data_dir=data_dir)

    assert dataset.has_manual_overrides is True
    assert len(dataset.manual_overrides) == 2

    # Verify user edit override
    edit_override = next(o for o in dataset.manual_overrides if o.item_id == f"{job_id}_0")
    assert edit_override.original_value == "3500"
    assert edit_override.final_value == "35000"
    assert edit_override.original_label == "Rent adj"
    assert edit_override.final_label == "Rent Adjustment"
    assert edit_override.is_hardcode is False

    # Verify hardcode item
    hc_override = next(o for o in dataset.manual_overrides if o.is_hardcode is True)
    assert hc_override.item_id == "Source_Inputs!B3"
    assert hc_override.final_value == "0.21"


def test_compile_classifier_governance_numeric_free_log(
    test_env: dict[str, Path],
) -> None:
    data_dir = test_env["data_dir"]
    job_repo = JobRepository(data_dir=data_dir)
    model_repo = ModelRepository(data_dir=data_dir)

    job_rec = job_repo.save_job("LogTest_2024.pdf", b"%PDF-1.4 dummy", "Adjusted EBITDA")
    job_id = job_rec.job_id

    rec1 = _make_w3c_record(
        job_id=job_id,
        sheet_name="Source_Inputs",
        cell_coord="B2",
        node_id="leaf_0_sbc",
        value="50000",
        label="Stock-Based Compensation",
        original_label="SBC",
        page=12,
        bbox=(10.0, 20.0, 30.0, 40.0),
    )
    model_repo.save_provenance_records(job_id, [rec1])

    # Write decision log JSONL
    log_file = data_dir / "results" / f"{job_id}_decision_log.jsonl"
    entries = [
        {
            "job_id": job_id,
            "record_index": 0,
            "timestamp": "2026-08-17T12:00:00Z",
            "input_payload": {"label": "SBC", "structural_context": "Note 5"},
            "raw_response": {"label": "Stock-Based Compensation", "confidence": 0.96},
            "taxonomy_status": "matched",
            "resulting_state": "confirmed",
            "error_detail": None,
        },
        {
            "job_id": job_id,
            "record_index": 1,
            "timestamp": "2026-08-17T12:00:01Z",
            "input_payload": {"label": "Unknown item", "structural_context": None},
            "raw_response": {"label": "Special Adjustment", "confidence": 0.60},
            "taxonomy_status": "pending_taxonomy_confirmation",
            "resulting_state": "pending_confirmation",
            "error_detail": None,
        },
    ]
    with log_file.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")

    compiler = AuditReportCompiler(data_dir=data_dir)
    dataset = compiler.compile(job_id)

    gov = dataset.classifier_governance
    assert gov.total_calls == 2
    assert gov.matched_count == 1
    assert gov.pending_count == 1
    assert gov.error_count == 0
    assert gov.is_strictly_numeric_free is True
    assert len(gov.entries) == 2
    assert gov.entries[0].input_label == "SBC"
    assert gov.entries[0].output_label == "Stock-Based Compensation"


def test_compile_drift_baseline_and_redefinition(
    test_env: dict[str, Path],
) -> None:
    data_dir = test_env["data_dir"]
    job_repo = JobRepository(data_dir=data_dir)
    model_repo = ModelRepository(data_dir=data_dir)
    drift_repo = DriftRepository(data_dir=data_dir)

    job_rec = job_repo.save_job("DriftTest_2024.pdf", b"%PDF-1.4 dummy", "Adjusted EBITDA")
    job_id = job_rec.job_id

    rec1 = _make_w3c_record(
        job_id=job_id,
        sheet_name="Source_Inputs",
        cell_coord="B2",
        node_id="leaf_0_sbc",
        value="50000",
        label="Stock-Based Compensation",
        original_label="SBC",
        page=12,
        bbox=(10.0, 20.0, 30.0, 40.0),
    )
    model_repo.save_provenance_records(job_id, [rec1])

    # Case A: Drift Baseline Result
    comp_res = DriftComparisonResult(
        entity="DriftTest",
        target_metric="Adjusted EBITDA",
        filing_year=2024,
        is_baseline=True,
        added_labels=[],
        removed_labels=[],
        unchanged_labels=["Stock-Based Compensation"],
        current_labels=["Stock-Based Compensation"],
        prior_node_id=None,
        has_discrepancy=False,
    )
    drift_repo.save_comparison_result(job_id, comp_res)

    dataset = compile_audit_dataset(job_id, data_dir=data_dir)
    assert dataset.drift_summary.is_evaluated is True
    assert dataset.drift_summary.is_baseline is True
    assert dataset.drift_summary.has_discrepancy is False
    assert "Baseline Year" in dataset.drift_summary.summary_text

    # Case B: Drift Redefinition Result
    comp_redef = DriftComparisonResult(
        entity="DriftTest",
        target_metric="Adjusted EBITDA",
        filing_year=2024,
        is_baseline=False,
        added_labels=["Litigation Expense"],
        removed_labels=["Lease Expense"],
        unchanged_labels=["Stock-Based Compensation"],
        current_labels=["Stock-Based Compensation", "Litigation Expense"],
        prior_node_id="DriftTest_Adjusted EBITDA_2023",
        has_discrepancy=True,
    )
    drift_repo.save_comparison_result(job_id, comp_redef)

    dataset2 = compile_audit_dataset(job_id, data_dir=data_dir)
    assert dataset2.drift_summary.is_baseline is False
    assert dataset2.drift_summary.has_discrepancy is True
    assert dataset2.drift_summary.added_labels == ["Litigation Expense"]
    assert dataset2.drift_summary.removed_labels == ["Lease Expense"]
    assert "Metric Redefinition Detected" in dataset2.drift_summary.summary_text


def test_compile_is_read_only_and_preserves_state(
    test_env: dict[str, Path],
) -> None:
    data_dir = test_env["data_dir"]
    job_repo = JobRepository(data_dir=data_dir)
    model_repo = ModelRepository(data_dir=data_dir)

    job_rec = job_repo.save_job("PureTest_2024.pdf", b"%PDF-1.4 dummy", "Adjusted EBITDA")
    job_id = job_rec.job_id

    rec1 = _make_w3c_record(
        job_id=job_id,
        sheet_name="Source_Inputs",
        cell_coord="B2",
        node_id="leaf_0_sbc",
        value="50000",
        label="Stock-Based Compensation",
        original_label="SBC",
        page=12,
        bbox=(10.0, 20.0, 30.0, 40.0),
    )
    model_repo.save_provenance_records(job_id, [rec1])

    # Record timestamps/hashes of files
    prov_file = data_dir / "models" / f"{job_id}_provenance.json"
    content_before = prov_file.read_text(encoding="utf-8")

    compiler = AuditReportCompiler(data_dir=data_dir)
    _ = compiler.compile(job_id)

    content_after = prov_file.read_text(encoding="utf-8")
    assert content_before == content_after
