"""
FastAPI router for Footnote Extraction endpoints (Feature 8, Step E).

Endpoints:
    GET  /footnote/{job_id}/debt         ← Retrieve parsed debt schedule
    POST /footnote/{job_id}/debt/confirm ← Save analyst-confirmed debt schedule
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.footnote.models import (
    ConcentrationConfirmRequest,
    ConcentrationSummary,
    DebtSchedule,
    DebtScheduleConfirmRequest,
    LeaseSchedule,
    LeaseScheduleConfirmRequest,
)
from app.footnote.repository import (
    ConcentrationRepository,
    DebtScheduleRepository,
    LeaseScheduleRepository,
)
from app.ingestion.repository import JobRepository

router = APIRouter(prefix="/footnote", tags=["footnote"])

_default_job_repo = JobRepository()
_default_schedule_repo = DebtScheduleRepository()
_default_lease_repo = LeaseScheduleRepository()
_default_concentration_repo = ConcentrationRepository()


def get_job_repository() -> JobRepository:
    return _default_job_repo


def get_debt_repository() -> DebtScheduleRepository:
    return _default_schedule_repo


def get_lease_repository() -> LeaseScheduleRepository:
    return _default_lease_repo


def get_concentration_repository() -> ConcentrationRepository:
    return _default_concentration_repo


@router.get(
    "/{job_id}/available",
    response_model=list[str],
    summary="Get list of available footnote categories extracted for a job",
)
def get_available_footnotes(
    job_id: str,
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
    debt_repo: Annotated[DebtScheduleRepository, Depends(get_debt_repository)],
    lease_repo: Annotated[LeaseScheduleRepository, Depends(get_lease_repository)],
    conc_repo: Annotated[
        ConcentrationRepository, Depends(get_concentration_repository)
    ],
) -> list[str]:
    job = job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )

    available: list[str] = []
    if debt_repo.get_debt_schedule(job_id) is not None:
        available.append("debt_schedule")
    if lease_repo.get_lease_schedule(job_id) is not None:
        available.append("lease_schedule")
    conc = conc_repo.get_concentration(job_id)
    if conc is not None and (conc.customers or conc.suppliers):
        available.append("customer_concentration")
    return available


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


@router.get(
    "/{job_id}/lease",
    response_model=LeaseSchedule,
    summary="Retrieve extracted ASC 842 lease schedule for a job",
    responses={
        200: {"description": "Extracted lease schedule and commitment waterfall."},
        404: {"description": "Job or lease records not found."},
    },
)
def get_lease_schedule(
    job_id: str,
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
    lease_repo: Annotated[LeaseScheduleRepository, Depends(get_lease_repository)],
) -> LeaseSchedule:
    """
    Retrieve or compile the Lease Schedule (Note 12 / ASC 842) for a filing.
    """
    job = job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )

    schedule = lease_repo.get_lease_schedule(job_id)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No lease footnote extracted for job '{job_id}'",
        )

    return schedule


@router.post(
    "/{job_id}/lease/confirm",
    response_model=LeaseSchedule,
    summary="Confirm and update lease schedule waterfall",
    responses={
        200: {"description": "Lease schedule confirmed and saved."},
        404: {"description": "Job not found."},
    },
)
def confirm_lease_schedule(
    job_id: str,
    payload: LeaseScheduleConfirmRequest,
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
    lease_repo: Annotated[LeaseScheduleRepository, Depends(get_lease_repository)],
) -> LeaseSchedule:
    """
    Save confirmed lease commitment waterfall and discount rates.
    """
    job = job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )

    updated = lease_repo.confirm_lease_schedule(
        job_id=job_id,
        years=payload.years,
        operating_discount_rate=payload.operating_discount_rate,
        finance_discount_rate=payload.finance_discount_rate,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not confirm lease schedule for job '{job_id}'",
        )

    return updated


@router.get(
    "/{job_id}/concentration",
    response_model=ConcentrationSummary,
    summary="Retrieve customer and supplier concentration disclosures (ASC 280)",
    responses={
        200: {"description": "Customer and supplier concentration summary."},
        404: {"description": "Job not found."},
    },
)
def get_concentration(
    job_id: str,
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
    conc_repo: Annotated[
        ConcentrationRepository, Depends(get_concentration_repository)
    ],
) -> ConcentrationSummary:
    job = job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )

    summary = conc_repo.get_concentration(job_id)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No concentration data extracted for job '{job_id}'",
        )

    return summary


@router.post(
    "/{job_id}/concentration/confirm",
    response_model=ConcentrationSummary,
    summary="Confirm and update customer and supplier concentration disclosures",
    responses={
        200: {"description": "Concentration summary confirmed and saved."},
        404: {"description": "Job not found."},
    },
)
def confirm_concentration(
    job_id: str,
    payload: ConcentrationConfirmRequest,
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
    conc_repo: Annotated[
        ConcentrationRepository, Depends(get_concentration_repository)
    ],
) -> ConcentrationSummary:
    job = job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )

    updated = conc_repo.confirm_concentration(
        job_id=job_id,
        customers=payload.customers,
        suppliers=payload.suppliers,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not confirm concentration for job '{job_id}'",
        )

    return updated
