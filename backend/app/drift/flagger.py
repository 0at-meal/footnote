"""
Drift flagger logic for detecting and structuring metric redefinition discrepancies (Feature 7, Step 2).

Governed by CONSTITUTION §1.1 (mypy --strict), §1.4 (pure generation logic), §3.11 (isolation).
"""

import uuid
from datetime import datetime, timezone

from app.drift.models import DriftComparisonResult, DriftFlag


def generate_drift_flag(
    job_id: str,
    comparison: DriftComparisonResult,
) -> DriftFlag | None:
    """
    Generate a structured DriftFlag when component discrepancies are detected.

    Returns None if:
    - The comparison is for a baseline year (no prior definition exists, spec AC-3).
    - Zero discrepancies were found (identical component set, spec AC-9).
    - No prior node reference exists.

    Args:
        job_id: The job ID for the current filing.
        comparison: DriftComparisonResult produced by the comparator.

    Returns:
        A DriftFlag instance if discrepancies exist against a prior node, else None.
    """
    if comparison.is_baseline:
        return None

    if not comparison.has_discrepancy:
        return None

    if comparison.prior_node_id is None:
        return None

    flag_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return DriftFlag(
        flag_id=flag_id,
        job_id=job_id,
        entity=comparison.entity,
        target_metric=comparison.target_metric,
        filing_year=comparison.filing_year,
        added_labels=list(comparison.added_labels),
        removed_labels=list(comparison.removed_labels),
        prior_node_id=comparison.prior_node_id,
        created_at=created_at,
    )
