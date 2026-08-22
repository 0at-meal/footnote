"""
Drift detection service and evaluation orchestrator (Feature 7, Step 4).

Coordinates review items, comparator, flagger, and SQLite graph persistence.
Governed by CONSTITUTION §1.1 (mypy --strict), §1.9 (atomic persistence), §3.11 (isolation).
"""

import logging
from pathlib import Path

from app.drift.comparator import (
    compare_metric_components,
    extract_locked_normalized_labels,
)
from app.drift.flagger import generate_drift_flag
from app.drift.models import (
    DriftComparisonResult,
    DriftFlag,
    MetricDefinitionNode,
)
from app.drift.repository import DriftRepository
from app.ingestion.repository import JobRepository
from app.review.repository import ReviewRepository

logger = logging.getLogger(__name__)


def evaluate_job_drift(
    job_id: str,
    repo: DriftRepository | None = None,
    job_repo: JobRepository | None = None,
    review_repo: ReviewRepository | None = None,
    entity: str | None = None,
    filing_year: int | None = None,
) -> tuple[DriftComparisonResult | None, DriftFlag | None, MetricDefinitionNode | None]:
    """
    Execute full cross-year drift evaluation for a confirmed job (spec §1, §2, §3, §4).

    Steps:
    1. Look up job metadata (entity, target_metric, filing_year).
    2. Extract locked normalized labels from confirmed review items (AC-5).
    3. If zero locked records, skip drift comparison gracefully (EC-4).
    4. Load authoritative historical graph from SQLite store.
    5. Compare against prior-year definition node (if any).
    6. Generate structured drift flag upon redefinition (AC-2, AC-4, silence on AC-3/AC-9).
    7. Apply mutation to graph and persist updated graph + flags atomically (AC-1, AC-7, AC-10).

    Args:
        job_id: Job identifier.
        repo: DriftRepository instance (defaults to shared backend data dir).
        job_repo: JobRepository instance.
        review_repo: ReviewRepository instance.
        entity: Optional override for entity identifier.
        filing_year: Optional override for filing year.

    Returns:
        Tuple of (DriftComparisonResult, DriftFlag | None, MetricDefinitionNode | None).
        All None if zero locked records exist for the target metric (EC-4).
    """
    drift_repo = repo or DriftRepository()
    j_repo = job_repo or JobRepository(data_dir=drift_repo.data_dir)
    r_repo = review_repo or ReviewRepository(data_dir=drift_repo.data_dir)

    job = j_repo.get_job(job_id)
    if job is None:
        raise ValueError(f"Job '{job_id}' not found in repository.")

    # Derive entity and filing year from parameters or job filename/metadata
    resolved_entity = (
        entity or getattr(job, "entity", None) or Path(job.filename).stem.split("_")[0]
    )
    resolved_metric = job.target_metric or "Adjusted EBITDA"
    resolved_year = filing_year or getattr(job, "filing_year", None) or 2024

    review_items = r_repo.get_review_items(job_id) or []
    locked_labels = extract_locked_normalized_labels(review_items)

    # EC-4: Zero locked records -> skip drift detection
    if not locked_labels:
        logger.info(
            "No confirmed locked records for job %s; skipping drift evaluation", job_id
        )
        return None, None, None

    # Load authoritative graph state from SQLite
    graph = drift_repo.load_graph()
    prior_node = graph.get_latest_node(
        entity=resolved_entity, target_metric=resolved_metric
    )

    # Run pure comparison
    comparison = compare_metric_components(
        entity=resolved_entity,
        target_metric=resolved_metric,
        filing_year=resolved_year,
        current_labels=locked_labels,
        prior_node=prior_node,
    )

    # Generate flag if redefinition detected
    flag = generate_drift_flag(job_id=job_id, comparison=comparison)

    # Apply mutation to graph
    node, _edge = graph.apply_comparison(comparison)

    # Synchronously & atomically persist graph, comparison, and flags (AC-7, AC-10)
    drift_repo.save_graph(graph)
    drift_repo.save_comparison_result(job_id, comparison)
    drift_repo.save_drift_flags(job_id, [flag] if flag is not None else [])

    logger.info(
        "Completed drift evaluation for job %s (entity=%s, year=%d, is_baseline=%s, discrepancy=%s)",
        job_id,
        resolved_entity,
        resolved_year,
        comparison.is_baseline,
        comparison.has_discrepancy,
    )

    return comparison, flag, node
