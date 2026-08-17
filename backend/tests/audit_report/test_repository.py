"""
Unit tests for AuditReportRepository (Feature 8 Step 2).

Enforces:
- CONSTITUTION §1.1 (mypy --strict), §1.9 (atomic persistence, no swallowed exceptions).
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from app.audit_report.repository import AuditReportRepository


def test_save_report_pdf_creates_file_atomically(tmp_path: Path) -> None:
    repo = AuditReportRepository(data_dir=tmp_path)
    job_id = "job-abc-123"
    pdf_content = b"%PDF-1.4 sample content"

    path = repo.save_report_pdf(job_id, pdf_content)
    assert path.exists()
    assert path.name == f"{job_id}_audit_report.pdf"
    assert path.read_bytes() == pdf_content

    # Ensure no .tmp file remained
    tmp_path_check = tmp_path / "reports" / f"{job_id}_audit_report.pdf.tmp"
    assert not tmp_path_check.exists()


def test_get_report_pdf_path_and_bytes(tmp_path: Path) -> None:
    repo = AuditReportRepository(data_dir=tmp_path)
    job_id = "job-456"

    # Non-existent job
    assert repo.get_report_pdf_path(job_id) is None
    assert repo.get_report_pdf_bytes(job_id) is None

    # Save and retrieve
    pdf_content = b"%PDF-1.4 sample data 456"
    repo.save_report_pdf(job_id, pdf_content)

    retrieved_path = repo.get_report_pdf_path(job_id)
    assert retrieved_path is not None
    assert retrieved_path.exists()

    retrieved_bytes = repo.get_report_pdf_bytes(job_id)
    assert retrieved_bytes == pdf_content


def test_delete_report_pdf(tmp_path: Path) -> None:
    repo = AuditReportRepository(data_dir=tmp_path)
    job_id = "job-789"
    repo.save_report_pdf(job_id, b"%PDF-1.4 to delete")

    assert repo.get_report_pdf_path(job_id) is not None
    deleted = repo.delete_report_pdf(job_id)
    assert deleted is True
    assert repo.get_report_pdf_path(job_id) is None

    # Delete non-existent
    assert repo.delete_report_pdf("non-existent") is False


def test_save_report_pdf_propagates_oserror_cleanly(tmp_path: Path) -> None:
    repo = AuditReportRepository(data_dir=tmp_path)
    job_id = "job-err"

    with (
        patch("os.replace", side_effect=OSError("Disk write error")),
        pytest.raises(OSError, match="Disk write error"),
    ):
        repo.save_report_pdf(job_id, b"%PDF-1.4 crash")

    # Ensure no partial corrupted file was saved as destination
    dest = tmp_path / "reports" / f"{job_id}_audit_report.pdf"
    assert not dest.exists()
