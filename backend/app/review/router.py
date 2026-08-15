"""
FastAPI router for extraction review endpoints (Feature 5).

Endpoints:
    GET /review/{job_id}/pdf   ← Stream source PDF binary for PDF.js rendering
    GET /review/{job_id}/items ← Retrieve all extracted items with review status
"""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.ingestion.repository import JobRepository
from app.review.models import ReviewItemsResponse
from app.review.repository import ReviewRepository

router = APIRouter(prefix="/review", tags=["review"])

_job_repo = JobRepository()
_review_repo = ReviewRepository()


@router.get(
    "/{job_id}/pdf",
    response_class=FileResponse,
    summary="Stream source PDF for a job",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Raw PDF binary stream.",
        },
        404: {"description": "Job not found or source PDF unavailable."},
    },
)
def get_job_pdf(job_id: str) -> FileResponse:
    """
    Stream the source PDF binary for job_id to the frontend.

    Handles EC-7 by returning a clear 404 error if the physical PDF file
    is missing on disk.
    """
    job = _job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    pdf_path = _job_repo.get_pdf_path(job_id)
    if not pdf_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source PDF unavailable",
        )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=job.filename,
    )


@router.get(
    "/{job_id}/items",
    response_model=ReviewItemsResponse,
    summary="Retrieve extracted items for review",
    responses={
        200: {"description": "List of all extracted items with review metadata."},
        404: {"description": "Job not found or extraction results not yet generated."},
    },
)
def get_review_items(job_id: str) -> ReviewItemsResponse:
    """
    Retrieve all extraction records for a job formatted for the review UI.

    Reachable across all confidence bands and statuses (spec AC-1).
    """
    job = _job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    items = _review_repo.get_review_items(job_id)
    if items is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No extraction records found for job",
        )

    return ReviewItemsResponse(
        job_id=job_id,
        items=items,
        total_items=len(items),
    )
