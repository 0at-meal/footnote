"""
Integration tests for Audit Report API Router (Feature 8 Step 4).

Enforces:
- spec.md §4, AC-1, AC-6, EC-6, EC-9, EC-10.
"""

from collections.abc import Generator
from pathlib import Path

import pytest
from app.audit_report.repository import AuditReportRepository
from app.audit_report.router import set_audit_report_repository
from app.excel_export.models import (
    BoundingBoxCoordinates,
    W3CAnnotationRecord,
    W3CBody,
    W3CRefinedBy,
    W3CSelector,
    W3CTarget,
)
from app.excel_export.repository import ModelRepository
from app.ingestion.repository import JobRepository
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    data_dir = tmp_path / "data"
    (data_dir / "uploads").mkdir(parents=True, exist_ok=True)
    (data_dir / "results").mkdir(parents=True, exist_ok=True)
    (data_dir / "models").mkdir(parents=True, exist_ok=True)
    (data_dir / "reports").mkdir(parents=True, exist_ok=True)

    report_repo = AuditReportRepository(data_dir=data_dir)
    set_audit_report_repository(report_repo)

    with TestClient(app) as test_client:
        yield test_client


def _create_mock_completed_job(tmp_path: Path, job_id_prefix: str = "job-route") -> tuple[str, Path]:
    data_dir = tmp_path / "data"
    job_repo = JobRepository(data_dir=data_dir)
    model_repo = ModelRepository(data_dir=data_dir)

    job_rec = job_repo.save_job(f"{job_id_prefix}_2024.pdf", b"%PDF-1.4 dummy", "Adjusted EBITDA")
    job_id = job_rec.job_id

    coords = BoundingBoxCoordinates(x0=100.0, y0=200.0, x1=300.0, y1=250.0)
    selector = W3CSelector(
        page=10,
        value="xywh=percent:100,200,200,50",
        refinedBy=W3CRefinedBy(coordinates=coords),
    )
    target = W3CTarget(source=f"{job_id}.pdf", selector=selector)
    body = W3CBody(value="50000", label="Stock-Based Compensation", original_label="SBC")
    rec = W3CAnnotationRecord(
        id=f"urn:footnote:provenance:{job_id}:leaf_0",
        job_id=job_id,
        sheet_name="Source_Inputs",
        cell_coord="B2",
        node_id="leaf_0_sbc",
        is_formula=False,
        body=body,
        target=target,
    )
    model_repo.save_provenance_records(job_id, [rec])
    return job_id, data_dir


def test_download_audit_report_success_on_the_fly(client: TestClient, tmp_path: Path) -> None:
    job_id, _ = _create_mock_completed_job(tmp_path, "job-fly")

    response = client.get(f"/api/jobs/{job_id}/audit-report")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert f'filename="audit_report_{job_id}.pdf"' in response.headers.get("content-disposition", "")
    assert response.content.startswith(b"%PDF-")


def test_download_audit_report_pre_existing_on_disk(client: TestClient, tmp_path: Path) -> None:
    job_id, data_dir = _create_mock_completed_job(tmp_path, "job-disk")
    repo = AuditReportRepository(data_dir=data_dir)
    dummy_pdf = b"%PDF-1.4 pre-existing content"
    repo.save_report_pdf(job_id, dummy_pdf)

    response = client.get(f"/jobs/{job_id}/audit-report")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == dummy_pdf


def test_download_audit_report_job_not_found_404(client: TestClient) -> None:
    response = client.get("/api/jobs/non-existent-uuid/audit-report")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_download_audit_report_incomplete_model_400(client: TestClient, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    job_repo = JobRepository(data_dir=data_dir)
    job_rec = job_repo.save_job("incomplete_job.pdf", b"%PDF-1.4 dummy", "Adjusted EBITDA")
    job_id = job_rec.job_id

    response = client.get(f"/api/jobs/{job_id}/audit-report")
    assert response.status_code == 400
    assert "model generation not complete" in response.json()["detail"].lower()


def test_get_audit_report_status(client: TestClient, tmp_path: Path) -> None:
    job_id, data_dir = _create_mock_completed_job(tmp_path, "job-stat")

    # Initial status: not yet generated
    res1 = client.get(f"/api/jobs/{job_id}/audit-report/status")
    assert res1.status_code == 200
    assert res1.json()["is_ready"] is False

    # Save report
    repo = AuditReportRepository(data_dir=data_dir)
    repo.save_report_pdf(job_id, b"%PDF-1.4 dummy")

    res2 = client.get(f"/api/jobs/{job_id}/audit-report/status")
    assert res2.status_code == 200
    assert res2.json()["is_ready"] is True
    assert res2.json()["download_url"] == f"/api/jobs/{job_id}/audit-report"
