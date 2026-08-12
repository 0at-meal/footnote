"""
Unit tests for app.ingestion.pipeline.process_queued_job.

Verifies:
- State transition from queued -> extracting -> done upon completion.
- State transition to failed if processing encounters an error.
"""

from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytest

from app.ingestion.models import JobStatus
from app.ingestion.pipeline import process_queued_job
from app.ingestion.repository import JobRepository


def make_minimal_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page()
    return doc.tobytes()  # type: ignore[no-any-return]


def test_process_queued_job_transitions_to_done(tmp_path: Path) -> None:
    repo = JobRepository(data_dir=tmp_path)
    job = repo.save_job("report.pdf", make_minimal_pdf(), "Adjusted EBITDA")
    assert job.status == JobStatus.queued

    with patch("time.sleep", return_value=None):
        process_queued_job(job.job_id, repo)

    updated = repo.list_jobs()[0]
    assert updated.status == JobStatus.done


def test_process_queued_job_transitions_to_failed_on_error(tmp_path: Path) -> None:
    repo = JobRepository(data_dir=tmp_path)
    job = repo.save_job("fail.pdf", make_minimal_pdf(), "Adjusted EBITDA")

    with patch("time.sleep", side_effect=RuntimeError("Extraction failed")):
        with pytest.raises(RuntimeError, match="Extraction failed"):
            process_queued_job(job.job_id, repo)

    updated = repo.list_jobs()[0]
    assert updated.status == JobStatus.failed
