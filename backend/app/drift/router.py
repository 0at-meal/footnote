"""
FastAPI router for Cross-Year Drift Detection (Feature 7, Steps 2 & 3).

Exposes endpoints for querying drift flags, graph definitions, and historical metric evolution.
Governed by CONSTITUTION §1.1 (mypy --strict), §1.3 (Pydantic models), §3.11 (isolation).
"""

from fastapi import APIRouter, HTTPException, Query, status

from app.drift.graph import HistoricalDriftGraph
from app.drift.models import (
    DriftFlagsResponse,
    DriftGraphExport,
    MetricHistoryResponse,
)
from app.drift.repository import DriftRepository
from app.ingestion.repository import JobRepository

router = APIRouter(prefix="/drift", tags=["drift"])
_drift_repo = DriftRepository()
_job_repo = JobRepository()
_drift_graph = HistoricalDriftGraph()


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


def get_drift_graph() -> HistoricalDriftGraph:
    """Return the active HistoricalDriftGraph instance."""
    return _drift_graph


def set_drift_graph(graph: HistoricalDriftGraph) -> None:
    """Set the active HistoricalDriftGraph instance (used for tests / DI)."""
    global _drift_graph
    _drift_graph = graph


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

    entity = comparison.entity if comparison else (getattr(job, "entity", None) or getattr(job, "filename", None))
    target_metric = comparison.target_metric if comparison else (job.target_metric if job else None)
    filing_year = comparison.filing_year if comparison else getattr(job, "filing_year", None)
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
    definitions = _drift_graph.get_history(entity=entity, target_metric=target_metric)
    edges = _drift_graph.get_edges(entity=entity, target_metric=target_metric)

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
    target_metric: str | None = Query(default=None, description="Optional filter by target metric"),
) -> DriftGraphExport:
    """
    Retrieve all nodes and edges in the drift graph, optionally filtered by entity and metric (spec §3, AC-8).
    """
    return _drift_graph.export_graph(entity=entity, target_metric=target_metric)
