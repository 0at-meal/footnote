"""
API Router for Model Downloads and Provenance Lookups (Feature 4 Step 4).

Exposes:
- GET /models/{job_id}/download (Exposed for Feature 6/8)
- GET /models/{job_id}/provenance (Exposed for Feature 6/8)
- GET /models/{job_id}/provenance/{sheet_name}/{cell_coord} (Exposed for Feature 6)
"""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.excel_export.models import (
    ProvenanceQueryResponse,
    W3CAnnotationRecord,
)
from app.excel_export.repository import ModelRepository

router = APIRouter(prefix="/models", tags=["models"])
_model_repo = ModelRepository()


def get_model_repository() -> ModelRepository:
    """Returns the active model repository instance."""
    return _model_repo


def set_model_repository(repo: ModelRepository) -> None:
    """Sets the active model repository instance (used for testing / dependency injection)."""
    global _model_repo
    _model_repo = repo


@router.get(
    "/{job_id}/download",
    response_class=FileResponse,
    summary="Download generated Excel model workbook",
)
def download_model(job_id: str) -> FileResponse:
    """
    Downloads the generated .xlsx workbook for a completed job.
    """
    path = _model_repo.get_workbook_path(job_id)
    if path is None or not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workbook for job '{job_id}' not found.",
        )

    return FileResponse(
        path=path,
        filename=f"{job_id}_model.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get(
    "/{job_id}/provenance",
    response_model=ProvenanceQueryResponse,
    summary="Get all W3C Web Annotation provenance records for a model",
)
def get_provenance_records(job_id: str) -> ProvenanceQueryResponse:
    """
    Returns all W3C Web Annotation provenance records queryable by cell reference (Feature 6 / Feature 8).
    """
    records = _model_repo.get_provenance_records(job_id)
    if records is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provenance records for job '{job_id}' not found.",
        )

    return ProvenanceQueryResponse(
        job_id=job_id,
        total_records=len(records),
        records=records,
    )


@router.get(
    "/{job_id}/provenance/{sheet_name}/{cell_coord}",
    response_model=W3CAnnotationRecord,
    summary="Get single cell W3C Web Annotation provenance record",
)
def get_cell_provenance(
    job_id: str,
    sheet_name: str,
    cell_coord: str,
) -> W3CAnnotationRecord:
    """
    Resolves a cell selection to its full W3C Web Annotation provenance record (Feature 6).
    """
    record = _model_repo.get_cell_provenance(job_id, sheet_name, cell_coord)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provenance record for cell '{sheet_name}!{cell_coord}' in job '{job_id}' not found.",
        )

    return record
