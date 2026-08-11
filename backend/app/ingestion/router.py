"""
FastAPI router for the ingestion upload endpoint.

At this step (Feature 1, Step 2) the endpoint validates files and
returns per-file results only. Job record creation is Feature 1, Step 3.
"""

from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from app.ingestion.models import ValidationResponse
from app.ingestion.validation import validate_pdf_bytes

router = APIRouter()


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
