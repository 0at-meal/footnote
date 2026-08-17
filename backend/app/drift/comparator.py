"""
Pure comparator engine for Cross-Year Drift Detection (Feature 7, Step 1).

Governed by CONSTITUTION §1.1 (mypy --strict), §1.4 (pure functions), §3.5 (isolation).
"""

from app.drift.models import DriftComparisonResult, MetricDefinitionNode
from app.review.models import ReviewItem, ReviewStatus


def extract_locked_normalized_labels(items: list[ReviewItem]) -> list[str]:
    """
    Extract sorted, unique normalized labels from confirmed, locked review items.

    Only items with status == ReviewStatus.locked and a valid non-empty normalized_label
    are included. All other statuses (e.g. pending_taxonomy_confirmation, needs_review,
    manual_required, extraction_error, flagged) are strictly excluded per spec AC-5.

    Args:
        items: List of ReviewItem objects from the review store.

    Returns:
        Sorted list of unique normalized label strings.
    """
    labels: set[str] = set()
    for item in items:
        if (
            item.status == ReviewStatus.locked
            and item.normalized_label is not None
            and item.normalized_label.strip()
        ):
            labels.add(item.normalized_label)

    return sorted(labels)


def compare_metric_components(
    entity: str,
    target_metric: str,
    filing_year: int,
    current_labels: list[str],
    prior_node: MetricDefinitionNode | None,
) -> DriftComparisonResult:
    """
    Compare a filing's confirmed component labels against a prior-year graph definition.

    Performs exact string equality comparisons to identify added, removed, and unchanged
    component labels for a given entity and target metric.

    If prior_node is None, the filing is treated as the baseline year (spec AC-3, EC-10).

    Args:
        entity: Entity identifier (e.g. 'ACME').
        target_metric: Target metric name (e.g. 'Adjusted EBITDA').
        filing_year: Current filing year.
        current_labels: Normalized component labels for the current filing.
        prior_node: Prior-year MetricDefinitionNode from the drift graph, if any.

    Returns:
        DriftComparisonResult detailing differences or baseline initialization.
    """
    deduped_current = sorted(set(current_labels))

    if prior_node is None:
        return DriftComparisonResult(
            entity=entity,
            target_metric=target_metric,
            filing_year=filing_year,
            is_baseline=True,
            added_labels=[],
            removed_labels=[],
            unchanged_labels=deduped_current,
            current_labels=deduped_current,
            prior_node_id=None,
            has_discrepancy=False,
        )

    current_set = set(deduped_current)
    prior_set = set(prior_node.component_labels)

    added = sorted(current_set - prior_set)
    removed = sorted(prior_set - current_set)
    unchanged = sorted(current_set & prior_set)

    return DriftComparisonResult(
        entity=entity,
        target_metric=target_metric,
        filing_year=filing_year,
        is_baseline=False,
        added_labels=added,
        removed_labels=removed,
        unchanged_labels=unchanged,
        current_labels=deduped_current,
        prior_node_id=prior_node.node_id,
        has_discrepancy=bool(added or removed),
    )
