"""
Cross-Year Drift Detection package (Feature 7).

Governed by CONSTITUTION §1.1 (mypy --strict), §3.11 (isolation rules).
"""

from app.drift.comparator import (
    compare_metric_components,
    extract_locked_normalized_labels,
)
from app.drift.flagger import generate_drift_flag
from app.drift.models import (
    DriftComparisonResult,
    DriftFlag,
    DriftFlagsResponse,
    MetricDefinitionNode,
)
from app.drift.repository import DriftRepository
from app.drift.router import router

__all__ = [
    "DriftComparisonResult",
    "DriftFlag",
    "DriftFlagsResponse",
    "DriftRepository",
    "MetricDefinitionNode",
    "compare_metric_components",
    "extract_locked_normalized_labels",
    "generate_drift_flag",
    "router",
]
