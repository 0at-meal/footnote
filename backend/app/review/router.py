"""
FastAPI router for extraction review endpoints (Feature 5).

Endpoints:
    GET /review/{job_id}/pdf   ← Stream source PDF binary for PDF.js rendering
    GET /review/{job_id}/items ← Retrieve all extracted items with review status
"""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.ingestion.repository import JobRepository
from app.review.models import (
    ReviewBatchConfirmRequest,
    ReviewBatchConfirmResponse,
    ReviewItem,
    ReviewItemConfirmRequest,
    ReviewItemEditRequest,
    ReviewItemsResponse,
)
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


@router.patch(
    "/{job_id}/items/{item_id}/edit",
    response_model=ReviewItem,
    summary="Edit an item's value or label",
    responses={
        200: {"description": "Item successfully updated."},
        400: {"description": "Validation error or invalid item state."},
        404: {"description": "Job or item not found."},
    },
)
def edit_review_item(
    job_id: str,
    item_id: str,
    payload: ReviewItemEditRequest,
) -> ReviewItem:
    """
    Edit value or label for an item (spec AC-4, AC-8, AC-9).
    """
    job = _job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    item, err = _review_repo.update_item(
        job_id=job_id,
        item_id=item_id,
        value=payload.value,
        label=payload.label,
    )
    if err is not None:
        if "not found" in err.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    return item


@router.post(
    "/{job_id}/items/{item_id}/confirm",
    response_model=ReviewItem,
    summary="Confirm an item and transition to locked state",
    responses={
        200: {"description": "Item confirmed and locked."},
        400: {"description": "Cannot confirm (e.g. extraction error or taxonomy rejection)."},
        404: {"description": "Job or item not found."},
    },
)
def confirm_review_item(
    job_id: str,
    item_id: str,
    payload: ReviewItemConfirmRequest,
) -> ReviewItem:
    """
    Confirm an item, locking it against automated overwrites (spec AC-4, AC-5, EC-1, EC-5).
    """
    job = _job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    item, err = _review_repo.confirm_item(
        job_id=job_id,
        item_id=item_id,
        add_to_taxonomy=payload.add_to_taxonomy,
    )
    if err is not None:
        if "not found" in err.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    return item


@router.post(
    "/{job_id}/items/{item_id}/flag",
    response_model=ReviewItem,
    summary="Flag an item for attention or toggle flag",
    responses={
        200: {"description": "Item flag state updated."},
        400: {"description": "Cannot flag a locked item."},
        404: {"description": "Job or item not found."},
    },
)
def flag_review_item(
    job_id: str,
    item_id: str,
) -> ReviewItem:
    """
    Flag an item or toggle its flagged state (spec AC-4, AC-7, EC-8).
    """
    job = _job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    item, err = _review_repo.flag_item(
        job_id=job_id,
        item_id=item_id,
    )
    if err is not None:
        if "not found" in err.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    return item


@router.post(
    "/{job_id}/items/{item_id}/unlock",
    response_model=ReviewItem,
    summary="Unlock a confirmed/locked item",
    responses={
        200: {"description": "Item unlocked and modifiable."},
        400: {"description": "Item is not currently locked."},
        404: {"description": "Job or item not found."},
    },
)
def unlock_review_item(
    job_id: str,
    item_id: str,
) -> ReviewItem:
    """
    Explicitly unlock a locked item (spec AC-6).
    """
    job = _job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    item, err = _review_repo.unlock_item(
        job_id=job_id,
        item_id=item_id,
    )
    if err is not None:
        if "not found" in err.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)

    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

    return item


@router.post(
    "/{job_id}/confirm-batch",
    response_model=ReviewBatchConfirmResponse,
    summary="Batch confirm and lock items for a job",
    responses={
        200: {"description": "Items successfully batch confirmed and locked."},
        400: {"description": "Batch confirmation failed."},
        404: {"description": "Job not found."},
    },
)
def confirm_batch_review_items(
    job_id: str,
    payload: ReviewBatchConfirmRequest,
) -> ReviewBatchConfirmResponse:
    """
    Batch confirm and lock target candidate items for a job (Ticket 4.1).
    """
    job = _job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    items, locked_ids, err = _review_repo.confirm_batch(
        job_id=job_id,
        target_candidates_only=payload.target_candidates_only,
        item_ids=payload.item_ids,
        auto_add_pending_taxonomy=payload.auto_add_pending_taxonomy,
    )
    if err is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err,
        )

    return ReviewBatchConfirmResponse(
        job_id=job_id,
        total_locked=len(locked_ids),
        locked_item_ids=locked_ids,
        items=items,
    )

