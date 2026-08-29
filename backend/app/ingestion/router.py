"""
FastAPI router for ingestion upload endpoints.

Endpoints:
    POST /upload/validate  ← Step 2 (unchanged): validate only, no persistence.
    POST /upload/jobs      ← Step 3: validate → persist → return JobRecords.
    GET  /upload/jobs      ← Step 3: return all persisted JobRecords.

The JobRepository is injected via FastAPI's Depends() mechanism so tests can
substitute a tmp_path-backed repository without touching the real data/ dir.
"""

from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)

from app.ingestion.company_repository import CompanyRepository
from app.ingestion.edgar_client import (
    EdgarClientError,
    EdgarCompanyNotFoundError,
    EdgarFetchError,
    EdgarFilingNotFoundError,
    fetch_filing_pdf,
    get_filings,
    search_company,
)
from app.ingestion.models import (
    ALLOWED_TARGET_METRICS,
    EdgarCompanyResult,
    EdgarFiling,
    EdgarSubmitRequest,
    GetJobsResponse,
    JobRecord,
    SubmitResponse,
    ValidationResponse,
)
from app.ingestion.repository import JobRepository
from app.ingestion.validation import validate_pdf_bytes
from app.job_runner import process_queued_job

router = APIRouter()


# ── Dependencies ──────────────────────────────────────────────────────────────


def get_repository() -> JobRepository:
    """
    Provide the default JobRepository instance.

    Tests override this via app.dependency_overrides[get_repository] to
    point at a tmp_path-backed repository without touching data/.
    """
    return JobRepository()


def get_company_repository() -> CompanyRepository:
    """
    Provide the default CompanyRepository instance.

    Tests override this via app.dependency_overrides[get_company_repository] to
    point at a tmp_path-backed repository without touching data/.
    """
    return CompanyRepository()


# ── POST /upload/validate (Step 2 — unchanged) ────────────────────────────────


@router.post(
    "/validate",
    response_model=ValidationResponse,
    summary="Validate uploaded PDF files",
    description=(
        "Accepts one or more files via multipart upload, runs server-side "
        "validation (type, size, structural integrity, password protection), "
        "and returns a per-file acceptance or rejection result. "
        "No job records are created at this stage (Feature 1, Step 3)."
    ),
)
async def validate_uploads(
    files: Annotated[
        list[UploadFile],
        File(description="One or more PDF files to validate"),
    ],
) -> ValidationResponse:
    """
    Validate one or more uploaded files.

    Each file is validated independently: a rejection of one file does
    not affect the result for any other file in the same request
    (spec AC-2, EC-7). The response is always HTTP 200; per-file
    rejection is communicated in the response body, not via HTTP status.
    """
    results = []
    for upload in files:
        content: bytes = await upload.read()
        filename: str = upload.filename or "<unknown>"
        result = validate_pdf_bytes(filename, content)
        results.append(result)
    return ValidationResponse(results=results)


# ── POST /upload/jobs (Step 3) ────────────────────────────────────────────────


@router.post(
    "/jobs",
    response_model=SubmitResponse,
    summary="Submit PDF files for processing",
    description=(
        "Validates each file, persists accepted files to disk, and creates a "
        "JobRecord for each accepted file. Rejected files are returned in the "
        "'rejections' list. The response is always HTTP 200 when the request "
        "itself is well-formed; per-file rejection is in the body, not HTTP status."
    ),
)
async def submit_jobs(
    files: Annotated[
        list[UploadFile],
        File(description="One or more PDF files to submit"),
    ],
    target_metrics: Annotated[
        list[str],
        Form(description="Target metric per file, parallel-indexed to files[]"),
    ],
    repo: Annotated[JobRepository, Depends(get_repository)],
    company_repo: Annotated[CompanyRepository, Depends(get_company_repository)],
    background_tasks: BackgroundTasks,
    filing_years: Annotated[
        list[str] | None,
        Form(description="Optional fiscal year per file, parallel-indexed to files[]"),
    ] = None,
    company_name: Annotated[
        str | None,
        Form(description="Optional company name to assign uploaded filings to"),
    ] = None,
) -> SubmitResponse:
    """
    Submit one or more PDF files for processing.

    The request must include an equal number of 'files' and 'target_metrics'
    fields (422 if they differ). Each file is validated independently:
    accepted files are persisted and a JobRecord is created; rejected files
    are returned in 'rejections' without affecting the other files (EC-7).

    File bytes are written atomically before the record is appended to
    jobs.json. Any write failure propagates as a 500 — no partial job
    record is silently left behind (spec AC-9, CONSTITUTION §1.9).
    """
    if len(files) != len(target_metrics):
        raise HTTPException(
            status_code=422,
            detail=(
                f"'files' and 'target_metrics' must have the same length "
                f"(got {len(files)} files and {len(target_metrics)} metrics)"
            ),
        )

    for metric in target_metrics:
        if metric not in ALLOWED_TARGET_METRICS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Invalid target metric '{metric}'. "
                    f"Allowed metrics: {', '.join(ALLOWED_TARGET_METRICS)}"
                ),
            )

    parsed_years: list[int | None] = []
    if filing_years is not None and len(filing_years) > 0:
        if len(filing_years) != len(files):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"'files' and 'filing_years' must have the same length "
                    f"(got {len(files)} files and {len(filing_years)} filing_years)"
                ),
            )
        for yr_str in filing_years:
            if (
                yr_str is None
                or yr_str.strip() == ""
                or yr_str.strip().lower() in ("null", "none")
            ):
                parsed_years.append(None)
            else:
                try:
                    parsed_years.append(int(yr_str.strip()))
                except ValueError:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Invalid filing year '{yr_str}'. Must be an integer or omitted.",
                    )
    else:
        parsed_years = [None] * len(files)

    company_id: str | None = None
    if company_name is not None and company_name.strip():
        cleaned_company_name = company_name.strip()
        company = company_repo.get_company_by_name(cleaned_company_name)
        if company is None:
            company = company_repo.save_company(name=cleaned_company_name)
        company_id = company.company_id

    created_jobs: list[JobRecord] = []
    rejections = []

    for upload, metric, year in zip(files, target_metrics, parsed_years):
        content: bytes = await upload.read()
        filename: str = upload.filename or "<unknown>"
        result = validate_pdf_bytes(filename, content)

        if not result.accepted:
            rejections.append(result)
        else:
            job = repo.save_job(
                filename=filename,
                content=content,
                target_metric=metric,
                filing_year=year,
                company_id=company_id,
            )
            if company_id is not None:
                company_repo.add_job_to_company(company_id, job.job_id)
            created_jobs.append(job)
            background_tasks.add_task(process_queued_job, job.job_id, repo)

    return SubmitResponse(created_jobs=created_jobs, rejections=rejections)


