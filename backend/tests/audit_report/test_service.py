"""
Unit and integration tests for Audit Report Service (Feature 8 Step 3).

Enforces:
- spec.md §1, §2, §3, AC-1, AC-10, EC-6, EC-10.
"""

from pathlib import Path
from typing import Any

import fitz  # pymupdf
import pytest
from app.audit_report.compiler import JobNotFoundError, ModelNotCompleteError
from app.audit_report.repository import AuditReportRepository
from app.audit_report.service import generate_audit_report
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


def _make_w3c_record(
    job_id: str,
    sheet_name: str,
    cell_coord: str,
    node_id: str,
    value: str,
    label: str,
) -> W3CAnnotationRecord:
    coords = BoundingBoxCoordinates(x0=100.0, y0=200.0, x1=300.0, y1=250.0)
    selector = W3CSelector(
        page=12,
        value="xywh=percent:100,200,200,50",
        refinedBy=W3CRefinedBy(coordinates=coords),
    )
    target = W3CTarget(source=f"{job_id}.pdf", selector=selector)
    body = W3CBody(value=value, label=label, original_label=label)
    return W3CAnnotationRecord(
        id=f"urn:footnote:provenance:{job_id}:{node_id}",
        job_id=job_id,
        sheet_name=sheet_name,
        cell_coord=cell_coord,
        node_id=node_id,
        is_formula=False,
        body=body,
        target=target,
    )


def test_generate_audit_report_success(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    job_repo = JobRepository(data_dir=data_dir)
    model_repo = ModelRepository(data_dir=data_dir)

    job_rec = job_repo.save_job("E2ETest_2024.pdf", b"%PDF-1.4 dummy", "Adjusted EBITDA")
    job_id = job_rec.job_id

    rec = _make_w3c_record(job_id, "Source_Inputs", "B2", "leaf_0_sbc", "50000", "Stock-Based Compensation")
    model_repo.save_provenance_records(job_id, [rec])

    pdf_path = generate_audit_report(job_id, data_dir=data_dir)

    assert pdf_path.exists()
    assert pdf_path.name == f"{job_id}_audit_report.pdf"
    assert pdf_path.stat().st_size > 0

    # Verify repository can retrieve it
    repo = AuditReportRepository(data_dir=data_dir)
    retrieved_path = repo.get_report_pdf_path(job_id)
    assert retrieved_path == pdf_path

    # Verify PDF content with PyMuPDF
    doc: Any = fitz.open(pdf_path)
    assert doc.page_count >= 1
    assert "E2ETest" in doc[0].get_text()
    doc.close()


def test_generate_audit_report_raises_for_missing_job(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    with pytest.raises(JobNotFoundError, match="Job 'missing-job-id' not found"):
        generate_audit_report("missing-job-id", data_dir=data_dir)


def test_generate_audit_report_raises_for_incomplete_model(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    job_repo = JobRepository(data_dir=data_dir)
    job_rec = job_repo.save_job("Incomplete_2024.pdf", b"%PDF-1.4 dummy", "Adjusted EBITDA")
    job_id = job_rec.job_id

    with pytest.raises(ModelNotCompleteError, match="model generation not complete"):
        generate_audit_report(job_id, data_dir=data_dir)
