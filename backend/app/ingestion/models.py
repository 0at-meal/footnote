from pydantic import BaseModel


class FileValidationResult(BaseModel):
    """Result of server-side validation for a single uploaded file."""

    filename: str
    accepted: bool
    error_message: str | None = None


class ValidationResponse(BaseModel):
    """Per-file validation results for a multi-file upload request."""

    results: list[FileValidationResult]
