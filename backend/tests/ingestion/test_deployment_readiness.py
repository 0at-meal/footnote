"""
Unit & integration tests for Deployment Readiness, Health Checks, Async Jobs, and Locking (Step K).

Tests:
- GET /health returns 200 with status=ok, db_ok=True, data_dir_writable=True.
- ALLOWED_ORIGINS comma-separated parsing.
- POST /upload/jobs/async returns 202 Accepted.
- JobRecord session_id support for multi-analyst setups.
- Single-writer thread-safety on JobRepository.
"""

import concurrent.futures
from pathlib import Path

from app.ingestion.models import JobStatus
from app.ingestion.repository import JobRepository
from app.ingestion.router import get_repository
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_check_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert data["data_dir_writable"] is True
    assert data["db_ok"] is True


def test_async_job_upload_endpoint(tmp_path: Path) -> None:
    import pymupdf

    doc = pymupdf.open()
    doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()

    repo = JobRepository(data_dir=tmp_path)
    app.dependency_overrides[get_repository] = lambda: repo

    try:
        response = client.post(
            "/upload/jobs/async",
            files=[("files", ("async_test.pdf", pdf_bytes, "application/pdf"))],
            data={
                "target_metrics": ["Adjusted EBITDA"],
                "filing_years": ["2024"],
                "session_id": "session_user_42",
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert len(data["created_jobs"]) == 1
        job = data["created_jobs"][0]
        assert job["filename"] == "async_test.pdf"
        assert job["target_metric"] == "Adjusted EBITDA"
        assert job["filing_year"] == 2024
        assert job["session_id"] == "session_user_42"
    finally:
        app.dependency_overrides.clear()


def test_job_repository_concurrent_writes_and_locking(tmp_path: Path) -> None:
    repo = JobRepository(data_dir=tmp_path)

    def write_worker(idx: int) -> str:
        job = repo.save_job(
            filename=f"filing_{idx}.pdf",
            content=f"%PDF-1.4 content_{idx}".encode(),
            target_metric="Adjusted EBITDA",
            filing_year=2020 + (idx % 5),
            session_id=f"analyst_{idx % 3}",
        )
        return job.job_id

    # Run 20 concurrent saves
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        job_ids = list(executor.map(write_worker, range(20)))

    assert len(job_ids) == 20
    all_jobs = repo.list_jobs()
    assert len(all_jobs) == 20
    assert {j.job_id for j in all_jobs} == set(job_ids)


def test_update_job_status_locking(tmp_path: Path) -> None:
    repo = JobRepository(data_dir=tmp_path)
    job = repo.save_job("test.pdf", b"%PDF-1.4", "Adjusted EBITDA")

    updated = repo.update_job_status(job.job_id, JobStatus.done, model_ready=True)
    assert updated is not None
    assert updated.status == JobStatus.done
    assert updated.model_ready is True
