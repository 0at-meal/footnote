"""
FastAPI router for compliance audit report download and status (Feature 8 Step 4).

Exposes:
- GET /api/jobs/{job_id}/audit-report (spec §4, AC-6)
- GET /jobs/{job_id}/audit-report
- GET /api/jobs/{job_id}/audit-report/status
- GET /jobs/{job_id}/audit-report/status

Enforces:
- CONSTITUTION §1.1 (mypy --strict), §1.9 (no swallowed exceptions).
- spec.md AC-6: Content-Type: application/pdf, Content-Disposition: attachment; filename="audit_report_{job_id}.pdf".
- spec.md EC-6: HTTP 400 on incomplete model.
- spec.md EC-9: Safe concurrent serving.
- spec.md EC-10: Descriptive HTTP 500 on filesystem error.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.audit_report.compiler import JobNotFoundError, ModelNotCompleteError
from app.audit_report.repository import AuditReportRepository
from app.audit_report.service import generate_audit_report

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audit-report"])
_report_repo = AuditReportRepository()


def get_audit_report_repository() -> AuditReportRepository:
    """Returns the active AuditReportRepository instance."""
    return _report_repo


def set_audit_report_repository(repo: AuditReportRepository) -> None:
    """Sets the active AuditReportRepository instance (used for testing / dependency injection)."""
    global _report_repo
    _report_repo = repo


class ReportStatusResponse(BaseModel):
    """Status metadata for an audit report (spec §4)."""

    job_id: str = Field(..., description="Job identifier")
    is_ready: bool = Field(..., description="True if report is generated and ready on disk")
    download_url: str = Field(..., description="API download endpoint path")
    error_detail: str | None = Field(default=None, description="Diagnostic error if unavailable")


@router.get(
    "/api/jobs/{job_id}/audit-report",
    response_class=FileResponse,
    summary="Download compliance audit report PDF",
)
@router.get(
    "/jobs/{job_id}/audit-report",
    response_class=FileResponse,
    include_in_schema=False,
)
def download_audit_report(job_id: str) -> FileResponse:
    """
    Serves the compliance audit report PDF as a downloadable binary attachment (spec §4, AC-6).
    If the report has not yet been rendered to disk, generates it on the fly.
    """
    repo = get_audit_report_repository()
    pdf_path = repo.get_report_pdf_path(job_id)

    if pdf_path is None or not pdf_path.exists():
        data_dir: Path = repo.reports_dir.parent
        try:
            pdf_path = generate_audit_report(job_id, data_dir=data_dir)
        except JobNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job '{job_id}' not found.",
            ) from None
        except ModelNotCompleteError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(err),
            ) from None
        except (OSError, ValueError, RuntimeError) as err:
            logger.error("Failed to generate audit report for job %s: %s", job_id, err)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate audit report: {err}",
            ) from None

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"audit_report_{job_id}.pdf",
        headers={"Content-Disposition": f'attachment; filename="audit_report_{job_id}.pdf"'},
    )


@router.get(
    "/api/jobs/{job_id}/audit-report/status",
    response_model=ReportStatusResponse,
    summary="Check audit report download status",
)
@router.get(
    "/jobs/{job_id}/audit-report/status",
    response_model=ReportStatusResponse,
    include_in_schema=False,
)
def get_audit_report_status(job_id: str) -> ReportStatusResponse:
    """
    Returns metadata indicating whether the compliance audit report is available for download.
    """
    repo = get_audit_report_repository()
    pdf_path = repo.get_report_pdf_path(job_id)
    is_ready = pdf_path is not None and pdf_path.exists()

    return ReportStatusResponse(
        job_id=job_id,
        is_ready=is_ready,
        download_url=f"/api/jobs/{job_id}/audit-report",
        error_detail=None if is_ready else "Report not yet generated or model incomplete",
    )
