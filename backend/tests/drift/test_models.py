"""
Unit tests for drift domain models (Feature 7, Step 1).
"""

from app.drift.models import DriftComparisonResult, MetricDefinitionNode


def test_metric_definition_node_creation() -> None:
    node = MetricDefinitionNode(
        node_id="node_123",
        entity="ACME_CORP",
        target_metric="Adjusted EBITDA",
        filing_year=2023,
        component_labels=["Stock-Based Compensation", "Restructuring Charges"],
        created_at="2026-08-17T12:00:00Z",
    )
    assert node.node_id == "node_123"
    assert node.entity == "ACME_CORP"
    assert node.target_metric == "Adjusted EBITDA"
    assert node.filing_year == 2023
    assert len(node.component_labels) == 2
    assert node.created_at == "2026-08-17T12:00:00Z"


def test_drift_comparison_result_baseline() -> None:
    result = DriftComparisonResult(
        entity="ACME_CORP",
        target_metric="Adjusted EBITDA",
        filing_year=2022,
        is_baseline=True,
        added_labels=[],
        removed_labels=[],
        unchanged_labels=["Stock-Based Compensation"],
        current_labels=["Stock-Based Compensation"],
        prior_node_id=None,
        has_discrepancy=False,
    )
    assert result.is_baseline is True
    assert result.has_discrepancy is False
    assert result.prior_node_id is None
    assert result.added_labels == []
    assert result.removed_labels == []


def test_drift_comparison_result_with_discrepancy() -> None:
    result = DriftComparisonResult(
        entity="ACME_CORP",
        target_metric="Adjusted EBITDA",
        filing_year=2024,
        is_baseline=False,
        added_labels=["Legal Settlement"],
        removed_labels=["Acquisition Costs"],
        unchanged_labels=["Stock-Based Compensation"],
        current_labels=["Legal Settlement", "Stock-Based Compensation"],
        prior_node_id="node_2023",
        has_discrepancy=True,
    )
    assert result.is_baseline is False
    assert result.has_discrepancy is True
    assert result.prior_node_id == "node_2023"
    assert result.added_labels == ["Legal Settlement"]
    assert result.removed_labels == ["Acquisition Costs"]
