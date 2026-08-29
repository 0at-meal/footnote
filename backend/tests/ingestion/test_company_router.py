"""
Integration tests for /companies REST endpoints in app.ingestion.company_router.

Uses FastAPI's TestClient with tmp_path dependency injection for both
JobRepository and CompanyRepository.

Tests verify:
- POST /companies (creation, optional ticker, empty name 422)
- GET /companies (empty list, populated list with resolved job records)
- GET /companies/{company_id} (success with jobs, 404 on missing)
- POST /companies/{company_id}/jobs/{job_id} (assignment, idempotency, 404 on missing company or job)
"""

import uuid
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from app.ingestion.company_repository import CompanyRepository
from app.ingestion.repository import JobRepository
from app.ingestion.router import get_company_repository, get_repository
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    """TestClient with both JobRepository and CompanyRepository wired to tmp_path."""
    job_repo = JobRepository(data_dir=tmp_path)
    company_repo = CompanyRepository(data_dir=tmp_path)
    app.dependency_overrides[get_repository] = lambda: job_repo
    app.dependency_overrides[get_company_repository] = lambda: company_repo
    with patch("app.ingestion.router.process_queued_job"):
        yield TestClient(app)
    app.dependency_overrides.clear()


# ── POST /companies ───────────────────────────────────────────────────────────


