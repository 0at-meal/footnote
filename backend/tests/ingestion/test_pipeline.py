"""
Unit tests for app.job_runner.process_queued_job.

Verifies:
- State transition from queued -> extracting -> done upon completion.
- State transition to failed if processing encounters an error.
"""

from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytest
from app.extraction.models import DoclingBbox, DoclingItem
from app.ingestion.models import JobStatus
from app.ingestion.repository import JobRepository
from app.job_runner import process_queued_job


def make_minimal_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page()
    return doc.tobytes()  # type: ignore[no-any-return]


def test_process_queued_job_transitions_to_done(tmp_path: Path) -> None:
    repo = JobRepository(data_dir=tmp_path)
    job = repo.save_job("report.pdf", make_minimal_pdf(), "Adjusted EBITDA")
    assert job.status == JobStatus.queued

    dummy_item = DoclingItem(
        value="100",
        label="EBITDA",
        page=1,
        bbox=DoclingBbox(x0=0, y0=0, x1=10, y1=10),
        source_file="report.pdf",
    )

    with patch("app.job_runner.parse_pdf", return_value=[dummy_item]):
        process_queued_job(job.job_id, repo)

    updated = repo.get_job(job.job_id)
    assert updated is not None
    assert updated.status == JobStatus.done

    # Verify intermediate docling file was persisted
    saved_docling_file = tmp_path / "results" / f"{job.job_id}_docling.json"
    assert saved_docling_file.exists()


def test_process_queued_job_transitions_to_failed_on_error(tmp_path: Path) -> None:
    repo = JobRepository(data_dir=tmp_path)
    job = repo.save_job("fail.pdf", make_minimal_pdf(), "Adjusted EBITDA")

    with (
        patch("app.job_runner.parse_pdf", side_effect=RuntimeError("Docling error")),
        pytest.raises(RuntimeError, match="Docling error"),
    ):
        process_queued_job(job.job_id, repo)

    updated = repo.get_job(job.job_id)
    assert updated is not None
    assert updated.status == JobStatus.failed
