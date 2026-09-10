"""
API Router for Model Downloads and Provenance Lookups (Feature 4 Step 4).

Exposes:
- GET /models/{job_id}/download (Exposed for Feature 6/8)
- GET /models/{job_id}/provenance (Exposed for Feature 6/8)
- GET /models/{job_id}/provenance/{sheet_name}/{cell_coord} (Exposed for Feature 6)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.classification.repository import ClassificationRepository
from app.excel_export.bridge_generator import generate_bridge_workbook
from app.excel_export.debt_schedule_generator import (
    generate_capital_structure_workbook,
)
from app.excel_export.models import (
    ProvenanceQueryResponse,
    W3CAnnotationRecord,
    WorkbookGenerationResult,
)
from app.excel_export.multi_statement_generator import generate_multi_statement_workbook
from app.excel_export.repository import ModelRepository
from app.footnote.models import DebtSchedule, LeaseSchedule
from app.footnote.repository import (
    DebtScheduleRepository,
    LeaseScheduleRepository,
)
from app.formula_engine.reader import (
    read_formula_inputs,
    read_formula_inputs_from_review,
)
from app.formula_engine.tree import (
    build_comprehensive_model_tree,
    build_formula_tree,
)
from app.ingestion.repository import JobRepository
from app.review.repository import ReviewRepository

router = APIRouter(prefix="/models", tags=["models"])


def get_model_repository() -> ModelRepository:
    """Returns the active model repository instance."""
    return ModelRepository()


@router.post(
    "/{job_id}/generate",
    response_model=WorkbookGenerationResult,
    summary="Compile confirmed review items into an Excel model workbook",
)
def generate_model_workbook(
    job_id: str,
    model_repo: Annotated[ModelRepository, Depends(get_model_repository)],
) -> WorkbookGenerationResult:
    """
    Builds the deterministic FormulaTree and compiles the .xlsx model workbook
    along with W3C Web Annotation provenance records. Reads from Review state (Feature 5)
    or falls back to Classification state (Feature 3).
    Routes to the appropriate generator based on the job's workflow pack:
    - capital_structure: Debt Schedule and Lease Waterfall (debt_schedule_generator)
    - non_gaap_bridge: Non-GAAP EBITDA / Adj EBITDA reconciliation bridge (bridge_generator)
    - other / default: Multi-statement comprehensive model (multi_statement_generator)
    """
    job_repo = JobRepository(data_dir=model_repo.data_dir)
    job = job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    if job.workflow_pack == "capital_structure":
        debt_repo = DebtScheduleRepository(data_dir=model_repo.data_dir)
        lease_repo = LeaseScheduleRepository(data_dir=model_repo.data_dir)
        debt_sched = debt_repo.get_debt_schedule(job_id) or DebtSchedule(
            job_id=job_id, tranches=[]
        )
        lease_sched = lease_repo.get_lease_schedule(job_id) or LeaseSchedule(
            job_id=job_id, years=[]
        )

        generation_result = generate_capital_structure_workbook(
            debt_schedule=debt_sched,
            lease_schedule=lease_sched,
            job_id=job_id,
            output_dir=model_repo.data_dir,
        )
        model_repo.save_generation_result(job_id, generation_result)

        if not generation_result.is_success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=generation_result.error_detail
                or "Failed to generate Capital Structure workbook.",
            )

        if generation_result.provenance_records:
            model_repo.save_provenance_records(
                job_id, generation_result.provenance_records
            )

        return generation_result

    review_repo = ReviewRepository(data_dir=model_repo.data_dir)
    review_items = review_repo.get_review_items(job_id)

    if review_items is not None and len(review_items) > 0:
        batch = read_formula_inputs_from_review(review_items)
    else:
        classification_repo = ClassificationRepository(data_dir=model_repo.data_dir)
        classified_records = classification_repo.get_classified_records(job_id)
        if classified_records is not None and len(classified_records) > 0:
            batch = read_formula_inputs(classified_records)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No confirmed or extracted records found for job '{job_id}'.",
            )

    if batch.error_message or len(batch.nodes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=batch.error_message
            or "No confirmed records available for formula generation.",
        )

    if job.workflow_pack == "non_gaap_bridge":
        formula_tree = build_formula_tree(
            batch, target_metric=job.target_metric or "Adjusted EBITDA"
        )
        if not formula_tree.is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=formula_tree.error_message
                or "Bridge formula tree is invalid (no confirmed add-back items).",
            )
        generation_result = generate_bridge_workbook(
            formula_tree,
            job_id=job_id,
            output_dir=model_repo.data_dir,
        )
    else:
        comp_tree = build_comprehensive_model_tree(batch)
        if not comp_tree.is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=comp_tree.error_message
                or "Comprehensive model tree is invalid (no confirmed line items).",
            )
        generation_result = generate_multi_statement_workbook(
            company=None,
            year_trees=[(job, comp_tree)],
            output_dir=model_repo.data_dir,
        )

    model_repo.save_generation_result(job_id, generation_result)

    if not generation_result.is_success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=generation_result.error_detail or "Failed to generate workbook.",
        )

    if generation_result.provenance_records:
        model_repo.save_provenance_records(
            job_id, generation_result.provenance_records
        )

    return generation_result


@router.get(
    "/{job_id}/download",
    response_class=FileResponse,
    summary="Download generated Excel model workbook",
)
def download_model(
    job_id: str,
    model_repo: Annotated[ModelRepository, Depends(get_model_repository)],
) -> FileResponse:
    """
    Downloads the generated .xlsx workbook for a completed job.
    """
    path = model_repo.get_workbook_path(job_id)
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
def get_provenance_records(
    job_id: str,
    model_repo: Annotated[ModelRepository, Depends(get_model_repository)],
) -> ProvenanceQueryResponse:
    """
    Returns all W3C Web Annotation provenance records queryable by cell reference (Feature 6 / Feature 8).
    """
    records = model_repo.get_provenance_records(job_id)
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
    model_repo: Annotated[ModelRepository, Depends(get_model_repository)],
) -> W3CAnnotationRecord:
    """
    Resolves a cell selection to its full W3C Web Annotation provenance record (Feature 6).
    """
    record = model_repo.get_cell_provenance(job_id, sheet_name, cell_coord)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provenance record for cell '{sheet_name}!{cell_coord}' in job '{job_id}' not found.",
        )

    return record