def test_create_company_success(client: TestClient) -> None:
    """POST /companies creates and returns a valid CompanyRecord."""
    response = client.post(
        "/companies",
        json={"name": "Initech Corporation", "ticker": "INIT"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Initech Corporation"
    assert body["ticker"] == "INIT"
    assert body["job_ids"] == []

    parsed_uuid = uuid.UUID(body["company_id"], version=4)
    assert str(parsed_uuid) == body["company_id"]


def test_create_company_without_ticker(client: TestClient) -> None:
    """POST /companies without ticker sets ticker to None."""
    response = client.post(
        "/companies",
        json={"name": "Massive Dynamic"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Massive Dynamic"
    assert body["ticker"] is None


def test_create_company_empty_name_returns_422(client: TestClient) -> None:
    """POST /companies with empty or whitespace name returns 422."""
    response = client.post(
        "/companies",
        json={"name": "   ", "ticker": "EMP"},
    )
    assert response.status_code == 422
    assert "Company name must not be empty" in response.json()["detail"]


# ── GET /companies ────────────────────────────────────────────────────────────


def test_list_companies_empty(client: TestClient) -> None:
    """GET /companies returns an empty list before any companies exist."""
    response = client.get("/companies")
    assert response.status_code == 200
    assert response.json() == []


def test_list_companies_populated_with_jobs(tmp_path: Path, client: TestClient) -> None:
    """GET /companies returns all companies with resolved job objects."""
    company_repo = CompanyRepository(data_dir=tmp_path)
    job_repo = JobRepository(data_dir=tmp_path)

    company = company_repo.save_company("Wayne Enterprises", ticker="WAYN")
    job = job_repo.save_job(
        "wayne_2023.pdf",
        b"%PDF-1.4 sample",
        "Adjusted EBITDA",
        filing_year=2023,
        company_id=company.company_id,
    )
    company_repo.add_job_to_company(company.company_id, job.job_id)

    response = client.get("/companies")
    assert response.status_code == 200
    companies = response.json()
    assert len(companies) == 1
    assert companies[0]["company_id"] == company.company_id
    assert companies[0]["name"] == "Wayne Enterprises"
    assert len(companies[0]["jobs"]) == 1
    assert companies[0]["jobs"][0]["job_id"] == job.job_id
    assert companies[0]["jobs"][0]["filing_year"] == 2023


# ── GET /companies/{company_id} ───────────────────────────────────────────────


def test_get_company_by_id_success(tmp_path: Path, client: TestClient) -> None:
    """GET /companies/{company_id} returns the company and its resolved jobs."""
    company_repo = CompanyRepository(data_dir=tmp_path)
    job_repo = JobRepository(data_dir=tmp_path)

    company = company_repo.save_company("Stark Industries", ticker="STRK")
    job = job_repo.save_job(
        "stark_2024.pdf",
        b"%PDF-1.4 sample",
        "Free Cash Flow",
        filing_year=2024,
        company_id=company.company_id,
    )
    company_repo.add_job_to_company(company.company_id, job.job_id)

    response = client.get(f"/companies/{company.company_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["company_id"] == company.company_id
    assert data["name"] == "Stark Industries"
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["job_id"] == job.job_id


def test_get_company_by_id_not_found(client: TestClient) -> None:
    """GET /companies/{company_id} returns 404 for nonexistent company."""
    response = client.get("/companies/nonexistent-id")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


# ── POST /companies/{company_id}/jobs/{job_id} ────────────────────────────────


def test_assign_job_to_company_success(tmp_path: Path, client: TestClient) -> None:
    """POST /companies/{company_id}/jobs/{job_id} links an existing job to a company."""
    company_repo = CompanyRepository(data_dir=tmp_path)
    job_repo = JobRepository(data_dir=tmp_path)

    company = company_repo.save_company("Umbrella Corp", ticker="UMB")
    job = job_repo.save_job("umbrella_2023.pdf", b"%PDF-1.4 sample", "Net Income")

    response = client.post(f"/companies/{company.company_id}/jobs/{job.job_id}")
    assert response.status_code == 200
    data = response.json()
    assert job.job_id in data["job_ids"]

    # Verify company repository state
    persisted_company = company_repo.get_company(company.company_id)
    assert persisted_company is not None
    assert job.job_id in persisted_company.job_ids

    # Verify job repository state
    persisted_job = job_repo.get_job(job.job_id)
    assert persisted_job is not None
    assert persisted_job.company_id == company.company_id


def test_assign_job_to_company_missing_company(
    tmp_path: Path, client: TestClient
) -> None:
    """POST /companies/{company_id}/jobs/{job_id} returns 404 if company does not exist."""
    job_repo = JobRepository(data_dir=tmp_path)
    job = job_repo.save_job("job.pdf", b"%PDF-1.4", "EBITDA")

    response = client.post(f"/companies/nonexistent-company-id/jobs/{job.job_id}")
    assert response.status_code == 404
    assert "Company 'nonexistent-company-id' not found" in response.json()["detail"]


def test_assign_job_to_company_missing_job(tmp_path: Path, client: TestClient) -> None:
    """POST /companies/{company_id}/jobs/{job_id} returns 404 if job does not exist."""
    company_repo = CompanyRepository(data_dir=tmp_path)
    company = company_repo.save_company("Acme Corp")

    response = client.post(f"/companies/{company.company_id}/jobs/nonexistent-job-id")
    assert response.status_code == 404
    assert "Job 'nonexistent-job-id' not found" in response.json()["detail"]


def test_assign_job_to_company_idempotent(tmp_path: Path, client: TestClient) -> None:
    """POST /companies/{company_id}/jobs/{job_id} called multiple times does not duplicate."""
    company_repo = CompanyRepository(data_dir=tmp_path)
    job_repo = JobRepository(data_dir=tmp_path)

    company = company_repo.save_company("Cyberdyne Systems")
    job = job_repo.save_job("cyberdyne.pdf", b"%PDF-1.4", "EBITDA")

    r1 = client.post(f"/companies/{company.company_id}/jobs/{job.job_id}")
    assert r1.status_code == 200

    r2 = client.post(f"/companies/{company.company_id}/jobs/{job.job_id}")
    assert r2.status_code == 200
    assert r2.json()["job_ids"] == [job.job_id]


# ── POST /companies/{company_id}/multi-year-model & GET download ──────────────


def test_generate_multi_year_model_success_with_two_jobs(
    tmp_path: Path, client: TestClient
) -> None:
    """POST /companies/{company_id}/multi-year-model compiles 2 jobs into multi-year workbook."""
    from app.extraction.models import ConfidenceBand
    from app.review.models import ReviewItem, ReviewStatus
    from app.review.repository import ReviewRepository

    company_repo = CompanyRepository(data_dir=tmp_path)
    job_repo = JobRepository(data_dir=tmp_path)
    review_repo = ReviewRepository(data_dir=tmp_path)

    company = company_repo.save_company("Stark Industries", ticker="STARK")

    # Job 1 (2022)
    job1 = job_repo.save_job(
        "stark_2022.pdf",
        b"%PDF-1.4",
        "Adjusted EBITDA",
        filing_year=2022,
        company_id=company.company_id,
    )
    company_repo.add_job_to_company(company.company_id, job1.job_id)
    review_repo.save_review_items(
        job1.job_id,
        [
            ReviewItem(
                id="item-2022-1",
                value="250.00",
                label="R&D Amortization",
                page=1,
                bbox={"x0": 0.0, "y0": 0.0, "x1": 100.0, "y1": 100.0},
                source_file="stark_2022.pdf",
                confidence_band=ConfidenceBand.auto_accepted,
                confidence_score=0.95,
                normalized_label="R&D Amortization",
                status=ReviewStatus.auto_accepted,
                is_target_metric_candidate=True,
            )
        ],
    )

    # Job 2 (2023)
    job2 = job_repo.save_job(
        "stark_2023.pdf",
        b"%PDF-1.4",
        "Adjusted EBITDA",
        filing_year=2023,
        company_id=company.company_id,
    )
    company_repo.add_job_to_company(company.company_id, job2.job_id)
    review_repo.save_review_items(
        job2.job_id,
        [
            ReviewItem(
                id="item-2023-1",
                value="300.00",
                label="R&D Amortization",
                page=1,
                bbox={"x0": 0.0, "y0": 0.0, "x1": 100.0, "y1": 100.0},
                source_file="stark_2023.pdf",
                confidence_band=ConfidenceBand.auto_accepted,
                confidence_score=0.95,
                normalized_label="R&D Amortization",
                status=ReviewStatus.auto_accepted,
                is_target_metric_candidate=True,
            )
        ],
    )

    response = client.post(f"/companies/{company.company_id}/multi-year-model")
    assert response.status_code == 200
    data = response.json()
    assert data["company_id"] == company.company_id
    assert (
        data["download_url"]
        == f"/companies/{company.company_id}/multi-year-model/download"
    )
    assert data["years"] == [2022, 2023]
    assert data["total_cells_generated"] > 0

    # Test Download endpoint
    download_res = client.get(data["download_url"])
    assert download_res.status_code == 200
    assert (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        in download_res.headers["content-type"]
    )
    assert len(download_res.content) > 0


def test_generate_multi_year_model_fewer_than_two_jobs_returns_400(
    tmp_path: Path, client: TestClient
) -> None:
    """POST /companies/{company_id}/multi-year-model returns 400 if fewer than 2 jobs exist."""
    company_repo = CompanyRepository(data_dir=tmp_path)
    company = company_repo.save_company("Single Filing LLC")

    response = client.post(f"/companies/{company.company_id}/multi-year-model")
    assert response.status_code == 400
    assert "At least 2 completed jobs" in response.json()["detail"]


def test_generate_multi_year_model_company_not_found_returns_404(
    client: TestClient,
) -> None:
    """POST /companies/{company_id}/multi-year-model returns 404 for missing company."""
    response = client.post("/companies/nonexistent-company/multi-year-model")
    assert response.status_code == 404


def test_download_multi_year_model_not_found_returns_404(
    tmp_path: Path, client: TestClient
) -> None:
    """GET /companies/{company_id}/multi-year-model/download returns 404 if file not yet generated."""
    company_repo = CompanyRepository(data_dir=tmp_path)
    company = company_repo.save_company("Missing Model Corp")

    response = client.get(f"/companies/{company.company_id}/multi-year-model/download")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_generate_full_model_success_and_download(
    tmp_path: Path, client: TestClient
) -> None:
    """POST /companies/{id}/full-model generates 6-tab model and GET /download retrieves it."""
    from app.extraction.models import ConfidenceBand
    from app.review.models import ReviewItem, ReviewStatus
    from app.review.repository import ReviewRepository

    company_repo = CompanyRepository(data_dir=tmp_path)
    job_repo = JobRepository(data_dir=tmp_path)
    review_repo = ReviewRepository(data_dir=tmp_path)

    company = company_repo.save_company("Acme Holdings", ticker="ACME")

    job_2023 = job_repo.save_job(
        "2023.pdf",
        b"%PDF-1.4 mock",
        "Adjusted EBITDA",
        filing_year=2023,
        company_id=company.company_id,
    )
    company_repo.add_job_to_company(company.company_id, job_2023.job_id)

    review_repo.save_review_items(
        job_2023.job_id,
        [
            ReviewItem(
                id=f"{job_2023.job_id}_0",
                value="1,000",
                label="Revenue",
                page=1,
                bbox={"x0": 10.0, "y0": 10.0, "x1": 100.0, "y1": 50.0},
                source_file="2023.pdf",
                confidence_band=ConfidenceBand.auto_accepted,
                confidence_score=0.99,
                normalized_label="Revenue",
                status=ReviewStatus.locked,
            )
        ],
    )

    res = client.post(f"/companies/{company.company_id}/full-model")
    assert res.status_code == 200
    data = res.json()
    assert data["company_id"] == company.company_id
    assert data["total_cells_generated"] > 0
    assert "download_url" in data

    # Test download
    dl_res = client.get(f"/companies/{company.company_id}/full-model/download")
    assert dl_res.status_code == 200
    assert (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        in dl_res.headers["content-type"]
    )
    assert len(dl_res.content) > 0
