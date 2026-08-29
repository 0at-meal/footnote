"""
FastAPI router for Footnote Extraction endpoints (Feature 8, Step E).

Endpoints:
    GET  /footnote/{job_id}/debt         ← Retrieve parsed debt schedule
    POST /footnote/{job_id}/debt/confirm ← Save analyst-confirmed debt schedule
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.footnote.models import DebtSchedule, DebtScheduleConfirmRequest
from app.footnote.repository import DebtScheduleRepository
from app.ingestion.repository import JobRepository

router = APIRouter(prefix="/footnote", tags=["footnote"])

_default_job_repo = JobRepository()
_default_schedule_repo = DebtScheduleRepository()


def get_job_repository() -> JobRepository:
    return _default_job_repo


def get_debt_repository() -> DebtScheduleRepository:
    return _default_schedule_repo


@router.get(
    "/{job_id}/debt",
    response_model=DebtSchedule,
    summary="Retrieve extracted debt schedule for a job",
    responses={
        200: {"description": "Extracted debt schedule and tranches."},
        404: {"description": "Job or extraction records not found."},
    },
)
def get_debt_schedule(
    job_id: str,
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
    debt_repo: Annotated[DebtScheduleRepository, Depends(get_debt_repository)],
) -> DebtSchedule:
    """
    Retrieve or compile the Debt Schedule (Note 8) for a filing.
    """
    job = job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )

    schedule = debt_repo.get_debt_schedule(job_id)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No debt footnote extracted for job '{job_id}'",
        )

    return schedule


@router.post(
    "/{job_id}/debt/confirm",
    response_model=DebtSchedule,
    summary="Confirm and update debt schedule tranches",
    responses={
        200: {"description": "Debt schedule confirmed and saved."},
        404: {"description": "Job not found."},
    },
)
def confirm_debt_schedule(
    job_id: str,
    payload: DebtScheduleConfirmRequest,
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
    debt_repo: Annotated[DebtScheduleRepository, Depends(get_debt_repository)],
) -> DebtSchedule:
    """
    Save confirmed debt tranches and recalculate totals and weighted average rates.
    """
    job = job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )

    updated = debt_repo.confirm_debt_schedule(
        job_id=job_id,
        tranches=payload.tranches,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not confirm debt schedule for job '{job_id}'",
        )

    return updated