# ── GET /upload/jobs (Step 3) ─────────────────────────────────────────────────


@router.get(
    "/jobs",
    response_model=GetJobsResponse,
    summary="List all persisted job records",
    description=(
        "Returns all JobRecords persisted to data/jobs.json. "
        "Returns an empty list if no jobs have been submitted yet. "
        "Used by the frontend on page load to restore state (spec AC-7)."
    ),
)
def list_jobs(
    repo: Annotated[JobRepository, Depends(get_repository)],
) -> GetJobsResponse:
    """Return all persisted JobRecords (spec AC-7: survive page refresh)."""
    return GetJobsResponse(jobs=repo.list_jobs())


# ── SEC EDGAR Direct Integration Endpoints (Step D) ──────────────────────────


@router.get(
    "/edgar/search",
    response_model=list[EdgarCompanyResult],
    summary="Search companies on SEC EDGAR",
)
def search_edgar_companies(q: str) -> list[EdgarCompanyResult]:
    """
    Search companies by ticker, name, or CIK on SEC EDGAR (Ticket D-1).
    """
    return search_company(query=q)


@router.get(
    "/edgar/filings/{cik}",
    response_model=list[EdgarFiling],
    summary="List SEC filings for a company CIK",
)
def list_edgar_filings(
    cik: str,
    form_type: str | None = None,
    limit: int = 10,
) -> list[EdgarFiling]:
    """
    Retrieve SEC 10-K and 10-Q filing history for a CIK (Ticket D-2).
    """
    try:
        return get_filings(cik=cik, form_type=form_type, limit=limit)
    except EdgarCompanyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except EdgarClientError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post(
    "/edgar",
    response_model=JobRecord,
    summary="Directly ingest a SEC EDGAR filing",
)
async def submit_edgar_filing(
    payload: EdgarSubmitRequest,
    background_tasks: BackgroundTasks,
    repo: Annotated[JobRepository, Depends(get_repository)],
    company_repo: Annotated[CompanyRepository, Depends(get_company_repository)],
) -> JobRecord:
    """
    Download SEC filing PDF directly from EDGAR, persist job, and enqueue extraction pipeline (Ticket D-4).
    """
    if payload.target_metric not in ALLOWED_TARGET_METRICS:
        raise HTTPException(
            status_code=422,
            detail=f"Target metric '{payload.target_metric}' is not in allowed metrics {ALLOWED_TARGET_METRICS}",
        )

    try:
        pdf_bytes = fetch_filing_pdf(
            accession_number=payload.accession_number,
            cik=payload.cik,
            primary_document=payload.primary_document,
        )
    except EdgarFilingNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except EdgarFetchError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except EdgarClientError as e:
        raise HTTPException(status_code=502, detail=str(e))

    company_id: str | None = None
    if payload.company_name and payload.company_name.strip():
        cleaned_company_name = payload.company_name.strip()
        company = company_repo.get_company_by_name(cleaned_company_name)
        if company is None:
            company = company_repo.save_company(name=cleaned_company_name)
        company_id = company.company_id

    filename = (
        payload.primary_document
        if payload.primary_document and payload.primary_document.endswith(".pdf")
        else f"{payload.accession_number}.pdf"
    )

    job = repo.save_job(
        filename=filename,
        content=pdf_bytes,
        target_metric=payload.target_metric,
        filing_year=payload.filing_year,
        company_id=company_id,
    )
    if company_id is not None:
        company_repo.add_job_to_company(company_id, job.job_id)

    background_tasks.add_task(process_queued_job, job.job_id, repo)
    return job
