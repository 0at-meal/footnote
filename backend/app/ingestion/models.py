from enum import Enum

from pydantic import BaseModel, Field

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
    model_ready: bool = False
    """True if an .xlsx model workbook was generated successfully for this job."""
    model_skip_reason: str | None = None
    """Explanation if Excel model auto-generation was skipped (e.g. no auto-accepted records)."""
    filing_year: int | None = None
    """User-selected fiscal year for the filing (e.g. 2023)."""
    company_id: str | None = None
    """UUIDv4 of the associated CompanyRecord, if assigned."""


class CompanyRecord(BaseModel):
    """A persisted company grouping record (Phase 2 Multi-Year Architecture)."""

    company_id: str
    """UUIDv4 — system-generated company identifier."""
    name: str
    """Human-readable company name (e.g. 'Acme Corporation')."""
    ticker: str | None = None
    """Optional stock ticker symbol (e.g. 'ACME')."""
    created_at: str
    """ISO 8601 UTC timestamp of creation, e.g. '2026-08-23T12:00:00Z'."""
    job_ids: list[str] = Field(default_factory=list)
    """List of job UUIDs associated with this company."""


class CreateCompanyRequest(BaseModel):
    """Request payload for POST /companies."""

    name: str
    """Human-readable company name (required, non-empty)."""
    ticker: str | None = None
    """Optional stock ticker symbol."""


class CompanyWithJobs(BaseModel):
    """A company record bundled with its resolved JobRecords for API responses."""

    company_id: str
    name: str
    ticker: str | None = None
    created_at: str
    job_ids: list[str] = Field(default_factory=list)
    jobs: list[JobRecord] = Field(default_factory=list)


class SubmitResponse(BaseModel):
    """Response for POST /upload/jobs: split between created records and rejections."""

    created_jobs: list[JobRecord]
    rejections: list[FileValidationResult]


class GetJobsResponse(BaseModel):
    """Response model for GET /upload/jobs."""

    jobs: list[JobRecord]


class EdgarCompanyResult(BaseModel):
    """Company search result from EDGAR EFTS / company tickers."""

    cik: str
    company_name: str
    sic: str | None = None
    ticker: str | None = None


class EdgarFiling(BaseModel):
    """SEC filing metadata parsed from EDGAR submissions API."""

    accession_number: str
    form_type: str
    filing_date: str
    report_date: str | None = None
    primary_document: str = ""
    description: str | None = None
    filing_year: int | None = None


class EdgarSubmitRequest(BaseModel):
    """Request payload for POST /upload/edgar."""

    cik: str
    accession_number: str
    target_metric: str = "Adjusted EBITDA"
    filing_year: int | None = None
    company_name: str | None = None
    primary_document: str | None = None


class MultiYearModelResponse(BaseModel):
    """Response for POST /companies/{company_id}/multi-year-model."""

    company_id: str
    download_url: str
    years: list[int]
    total_cells_generated: int
    file_path: str
