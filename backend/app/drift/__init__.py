"""
Cross-Year Drift Detection package (Feature 7).

Governed by CONSTITUTION §1.1 (mypy --strict), §3.5 (isolation rules).
"""

from app.drift.comparator import (
    compare_metric_components,
    extract_locked_normalized_labels,
)
from app.drift.models import (
    DriftComparisonResult,
    MetricDefinitionNode,
)

__all__ = [
    "DriftComparisonResult",
    "MetricDefinitionNode",
    "compare_metric_components",
    "extract_locked_normalized_labels",
]
