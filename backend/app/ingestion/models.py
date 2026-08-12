from enum import Enum

from pydantic import BaseModel

ALLOWED_TARGET_METRICS: tuple[str, ...] = (
    "Adjusted EBITDA",
    "EBITDA",
    "Net Income",
    "Free Cash Flow",
)



class FileValidationResult(BaseModel):
    """Result of server-side validation for a single uploaded file."""

    filename: str
    accepted: bool
    error_message: str | None = None


class ValidationResponse(BaseModel):
    """Per-file validation results for a multi-file upload request."""

    results: list[FileValidationResult]


class JobStatus(str, Enum):
    """Lifecycle states for a job record (CONSTITUTION §2.3 — frozen values)."""

    queued = "queued"
    extracting = "extracting"
    done = "done"
    failed = "failed"


class JobRecord(BaseModel):
    """A persisted job record created for each accepted file upload."""

    job_id: str
    """UUIDv4 — system-generated, never derived from the filename."""
    filename: str
    """Original filename as supplied by the uploader (UTF-8, stored as-is — EC-8)."""
    file_size_bytes: int
    """Exact byte count of the uploaded file."""
    status: JobStatus
    """Always 'queued' at creation; transitions are Feature 1 Step 5's responsibility."""
    target_metric: str
    """User-selected target metric recorded before queuing (spec AC-6)."""
    submitted_at: str
    """ISO 8601 UTC timestamp of job creation, e.g. '2026-08-12T01:00:00Z'."""


class SubmitResponse(BaseModel):
    """Response for POST /upload/jobs: split between created records and rejections."""

    created_jobs: list[JobRecord]
    rejections: list[FileValidationResult]


class GetJobsResponse(BaseModel):
    """Response for GET /upload/jobs: all persisted job records."""

    jobs: list[JobRecord]
