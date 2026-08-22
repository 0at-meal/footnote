"""
Integration unit tests for full extraction and classification pipeline orchestration in app/job_runner.py.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
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


@pytest.fixture
def mock_job_repo(tmp_path: Path) -> JobRepository:
    repo = JobRepository(data_dir=tmp_path)
    repo.save_job(
        filename="filing.pdf",
        content=b"%PDF-1.4 dummy",
        target_metric="Adjusted EBITDA",
    )
    return repo


def test_process_queued_job_runs_full_pipeline(
    tmp_path: Path, mock_job_repo: JobRepository
) -> None:
    """process_queued_job runs all extraction and classification stages and updates status to done."""
    job_id = mock_job_repo.list_jobs()[0].job_id

    sample_docling = [
        DoclingItem(
            value="100",
            label="Revenue",
            page=1,
            bbox=DoclingBbox(x0=10.0, y0=20.0, x1=30.0, y1=40.0),
            source_file="filing.pdf",
            table_name="Reconciliation of Non-GAAP Adjusted EBITDA",
            is_reconciliation_candidate=True,
        )
    ]
    sample_normalized = [
        NormalizedItem(
            value="100",
            label="Revenue",
            page=1,
            bbox=NormalizedBbox(x0=100.0, y0=200.0, x1=300.0, y1=400.0),
            source_file="filing.pdf",
            table_name="Reconciliation of Non-GAAP Adjusted EBITDA",
            is_reconciliation_candidate=True,
        )
    ]
    sample_records = [
        ExtractedRecord(
            value="100",
            label="Revenue",
            page=1,
            bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 400.0},
            source_file="filing.pdf",
            is_reconciliation_candidate=True,
        )
    ]
    sample_scored = [
        ScoredRecord(
            record=sample_records[0],
            confidence_score=1.0,
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
        confidence=0.98,
    )

    with (
        patch("app.job_runner.parse_pdf", return_value=sample_docling) as mock_parse,
        patch(
            "app.job_runner.normalize_coordinates", return_value=sample_normalized
        ) as mock_norm,
        patch(
            "app.job_runner.assemble_records", return_value=sample_records
        ) as mock_assemble,
        patch("app.job_runner.score_records", return_value=sample_scored) as mock_score,
        patch(
            "app.job_runner.count_image_only_pages", return_value=0
        ) as mock_count_pages,
        patch(
            "app.job_runner.create_extraction_summary", return_value=sample_summary
        ) as mock_summary,
    ):
        process_queued_job(
            job_id,
            mock_job_repo,
            classifier_client=mock_classifier,
        )

    mock_parse.assert_called_once()
    mock_norm.assert_called_once()
    mock_assemble.assert_called_once()
    mock_score.assert_called_once()
    mock_count_pages.assert_called_once()
    mock_summary.assert_called_once()
    mock_classifier.classify.assert_called_once()

    updated_job = mock_job_repo.get_job(job_id)
    assert updated_job is not None
    assert updated_job.status == JobStatus.done
    assert updated_job.model_ready is True

    results_dir = tmp_path / "results"
    assert (results_dir / f"{job_id}_docling.json").exists()
    assert (results_dir / f"{job_id}_normalized.json").exists()
    assert (results_dir / f"{job_id}_records.json").exists()
    assert (results_dir / f"{job_id}_scored.json").exists()
    assert (results_dir / f"{job_id}_summary.json").exists()
    assert (results_dir / f"{job_id}_classified.json").exists()
    assert (results_dir / f"{job_id}_decision_log.jsonl").exists()

    models_dir = tmp_path / "models"
    assert (models_dir / f"{job_id}_model.xlsx").exists()
    assert (models_dir / f"{job_id}_provenance.json").exists()
    assert (models_dir / f"{job_id}_generation.json").exists()


def test_process_queued_job_failure_updates_status_to_failed(
    mock_job_repo: JobRepository,
) -> None:
    """An unrecoverable exception in pipeline updates job status to failed."""
    job_id = mock_job_repo.list_jobs()[0].job_id

    with (
        patch(
            "app.job_runner.parse_pdf", side_effect=RuntimeError("Docling model crash")
        ),
        pytest.raises(RuntimeError, match="Docling model crash"),
    ):
        process_queued_job(job_id, mock_job_repo)

    updated_job = mock_job_repo.get_job(job_id)
    assert updated_job is not None
    assert updated_job.status == JobStatus.failed
