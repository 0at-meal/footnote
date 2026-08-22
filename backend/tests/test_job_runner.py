"""
Unit and integration tests for Job Runner draft model generation and model_ready propagation (Ticket 0.4.4).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.classification.models import ClassifierRawResponse
from app.extraction.models import (
    ConfidenceBand,
    DoclingBbox,
    DoclingItem,
    ExtractedRecord,
    ExtractionSummary,
    NormalizedBbox,
    NormalizedItem,
    ScoredRecord,
)
from app.ingestion.models import JobStatus
from app.ingestion.repository import JobRepository
from app.job_runner import process_queued_job


def test_job_runner_auto_accepted_generates_draft_model(tmp_path: Path) -> None:
    """Verifies that job runner with auto-accepted records generates .xlsx and sets model_ready=True."""
    repo = JobRepository(data_dir=tmp_path)
    repo.save_job(
        filename="apple_report.pdf",
        content=b"%PDF-1.4 dummy",
        target_metric="Adjusted EBITDA",
    )
    job_id = repo.list_jobs()[0].job_id

    sample_docling = [
        DoclingItem(
            value="500.0",
            label="Operating Expenses / Stock-based comp",
            page=1,
            bbox=DoclingBbox(x0=10.0, y0=20.0, x1=30.0, y1=40.0),
            source_file="apple_report.pdf",
            table_name="Reconciliation of Non-GAAP Adjusted EBITDA",
            is_reconciliation_candidate=True,
        )
    ]
    sample_normalized = [
        NormalizedItem(
            value="500.0",
            label="Operating Expenses / Stock-based comp",
            page=1,
            bbox=NormalizedBbox(x0=100.0, y0=200.0, x1=300.0, y1=400.0),
            source_file="apple_report.pdf",
            table_name="Reconciliation of Non-GAAP Adjusted EBITDA",
            is_reconciliation_candidate=True,
        )
    ]
    sample_records = [
        ExtractedRecord(
            value="500.0",
            label="Operating Expenses / Stock-based comp",
            page=1,
            bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 400.0},
            source_file="apple_report.pdf",
            is_reconciliation_candidate=True,
        )
    ]
    sample_scored = [
        ScoredRecord(
            record=sample_records[0],
            confidence_score=0.99,
            confidence_band=ConfidenceBand.auto_accepted,
            flags=[],
            table_name="Reconciliation of Non-GAAP Adjusted EBITDA",
            is_reconciliation_candidate=True,
        )
    ]
    sample_summary = ExtractionSummary(
        total_items=1,
        auto_accepted_count=1,
        needs_review_count=0,
        manual_required_count=0,
        extraction_error_count=0,
        flagged_count=0,
        flagged_percentage=0.0,
        passed_threshold=True,
    )

    mock_classifier = MagicMock()
    mock_classifier.classify.return_value = ClassifierRawResponse(
        label="Stock-Based Compensation",
        confidence=0.99,
    )

    with (
        patch("app.job_runner.parse_pdf", return_value=sample_docling),
        patch("app.job_runner.normalize_coordinates", return_value=sample_normalized),
        patch("app.job_runner.assemble_records", return_value=sample_records),
        patch("app.job_runner.score_records", return_value=sample_scored),
        patch("app.job_runner.count_image_only_pages", return_value=0),
        patch("app.job_runner.create_extraction_summary", return_value=sample_summary),
    ):
        process_queued_job(job_id, repo, classifier_client=mock_classifier)

    updated_job = repo.get_job(job_id)
    assert updated_job is not None
    assert updated_job.status == JobStatus.done
    assert updated_job.model_ready is True

    # Assert .xlsx file exists
    model_path = tmp_path / "models" / f"{job_id}_model.xlsx"
    assert model_path.exists()
    assert model_path.stat().st_size > 0


def test_job_runner_zero_auto_accepted_sets_model_ready_false(tmp_path: Path) -> None:
    """Verifies that job runner with zero auto-accepted records sets model_ready=False and does not write .xlsx."""
    repo = JobRepository(data_dir=tmp_path)
    repo.save_job(
        filename="unclear_report.pdf",
        content=b"%PDF-1.4 dummy",
        target_metric="Adjusted EBITDA",
    )
    job_id = repo.list_jobs()[0].job_id

    sample_docling = [
        DoclingItem(
            value="20.0",
            label="Ambiguous Item",
            page=1,
            bbox=DoclingBbox(x0=10.0, y0=20.0, x1=30.0, y1=40.0),
            source_file="unclear_report.pdf",
        )
    ]
    sample_normalized = [
        NormalizedItem(
            value="20.0",
            label="Ambiguous Item",
            page=1,
            bbox=NormalizedBbox(x0=100.0, y0=200.0, x1=300.0, y1=400.0),
            source_file="unclear_report.pdf",
        )
    ]
    sample_records = [
        ExtractedRecord(
            value="20.0",
            label="Ambiguous Item",
            page=1,
            bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 400.0},
            source_file="unclear_report.pdf",
        )
    ]
    sample_scored = [
        ScoredRecord(
            record=sample_records[0],
            confidence_score=0.75,
            confidence_band=ConfidenceBand.needs_review,
            flags=["low_confidence"],
        )
    ]
    sample_summary = ExtractionSummary(
        total_items=1,
        auto_accepted_count=0,
        needs_review_count=1,
        manual_required_count=0,
        extraction_error_count=0,
        flagged_count=1,
        flagged_percentage=100.0,
        passed_threshold=False,
    )

    mock_classifier = MagicMock()
    mock_classifier.classify.return_value = ClassifierRawResponse(
        label="Uncertain Item",
        confidence=0.70,
    )

    with (
        patch("app.job_runner.parse_pdf", return_value=sample_docling),
        patch("app.job_runner.normalize_coordinates", return_value=sample_normalized),
        patch("app.job_runner.assemble_records", return_value=sample_records),
        patch("app.job_runner.score_records", return_value=sample_scored),
        patch("app.job_runner.count_image_only_pages", return_value=0),
        patch("app.job_runner.create_extraction_summary", return_value=sample_summary),
    ):
        process_queued_job(job_id, repo, classifier_client=mock_classifier)

    updated_job = repo.get_job(job_id)
    assert updated_job is not None
    assert updated_job.status == JobStatus.done
    assert updated_job.model_ready is False

    # Assert .xlsx file does NOT exist
    model_path = tmp_path / "models" / f"{job_id}_model.xlsx"
    assert not model_path.exists()


def test_job_repository_model_ready_roundtrip(tmp_path: Path) -> None:
    """Verifies that model_ready field persists across JobRepository instances."""
    repo1 = JobRepository(data_dir=tmp_path)
    created = repo1.save_job(
        filename="doc.pdf",
        content=b"%PDF-1.4 mock",
        target_metric="Adjusted EBITDA",
    )
    assert created.model_ready is False

    # Update to done with model_ready=True
    updated = repo1.update_job_status(created.job_id, JobStatus.done, model_ready=True)
    assert updated is not None
    assert updated.model_ready is True

    # Fresh repository instance reading from disk
    repo2 = JobRepository(data_dir=tmp_path)
    fetched = repo2.get_job(created.job_id)
    assert fetched is not None
    assert fetched.model_ready is True

    all_jobs = repo2.list_jobs()
    assert len(all_jobs) == 1
    assert all_jobs[0].model_ready is True


def test_job_runner_filters_non_reconciliation_candidates_before_classification(
    tmp_path: Path,
) -> None:
    """Verifies that non-reconciliation candidate records are excluded from classifier dispatch."""
    repo = JobRepository(data_dir=tmp_path)
    repo.save_job(
        filename="filing_2023.pdf",
        content=b"%PDF-1.4 dummy",
        target_metric="Adjusted EBITDA",
    )
    job_id = repo.list_jobs()[0].job_id

    # Item 1: Reconciliation item
    rec1 = ExtractedRecord(
        value="50.0",
        label="Operating Expenses / Stock-based comp",
        page=1,
        bbox={"x0": 0.0, "y0": 0.0, "x1": 10.0, "y1": 10.0},
        source_file="filing_2023.pdf",
        is_reconciliation_candidate=True,
    )
    scored1 = ScoredRecord(
        record=rec1,
        confidence_score=0.99,
        confidence_band=ConfidenceBand.auto_accepted,
        flags=[],
        table_name="Reconciliation of Non-GAAP Adjusted EBITDA",
        is_reconciliation_candidate=True,
    )

    # Item 2: Balance sheet item (not a candidate)
    rec2 = ExtractedRecord(
        value="1000.0",
        label="Assets / Cash and cash equivalents",
        page=2,
        bbox={"x0": 0.0, "y0": 0.0, "x1": 10.0, "y1": 10.0},
        source_file="filing_2023.pdf",
        is_reconciliation_candidate=False,
    )
    scored2 = ScoredRecord(
        record=rec2,
        confidence_score=0.99,
        confidence_band=ConfidenceBand.auto_accepted,
        flags=[],
        table_name="Consolidated Balance Sheets",
        is_reconciliation_candidate=False,
    )

    mock_classifier = MagicMock()
    mock_classifier.classify.return_value = ClassifierRawResponse(
        label="Stock-Based Compensation",
        confidence=0.99,
    )

    sample_docling = [
        DoclingItem(
            value="50.0",
            label="Operating Expenses / Stock-based comp",
            page=1,
            bbox=DoclingBbox(x0=0.0, y0=0.0, x1=10.0, y1=10.0),
            source_file="filing_2023.pdf",
            table_name="Reconciliation of Non-GAAP Adjusted EBITDA",
            is_reconciliation_candidate=True,
        ),
        DoclingItem(
            value="1000.0",
            label="Assets / Cash and cash equivalents",
            page=2,
            bbox=DoclingBbox(x0=0.0, y0=0.0, x1=10.0, y1=10.0),
            source_file="filing_2023.pdf",
            table_name="Consolidated Balance Sheets",
            is_reconciliation_candidate=False,
        ),
    ]

    sample_normalized = [
        NormalizedItem(
            value="50.0",
            label="Operating Expenses / Stock-based comp",
            page=1,
            bbox=NormalizedBbox(x0=0.0, y0=0.0, x1=10.0, y1=10.0),
            source_file="filing_2023.pdf",
            table_name="Reconciliation of Non-GAAP Adjusted EBITDA",
            is_reconciliation_candidate=True,
        ),
        NormalizedItem(
            value="1000.0",
            label="Assets / Cash and cash equivalents",
            page=2,
            bbox=NormalizedBbox(x0=0.0, y0=0.0, x1=10.0, y1=10.0),
            source_file="filing_2023.pdf",
            table_name="Consolidated Balance Sheets",
            is_reconciliation_candidate=False,
        ),
    ]

    with (
        patch("app.job_runner.parse_pdf", return_value=sample_docling),
        patch("app.job_runner.normalize_coordinates", return_value=sample_normalized),
        patch("app.job_runner.assemble_records", return_value=[rec1, rec2]),
        patch("app.job_runner.score_records", return_value=[scored1, scored2]),
        patch("app.job_runner.count_image_only_pages", return_value=0),
    ):
        process_queued_job(job_id, repo, classifier_client=mock_classifier)

    # Verify classifier called exactly once (for the reconciliation item only)
    assert mock_classifier.classify.call_count == 1
    call_args = mock_classifier.classify.call_args[0][0]
    assert call_args.label == "Operating Expenses / Stock-based comp"
