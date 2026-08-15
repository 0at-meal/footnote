"""
Tests for GET /review/{job_id}/pdf endpoint (Feature 5 Step 1).

Validates:
- 200 streams raw PDF bytes for valid job + existing file
- 404 returned when job does not exist in job store
- 404 returned when job exists but PDF binary is missing on disk (EC-7)
"""

from pathlib import Path
from unittest.mock import patch

from app.ingestion.repository import JobRepository
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_get_job_pdf_success_200(tmp_path: Path) -> None:
    job_repo = JobRepository(data_dir=tmp_path)
    job = job_repo.save_job(
        filename="apple_10k.pdf",
        content=b"%PDF-1.4 test binary stream",
        target_metric="Adjusted EBITDA",
    )

    with patch("app.review.router._job_repo", job_repo):
        response = client.get(f"/review/{job.job_id}/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == b"%PDF-1.4 test binary stream"


def test_get_job_pdf_job_not_found_404(tmp_path: Path) -> None:
    job_repo = JobRepository(data_dir=tmp_path)

    with patch("app.review.router._job_repo", job_repo):
        response = client.get("/review/non-existent-job-uuid/pdf")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_get_job_pdf_file_missing_404(tmp_path: Path) -> None:
    job_repo = JobRepository(data_dir=tmp_path)
    job = job_repo.save_job(
        filename="apple_10k.pdf",
        content=b"%PDF-1.4 test binary stream",
        target_metric="Adjusted EBITDA",
    )

    # Delete the stored PDF to simulate missing file (EC-7)
    pdf_path = job_repo.get_pdf_path(job.job_id)
    pdf_path.unlink()

    with patch("app.review.router._job_repo", job_repo):
        response = client.get(f"/review/{job.job_id}/pdf")

    assert response.status_code == 404
    assert response.json()["detail"] == "Source PDF unavailable"
