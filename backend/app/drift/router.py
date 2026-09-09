"""
FastAPI router for Cross-Year Drift Detection (Feature 7).

Exposes endpoints for querying drift flags, evaluation, graph definitions, and historical metric evolution.
Governed by CONSTITUTION §1.1 (mypy --strict), §1.3 (Pydantic models), §3.11 (isolation).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.drift.graph import HistoricalDriftGraph
from app.drift.models import (
    DriftEvaluationRequest,
    DriftEvaluationResponse,
    DriftFlag,
    DriftFlagsResponse,
    DriftGraphExport,
    MarkRelabeledRequest,
    MetricHistoryResponse,
)
from app.drift.repository import DriftRepository
from app.drift.service import evaluate_job_drift
from app.ingestion.repository import JobRepository
from app.review.repository import ReviewRepository

router = APIRouter(prefix="/drift", tags=["drift"])


def get_drift_repository() -> DriftRepository:
    """Dependency provider returning a DriftRepository instance."""
    return DriftRepository()


def get_job_repository() -> JobRepository:
    """Dependency provider returning a JobRepository instance."""
    return JobRepository()


def get_review_repository() -> ReviewRepository:
    """Dependency provider returning a ReviewRepository instance."""
    return ReviewRepository()


def get_drift_graph(
    drift_repo: Annotated[DriftRepository, Depends(get_drift_repository)],
) -> HistoricalDriftGraph:
    """Dependency provider returning the authoritative HistoricalDriftGraph from SQLite."""
    return drift_repo.load_graph()


@router.post(
    "/jobs/{job_id}/evaluate",
    response_model=DriftEvaluationResponse,
    summary="Evaluate drift for confirmed review items in a job",
)
def evaluate_job(
    job_id: str,
    drift_repo: Annotated[DriftRepository, Depends(get_drift_repository)],
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
    review_repo: Annotated[ReviewRepository, Depends(get_review_repository)],
    payload: DriftEvaluationRequest | None = None,
) -> DriftEvaluationResponse:
    """
    Run cross-year drift detection on confirmed locked items for a job (spec §1, §2, §3, §4).

    Synchronously updates the SQLite drift graph and persists drift flags if discrepancies are detected.
    """
    entity = payload.entity if payload else None
    filing_year = payload.filing_year if payload else None

    try:
        comparison, flag, node = evaluate_job_drift(
            job_id=job_id,
            repo=drift_repo,
            job_repo=job_repo,
            review_repo=review_repo,
            entity=entity,
            filing_year=filing_year,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err

    if comparison is None:
        job = job_repo.get_job(job_id)
        return DriftEvaluationResponse(
            job_id=job_id,
            status="skipped_no_locked_records",
            entity=entity or (getattr(job, "entity", None) if job else None),
            target_metric=job.target_metric if job else None,
            filing_year=filing_year
            or (getattr(job, "filing_year", None) if job else None),
            is_baseline=False,
            has_discrepancy=False,
            flag=None,
            active_definition_node=None,
        )

    return DriftEvaluationResponse(
        job_id=job_id,
        status="evaluated",
        entity=comparison.entity,
        target_metric=comparison.target_metric,
        filing_year=comparison.filing_year,
        is_baseline=comparison.is_baseline,
        has_discrepancy=comparison.has_discrepancy,
        flag=flag,
        active_definition_node=node,
    )


@router.get(
    "/jobs/{job_id}/flags",
    response_model=DriftFlagsResponse,
    summary="Get drift flags for a job",
)
@router.get(
    "/flags/{job_id}",
    response_model=DriftFlagsResponse,
    summary="Get drift flags for a job (alias)",
    include_in_schema=False,
)
def get_job_drift_flags(
    job_id: str,
    drift_repo: Annotated[DriftRepository, Depends(get_drift_repository)],
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
) -> DriftFlagsResponse:
    """
    Retrieve all active drift flags for a processed job (spec AC-8, AC-9, EC-10).

    Returns:
    - 200 OK with flags list (empty if baseline year or identical definition).
    - 404 Not Found if the job ID is unrecognized.
    """
    job = job_repo.get_job(job_id)
    comparison = drift_repo.get_comparison_result(job_id)
    flags = drift_repo.get_drift_flags(job_id)

    if job is None and comparison is None and not flags:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    entity = (
        comparison.entity
        if comparison
        else (getattr(job, "entity", None) or getattr(job, "filename", None))
    )
    target_metric = (
        comparison.target_metric if comparison else (job.target_metric if job else None)
    )
    filing_year = (
        comparison.filing_year if comparison else getattr(job, "filing_year", None)
    )
    is_baseline = comparison.is_baseline if comparison else False

    return DriftFlagsResponse(
        job_id=job_id,
        entity=entity,
        target_metric=target_metric,
        filing_year=filing_year,
        is_baseline=is_baseline,
        flags=flags,
        total_flags=len(flags),
    )


@router.get(
    "/history/{entity}/{target_metric}",
    response_model=MetricHistoryResponse,
    summary="Get historical definition evolution for an entity and target metric",
)
def get_metric_history(
    entity: str,
    target_metric: str,
    graph: Annotated[HistoricalDriftGraph, Depends(get_drift_graph)],
) -> MetricHistoryResponse:
    """
    Retrieve the historical sequence of metric definition nodes and transition edges (spec §3, AC-8).
    """
    definitions = graph.get_history(entity=entity, target_metric=target_metric)
    edges = graph.get_edges(entity=entity, target_metric=target_metric)

    return MetricHistoryResponse(
        entity=entity,
        target_metric=target_metric,
        definitions=definitions,
        edges=edges,
        total_definitions=len(definitions),
    )


@router.get(
    "/graph",
    response_model=DriftGraphExport,
    summary="Export the historical drift graph",
)
def export_drift_graph(
    graph: Annotated[HistoricalDriftGraph, Depends(get_drift_graph)],
    entity: str | None = Query(default=None, description="Optional filter by entity"),
    target_metric: str | None = Query(
        default=None, description="Optional filter by target metric"
    ),
) -> DriftGraphExport:
    """
    Retrieve all nodes and edges in the drift graph, optionally filtered by entity and metric (spec §3, AC-8).
    """
    return graph.export_graph(entity=entity, target_metric=target_metric)


@router.post(
    "/jobs/{job_id}/mark-relabeled",
    response_model=DriftFlag,
    summary="Mark a component as confirmed cosmetic relabeling (Step J)",
)
def mark_component_relabeled(
    job_id: str,
    payload: MarkRelabeledRequest,
    drift_repo: Annotated[DriftRepository, Depends(get_drift_repository)],
) -> DriftFlag:
    """
    Confirm that an added/removed component pair represents a cosmetic relabeling (Step J).
    """
    updated_flag = drift_repo.confirm_relabeling(
        job_id=job_id,
        old_label=payload.old_standard_label,
        new_label=payload.new_standard_label,
        justification=payload.justification,
    )
    if updated_flag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Drift flag or relabeled component not found for job '{job_id}'",
        )
    return updated_flag
