"""
Integration tests for POST /upload/jobs and GET /upload/jobs.

Uses FastAPI's TestClient (synchronous wrapper around the async app).
Each test uses a fresh tmp_path-backed JobRepository injected via
FastAPI's dependency_overrides mechanism — no real data/ directory is
ever created or touched.

Tests verify the HTTP contract: status codes, JSON shape, per-file result
semantics, and spec edge cases. Internal repository logic is tested in
test_repository.py, not here.
"""

import io
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.ingestion.router import get_repository
from app.ingestion.repository import JobRepository
from app.main import app


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_minimal_pdf() -> bytes:
    """Real, parseable, unencrypted PDF — one blank page."""
    doc = pymupdf.open()
    doc.new_page()
    return doc.tobytes()  # type: ignore[no-any-return]


def pdf_file(filename: str, content: bytes) -> tuple[str, tuple[str, io.BytesIO, str]]:
    return ("files", (filename, io.BytesIO(content), "application/pdf"))


def bad_file(filename: str, content: bytes) -> tuple[str, tuple[str, io.BytesIO, str]]:
    return ("files", (filename, io.BytesIO(content), "application/octet-stream"))


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:  # type: ignore[misc]
    """TestClient with the repository wired to a fresh tmp_path directory."""
    repo = JobRepository(data_dir=tmp_path)
    app.dependency_overrides[get_repository] = lambda: repo
    yield TestClient(app)  # type: ignore[misc]
    app.dependency_overrides.clear()


# ── POST /upload/jobs ─────────────────────────────────────────────────────────


def test_single_valid_pdf_creates_one_job(client: TestClient) -> None:
    """Test 1: one accepted file → one created_job, zero rejections."""
    pdf = make_minimal_pdf()
    response = client.post(
        "/upload/jobs",
        files=[pdf_file("annual.pdf", pdf)],
        data={"target_metrics": "Adjusted EBITDA"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["created_jobs"]) == 1
    assert len(body["rejections"]) == 0


def test_single_invalid_file_returns_rejection(client: TestClient) -> None:
    """Test 2: one rejected file → zero created_jobs, one rejection."""
    response = client.post(
        "/upload/jobs",
        files=[bad_file("resume.docx", b"not a pdf")],
        data={"target_metrics": "EBITDA"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["created_jobs"]) == 0
    assert len(body["rejections"]) == 1
    assert body["rejections"][0]["filename"] == "resume.docx"


def test_mix_of_valid_and_invalid_splits_correctly(client: TestClient) -> None:
    """Test 3: valid + invalid → correct split; neither blocks the other (EC-7)."""
    pdf = make_minimal_pdf()
    response = client.post(
        "/upload/jobs",
        files=[
            pdf_file("valid.pdf", pdf),
            bad_file("bad.txt", b"plain text"),
        ],
        data={"target_metrics": ["Adjusted EBITDA", "Net Income"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["created_jobs"]) == 1
    assert len(body["rejections"]) == 1
    assert body["created_jobs"][0]["filename"] == "valid.pdf"
    assert body["rejections"][0]["filename"] == "bad.txt"


def test_mismatched_files_and_metrics_returns_422(client: TestClient) -> None:
    """Test 4: len(files) != len(target_metrics) → 422 Unprocessable Entity."""
    pdf = make_minimal_pdf()
    response = client.post(
        "/upload/jobs",
        files=[
            pdf_file("a.pdf", pdf),
            pdf_file("b.pdf", pdf),
        ],
        data={"target_metrics": "Adjusted EBITDA"},  # only 1 metric for 2 files
    )
    assert response.status_code == 422


def test_same_filename_twice_produces_distinct_job_ids(client: TestClient) -> None:
    """Test 5: EC-1 — same filename → two separate records with distinct job_ids."""
    pdf = make_minimal_pdf()
    response = client.post(
        "/upload/jobs",
        files=[
            pdf_file("annual.pdf", pdf),
            pdf_file("annual.pdf", pdf),
        ],
        data={"target_metrics": ["Adjusted EBITDA", "EBITDA"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["created_jobs"]) == 2
    ids = [j["job_id"] for j in body["created_jobs"]]
    assert ids[0] != ids[1]


# ── GET /upload/jobs ──────────────────────────────────────────────────────────


def test_get_jobs_returns_all_submitted_jobs(client: TestClient) -> None:
    """Test 6: GET /upload/jobs returns previously submitted records."""
    pdf = make_minimal_pdf()
    client.post(
        "/upload/jobs",
        files=[pdf_file("q1.pdf", pdf)],
        data={"target_metrics": "Adjusted EBITDA"},
    )
    client.post(
        "/upload/jobs",
        files=[pdf_file("q2.pdf", pdf)],
        data={"target_metrics": "EBITDA"},
    )

    response = client.get("/upload/jobs")
    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert len(jobs) == 2


def test_get_jobs_returns_empty_list_before_any_submissions(client: TestClient) -> None:
    """Test 7: GET /upload/jobs returns {"jobs": []} when no jobs exist."""
    response = client.get("/upload/jobs")
    assert response.status_code == 200
    body = response.json()
    assert body == {"jobs": []}


# ── JobRecord field validation ────────────────────────────────────────────────


def test_created_job_has_all_required_fields(client: TestClient) -> None:
    """Test 8: created_job includes all spec-mandated fields (spec AC-5)."""
    pdf = make_minimal_pdf()
    response = client.post(
        "/upload/jobs",
        files=[pdf_file("report.pdf", pdf)],
        data={"target_metrics": "Free Cash Flow"},
    )
    job = response.json()["created_jobs"][0]
    required = {"job_id", "filename", "file_size_bytes", "status", "target_metric", "submitted_at"}
    assert required.issubset(job.keys())
    assert isinstance(job["job_id"], str) and len(job["job_id"]) > 0
    assert job["filename"] == "report.pdf"
    assert isinstance(job["file_size_bytes"], int) and job["file_size_bytes"] > 0


def test_created_job_status_is_always_queued(client: TestClient) -> None:
    """Test 9: status is 'queued' immediately after creation (spec AC-5)."""
    pdf = make_minimal_pdf()
    response = client.post(
        "/upload/jobs",
        files=[pdf_file("fy24.pdf", pdf)],
        data={"target_metrics": "Adjusted EBITDA"},
    )
    job = response.json()["created_jobs"][0]
    assert job["status"] == "queued"


def test_target_metric_reflects_per_file_selection(client: TestClient) -> None:
    """Test 10: target_metric on the record matches what was sent, not always the default."""
    pdf = make_minimal_pdf()
    response = client.post(
        "/upload/jobs",
        files=[
            pdf_file("a.pdf", pdf),
            pdf_file("b.pdf", pdf),
        ],
        data={"target_metrics": ["EBITDA", "Net Income"]},
    )
    jobs = response.json()["created_jobs"]
    metrics = {j["filename"]: j["target_metric"] for j in jobs}
    assert metrics["a.pdf"] == "EBITDA"
    assert metrics["b.pdf"] == "Net Income"


def test_invalid_target_metric_returns_422(client: TestClient) -> None:
    """Test 11: Invalid target_metric returns HTTP 422 Unprocessable Entity."""
    pdf = make_minimal_pdf()
    response = client.post(
        "/upload/jobs",
        files=[pdf_file("a.pdf", pdf)],
        data={"target_metrics": "Invalid Metric Name"},
    )
    assert response.status_code == 422
    assert "Invalid target metric" in response.json()["detail"]

