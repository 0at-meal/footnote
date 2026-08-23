"""
FastAPI router for company entity and multi-year management endpoints.

Endpoints:
    POST /companies                       ← Create a company
    GET  /companies                       ← List all companies with associated jobs
    GET  /companies/{company_id}          ← Get a company with its full job list
    POST /companies/{company_id}/jobs/{job_id} ← Assign an existing job to a company
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.ingestion.company_repository import CompanyRepository
from app.ingestion.models import (
    CompanyRecord,
    CompanyWithJobs,
    CreateCompanyRequest,
    JobRecord,
)
from app.ingestion.repository import JobRepository
from app.ingestion.router import get_company_repository, get_repository

router = APIRouter()


@router.post(
    "",
    response_model=CompanyRecord,
    summary="Create a new company",
    description="Creates a company record with a name and optional ticker.",
)
def create_company(
    request: CreateCompanyRequest,
    company_repo: Annotated[CompanyRepository, Depends(get_company_repository)],
) -> CompanyRecord:
    """Create and persist a new company entity."""
    name: str = request.name.strip()
    if not name:
        raise HTTPException(
            status_code=422,
            detail="Company name must not be empty",
        )
    ticker: str | None = request.ticker.strip() if request.ticker is not None else None
    if ticker == "":
        ticker = None
    return company_repo.save_company(name=name, ticker=ticker)


@router.get(
    "",
    response_model=list[CompanyWithJobs],
    summary="List all companies with associated job summaries",
    description="Returns all companies and their associated JobRecords.",
)
def list_companies(
    company_repo: Annotated[CompanyRepository, Depends(get_company_repository)],
    job_repo: Annotated[JobRepository, Depends(get_repository)],
) -> list[CompanyWithJobs]:
    """Return all persisted companies bundled with their associated jobs."""
    companies: list[CompanyRecord] = company_repo.list_companies()
    results: list[CompanyWithJobs] = []
    for c in companies:
        jobs: list[JobRecord] = []
        for j_id in c.job_ids:
            job: JobRecord | None = job_repo.get_job(j_id)
            if job is not None:
                jobs.append(job)
        results.append(
            CompanyWithJobs(
                company_id=c.company_id,
                name=c.name,
                ticker=c.ticker,
                created_at=c.created_at,
                job_ids=c.job_ids,
                jobs=jobs,
            )
        )
    return results


@router.get(
    "/{company_id}",
    response_model=CompanyWithJobs,
    summary="Get a company with full job list",
    description="Returns a specific company and all of its associated JobRecords.",
)
def get_company(
    company_id: str,
    company_repo: Annotated[CompanyRepository, Depends(get_company_repository)],
    job_repo: Annotated[JobRepository, Depends(get_repository)],
) -> CompanyWithJobs:
    """Retrieve a single company by ID with all associated jobs."""
    company: CompanyRecord | None = company_repo.get_company(company_id)
    if company is None:
        raise HTTPException(
            status_code=404,
            detail=f"Company '{company_id}' not found",
        )

    jobs: list[JobRecord] = []
    for j_id in company.job_ids:
        job: JobRecord | None = job_repo.get_job(j_id)
        if job is not None:
            jobs.append(job)

    return CompanyWithJobs(
        company_id=company.company_id,
        name=company.name,
        ticker=company.ticker,
        created_at=company.created_at,
        job_ids=company.job_ids,
        jobs=jobs,
    )


@router.post(
    "/{company_id}/jobs/{job_id}",
    response_model=CompanyRecord,
    summary="Assign a job to a company",
    description="Associates an existing job with a company entity.",
)
def assign_job_to_company(
    company_id: str,
    job_id: str,
    company_repo: Annotated[CompanyRepository, Depends(get_company_repository)],
    job_repo: Annotated[JobRepository, Depends(get_repository)],
) -> CompanyRecord:
    """Link an existing job to a company."""
    company: CompanyRecord | None = company_repo.get_company(company_id)
    if company is None:
        raise HTTPException(
            status_code=404,
            detail=f"Company '{company_id}' not found",
        )

    job: JobRecord | None = job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job '{job_id}' not found",
        )

    updated_company: CompanyRecord | None = company_repo.add_job_to_company(
        company_id, job_id
    )
    if updated_company is None:
        raise HTTPException(
            status_code=404,
            detail=f"Company '{company_id}' not found",
        )

    job_repo.update_job_status(job_id=job_id, status=job.status, company_id=company_id)

    return updated_company
