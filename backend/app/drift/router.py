"""
FastAPI router for Cross-Year Drift Detection (Feature 7).

Exposes endpoints for querying drift flags, evaluation, graph definitions, and historical metric evolution.
Governed by CONSTITUTION §1.1 (mypy --strict), §1.3 (Pydantic models), §3.11 (isolation).
"""

from fastapi import APIRouter, HTTPException, Query, status

from app.drift.graph import HistoricalDriftGraph
from app.drift.models import (
    DriftEvaluationRequest,
    DriftEvaluationResponse,
    DriftFlagsResponse,
    DriftGraphExport,
    MetricHistoryResponse,
)
from app.drift.repository import DriftRepository
from app.drift.service import evaluate_job_drift
from app.ingestion.repository import JobRepository
from app.review.repository import ReviewRepository

router = APIRouter(prefix="/drift", tags=["drift"])
_drift_repo = DriftRepository()
_job_repo = JobRepository()
_review_repo = ReviewRepository()
_drift_graph_override: HistoricalDriftGraph | None = None


def get_drift_repository() -> DriftRepository:
    """Return the active DriftRepository instance."""
    return _drift_repo


def set_drift_repository(repo: DriftRepository) -> None:
    """Set the active DriftRepository instance (used for tests / DI)."""
    global _drift_repo
    _drift_repo = repo


def get_job_repository() -> JobRepository:
    """Return the active JobRepository instance."""
    return _job_repo


def set_job_repository(repo: JobRepository) -> None:
    """Set the active JobRepository instance (used for tests / DI)."""
    global _job_repo
    _job_repo = repo


def get_review_repository() -> ReviewRepository:
    """Return the active ReviewRepository instance."""
    return _review_repo


def set_review_repository(repo: ReviewRepository) -> None:
    """Set the active ReviewRepository instance (used for tests / DI)."""
    global _review_repo
    _review_repo = repo


def get_drift_graph() -> HistoricalDriftGraph:
    """Return the authoritative HistoricalDriftGraph from SQLite or override."""
    if _drift_graph_override is not None:
        return _drift_graph_override
    return _drift_repo.load_graph()


def set_drift_graph(graph: HistoricalDriftGraph | None) -> None:
    """Set the active HistoricalDriftGraph instance (used for tests / DI)."""
    global _drift_graph_override
    _drift_graph_override = graph


@router.post(
    "/jobs/{job_id}/evaluate",
    response_model=DriftEvaluationResponse,
    summary="Evaluate drift for confirmed review items in a job",
)
def evaluate_job(
    job_id: str,
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
            repo=_drift_repo,
            job_repo=_job_repo,
            review_repo=_review_repo,
            entity=entity,
            filing_year=filing_year,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err

    if comparison is None:
        job = _job_repo.get_job(job_id)
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
def get_job_drift_flags(job_id: str) -> DriftFlagsResponse:
    """
    Retrieve all active drift flags for a processed job (spec AC-8, AC-9, EC-10).

    Returns:
    - 200 OK with flags list (empty if baseline year or identical definition).
    - 404 Not Found if the job ID is unrecognized.
    """
    job = _job_repo.get_job(job_id)
    comparison = _drift_repo.get_comparison_result(job_id)
    flags = _drift_repo.get_drift_flags(job_id)

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
) -> MetricHistoryResponse:
    """
    Retrieve the historical sequence of metric definition nodes and transition edges (spec §3, AC-8).
    """
    graph = get_drift_graph()
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
    entity: str | None = Query(default=None, description="Optional filter by entity"),
    target_metric: str | None = Query(
        default=None, description="Optional filter by target metric"
    ),
) -> DriftGraphExport:
    """
    Retrieve all nodes and edges in the drift graph, optionally filtered by entity and metric (spec §3, AC-8).
    """
    graph = get_drift_graph()
    return graph.export_graph(entity=entity, target_metric=target_metric)
