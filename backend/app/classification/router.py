"""
FastAPI router for classification stage endpoints (Feature 3 Step 4).

Exposes:
- GET /classification/{job_id}/decision-log (spec.md §6, AC-7)
"""

from fastapi import APIRouter, HTTPException

from app.classification.decision_log import DecisionLogRepository
from app.classification.models import DecisionLogResponse

router = APIRouter()


@router.get(
    "/{job_id}/decision-log",
    response_model=DecisionLogResponse,
    summary="Retrieve machine-readable classification decision log for a job",
)
def get_decision_log(job_id: str) -> DecisionLogResponse:
    """
    Returns the complete decision log for a job (AC-7).

    The decision log provides verifiable proof that classifier calls were strictly
    numeric-free (AC-2).
    """
    repo = DecisionLogRepository()
    entries = repo.get_decision_log(job_id)

    if entries is None:
        raise HTTPException(
            status_code=404,
            detail=f"Decision log not found for job '{job_id}'",
        )

    return DecisionLogResponse(
        job_id=job_id,
        total_calls=len(entries),
        entries=entries,
    )
