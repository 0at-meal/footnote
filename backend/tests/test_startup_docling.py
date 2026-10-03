"""
AUD-003 part 1 / decision D1: missing Docling must never be silent.

- Default: the server refuses to start with a clear error.
- ALLOW_PYMUPDF_FALLBACK=1: /health reports degraded and every job is stamped with the
  parser and the fallback reason.

Docling *is* installed in the test venv, so its absence is simulated by setting the module's
recorded import error, which is exactly what the module sets when the import fails.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app.classification.models import ClassifierRawResponse
from app.extraction import docling_parser
from app.ingestion.models import JobStatus
from app.ingestion.repository import JobRepository
from app.job_runner import process_queued_job
from app.main import app
from fastapi.testclient import TestClient

from tests.fixtures.synthetic.pdfs import SYNTHETIC_BALANCE_SHEET, write_synthetic_pdf

MISSING = "ModuleNotFoundError: No module named 'docling'"


@pytest.fixture
def docling_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docling_parser, "DOCLING_IMPORT_ERROR", MISSING, raising=False)


def _submit(tmp_path: Path) -> tuple[JobRepository, str]:
    repo = JobRepository(data_dir=tmp_path)
    pdf = write_synthetic_pdf(tmp_path / "synthetic_balance_sheet.pdf", [SYNTHETIC_BALANCE_SHEET])
    job = repo.save_job(
        filename="synthetic_balance_sheet.pdf",
        content=pdf.read_bytes(),
        target_metric="Adjusted EBITDA",
        filing_year=2025,
        workflow_pack="capital_structure",
    )
    return repo, job.job_id


def _classifier() -> MagicMock:
    client = MagicMock()
    client.classify.return_value = ClassifierRawResponse(label="Other", confidence=0.5)
    return client


def test_server_refuses_to_start_without_docling(
    docling_missing: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ALLOW_PYMUPDF_FALLBACK", raising=False)
    with pytest.raises(RuntimeError, match="Docling"), TestClient(app):
        pass


def test_degraded_mode_health_reports_fallback(
    docling_missing: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALLOW_PYMUPDF_FALLBACK", "1")
    with TestClient(app) as client:
        body = client.get("/health").json()
    assert body["status"] == "degraded"
    assert body["docling_available"] is False
    assert body["parser_mode"] == "pymupdf_fallback"
    assert "Docling" in body["degraded_reason"]


def test_degraded_job_is_stamped_with_parser_and_reason(
    docling_missing: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ALLOW_PYMUPDF_FALLBACK", "1")
    repo, job_id = _submit(tmp_path)
    process_queued_job(job_id, repo, classifier_client=_classifier())
    job = repo.get_job(job_id)
    assert job is not None
    assert job.parser_used == "pymupdf"
    assert job.parser_fallback_reason is not None
    assert "Docling unavailable" in job.parser_fallback_reason


def test_job_fails_with_reason_when_docling_missing_and_fallback_not_allowed(
    docling_missing: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ALLOW_PYMUPDF_FALLBACK", raising=False)
    repo, job_id = _submit(tmp_path)
    with pytest.raises(docling_parser.DoclingParseError):
        process_queued_job(job_id, repo, classifier_client=_classifier())
    job = repo.get_job(job_id)
    assert job is not None
    assert job.status == JobStatus.failed
    assert job.failure_reason is not None
    assert "Docling is not installed" in job.failure_reason


def test_healthy_server_reports_docling() -> None:
    with TestClient(app) as client:
        body = client.get("/health").json()
    assert body["docling_available"] is True
    assert body["parser_mode"] == "docling"
    assert body["degraded_reason"] is None
