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

from app.ingestion.models import (
    ALLOWED_TARGET_METRICS,
    GetJobsResponse,
    JobRecord,
    SubmitResponse,
    ValidationResponse,
)
from app.ingestion.pipeline import process_queued_job
from app.ingestion.repository import JobRepository
from app.ingestion.validation import validate_pdf_bytes

router = APIRouter()


# ── Dependency ────────────────────────────────────────────────────────────────

def get_repository() -> JobRepository:
    """
    Provide the default JobRepository instance.

    Tests override this via app.dependency_overrides[get_repository] to
    point at a tmp_path-backed repository without touching data/.
    """
    return JobRepository()


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
    background_tasks: BackgroundTasks,
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

    created_jobs: list[JobRecord] = []
    rejections = []

    for upload, metric in zip(files, target_metrics):
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
            )
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
