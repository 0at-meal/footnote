"""
FastAPI router for company entity and multi-year management endpoints.

Endpoints:
    POST /companies                       ← Create a company
    GET  /companies                       ← List all companies with associated jobs
    GET  /companies/{company_id}          ← Get a company with its full job list
    POST /companies/{company_id}/jobs/{job_id} ← Assign an existing job to a company
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.classification.repository import ClassificationRepository
from app.excel_export.multi_year_generator import generate_multi_year_workbook
from app.formula_engine.models import FormulaTree
from app.formula_engine.reader import (
    read_formula_inputs,
    read_formula_inputs_from_review,
)
from app.formula_engine.tree import build_formula_tree
from app.ingestion.company_repository import CompanyRepository
from app.ingestion.models import (
    CompanyRecord,
    CompanyWithJobs,
    CreateCompanyRequest,
    JobRecord,
    MultiYearModelResponse,
)
from app.ingestion.repository import JobRepository
from app.ingestion.router import get_company_repository, get_repository
from app.review.repository import ReviewRepository

router = APIRouter()


def get_review_repository(
    company_repo: Annotated[CompanyRepository, Depends(get_company_repository)],
) -> ReviewRepository:
    """Returns a ReviewRepository using the active company data directory."""
    return ReviewRepository(data_dir=company_repo.data_dir)


def get_classification_repository(
    company_repo: Annotated[CompanyRepository, Depends(get_company_repository)],
) -> ClassificationRepository:
    """Returns a ClassificationRepository using the active company data directory."""
    return ClassificationRepository(data_dir=company_repo.data_dir)


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


@router.post(
    "/{company_id}/multi-year-model",
    response_model=MultiYearModelResponse,
    summary="Generate multi-year Excel model for a company",
    description="Builds formula trees for all completed jobs of the company and generates a multi-year model workbook.",
)
def generate_company_multi_year_model(
    company_id: str,
    company_repo: Annotated[CompanyRepository, Depends(get_company_repository)],
    job_repo: Annotated[JobRepository, Depends(get_repository)],
    review_repo: Annotated[ReviewRepository, Depends(get_review_repository)],
    classification_repo: Annotated[
        ClassificationRepository, Depends(get_classification_repository)
    ],
) -> MultiYearModelResponse:
    """Orchestrate compilation and export of a multi-year Excel model workbook."""
    company: CompanyRecord | None = company_repo.get_company(company_id)
    if company is None:
        raise HTTPException(
            status_code=404,
            detail=f"Company '{company_id}' not found",
        )

    valid_jobs: list[tuple[JobRecord, FormulaTree]] = []
    for j_id in company.job_ids:
        job: JobRecord | None = job_repo.get_job(j_id)
        if job is None:
            continue

        target_metric = job.target_metric or "Adjusted EBITDA"
        review_items = review_repo.get_review_items(j_id)
        if review_items is not None and len(review_items) > 0:
            batch = read_formula_inputs_from_review(review_items)
        else:
            classified_records = classification_repo.get_classified_records(j_id)
            if classified_records is not None and len(classified_records) > 0:
                batch = read_formula_inputs(classified_records)
            else:
                continue

        if batch.nodes and len(batch.nodes) > 0:
            tree = build_formula_tree(batch, target_metric=target_metric)
            if tree.is_valid:
                valid_jobs.append((job, tree))

    if len(valid_jobs) < 2:
        raise HTTPException(
            status_code=400,
            detail="At least 2 completed jobs with confirmed line items are required to generate a multi-year model.",
        )

    result = generate_multi_year_workbook(
        company=company,
        jobs=valid_jobs,
        output_dir=company_repo.data_dir,
    )
    if not result.is_success:
        raise HTTPException(
            status_code=400,
            detail=result.error_detail or "Failed to generate multi-year workbook.",
        )

    sorted_pairs = sorted(
        valid_jobs,
        key=lambda pair: (
            pair[0].filing_year if pair[0].filing_year is not None else 0,
            pair[0].submitted_at,
        ),
    )
    years: list[int] = [
        pair[0].filing_year for pair in sorted_pairs if pair[0].filing_year is not None
    ]

    return MultiYearModelResponse(
        company_id=company_id,
        download_url=f"/companies/{company_id}/multi-year-model/download",
        years=years,
        total_cells_generated=result.total_cells_generated,
        file_path=result.file_path,
    )


@router.get(
    "/{company_id}/multi-year-model/download",
    response_class=FileResponse,
    summary="Download generated multi-year Excel model",
)
def download_company_multi_year_model(
    company_id: str,
    company_repo: Annotated[CompanyRepository, Depends(get_company_repository)],
) -> FileResponse:
    """Download the generated multi-year .xlsx workbook."""
    company: CompanyRecord | None = company_repo.get_company(company_id)
    if company is None:
        raise HTTPException(
            status_code=404,
            detail=f"Company '{company_id}' not found",
        )

    file_path: Path = company_repo.data_dir / "models" / f"{company_id}_multi_year.xlsx"
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Multi-year model for company '{company_id}' not found. Generate it first.",
        )

    return FileResponse(
        path=str(file_path),
        filename=f"{company_id}_multi_year.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
