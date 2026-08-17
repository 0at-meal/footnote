"""
Unit tests for drift comparator engine (Feature 7, Step 1).

Governed by CONSTITUTION §1.1 (mypy --strict), §1.4 (pure functions).
"""

from app.drift.comparator import (
    compare_metric_components,
    extract_locked_normalized_labels,
)
from app.drift.models import MetricDefinitionNode
from app.extraction.models import ConfidenceBand
from app.review.models import ReviewItem, ReviewStatus


def _make_review_item(
    item_id: str,
    normalized_label: str | None,
    status: ReviewStatus,
    label: str = "Operating Expenses",
    value: str = "100.0",
) -> ReviewItem:
    return ReviewItem(
        id=item_id,
        value=value,
        label=label,
        page=1,
        bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 250.0},
        source_file="test_filing.pdf",
        confidence_band=ConfidenceBand.auto_accepted,
        confidence_score=0.98,
        normalized_label=normalized_label,
        taxonomy_status="matched",
        status=status,
    )


def test_extract_locked_normalized_labels_only_locked_items() -> None:
    items = [
        _make_review_item("item_1", "Stock-Based Compensation", ReviewStatus.locked),
        _make_review_item("item_2", "Restructuring Charges", ReviewStatus.locked),
        _make_review_item("item_3", "Litigation Settlement", ReviewStatus.pending_taxonomy_confirmation),
        _make_review_item("item_4", "Acquisition Costs", ReviewStatus.needs_review),
        _make_review_item("item_5", "Goodwill Impairment", ReviewStatus.manual_required),
        _make_review_item("item_6", "Foreign Exchange Loss", ReviewStatus.extraction_error),
        _make_review_item("item_7", "Severance Costs", ReviewStatus.flagged),
    ]

    labels = extract_locked_normalized_labels(items)
    assert labels == ["Restructuring Charges", "Stock-Based Compensation"]


def test_extract_locked_normalized_labels_deduplication_and_null_filtering() -> None:
    items = [
        _make_review_item("item_1", "Stock-Based Compensation", ReviewStatus.locked),
        _make_review_item("item_2", "Stock-Based Compensation", ReviewStatus.locked),
        _make_review_item("item_3", None, ReviewStatus.locked),
        _make_review_item("item_4", "   ", ReviewStatus.locked),
    ]

    labels = extract_locked_normalized_labels(items)
    assert labels == ["Stock-Based Compensation"]


def test_baseline_year_produces_no_discrepancies_and_is_baseline_flag() -> None:
    current_labels = ["Depreciation & Amortization", "Stock-Based Compensation"]
    result = compare_metric_components(
        entity="ACME_CORP",
        target_metric="Adjusted EBITDA",
        filing_year=2022,
        current_labels=current_labels,
        prior_node=None,
    )

    assert result.entity == "ACME_CORP"
    assert result.target_metric == "Adjusted EBITDA"
    assert result.filing_year == 2022
    assert result.is_baseline is True
    assert result.has_discrepancy is False
    assert result.added_labels == []
    assert result.removed_labels == []
    assert result.unchanged_labels == ["Depreciation & Amortization", "Stock-Based Compensation"]
    assert result.current_labels == ["Depreciation & Amortization", "Stock-Based Compensation"]
    assert result.prior_node_id is None


def test_added_and_removed_components_separately_enumerated() -> None:
    prior_node = MetricDefinitionNode(
        node_id="node_2022",
        entity="ACME_CORP",
        target_metric="Adjusted EBITDA",
        filing_year=2022,
        component_labels=[
            "Depreciation & Amortization",
            "Restructuring Charges",
            "Stock-Based Compensation",
        ],
        created_at="2026-08-17T10:00:00Z",
    )

    current_labels = [
        "Depreciation & Amortization",
        "Stock-Based Compensation",
        "Legal Settlement",
        "COVID-19 Relief",
    ]

    result = compare_metric_components(
        entity="ACME_CORP",
        target_metric="Adjusted EBITDA",
        filing_year=2023,
        current_labels=current_labels,
        prior_node=prior_node,
    )

    assert result.is_baseline is False
    assert result.has_discrepancy is True
    assert result.prior_node_id == "node_2022"
    assert result.added_labels == ["COVID-19 Relief", "Legal Settlement"]
    assert result.removed_labels == ["Restructuring Charges"]
    assert result.unchanged_labels == [
        "Depreciation & Amortization",
        "Stock-Based Compensation",
    ]


def test_identical_component_set_produces_zero_discrepancies() -> None:
    prior_node = MetricDefinitionNode(
        node_id="node_2022",
        entity="ACME_CORP",
        target_metric="Adjusted EBITDA",
        filing_year=2022,
        component_labels=[
            "Depreciation & Amortization",
            "Stock-Based Compensation",
        ],
        created_at="2026-08-17T10:00:00Z",
    )

    current_labels = [
        "Stock-Based Compensation",
        "Depreciation & Amortization",
    ]

    result = compare_metric_components(
        entity="ACME_CORP",
        target_metric="Adjusted EBITDA",
        filing_year=2023,
        current_labels=current_labels,
        prior_node=prior_node,
    )

    assert result.is_baseline is False
    assert result.has_discrepancy is False
    assert result.added_labels == []
    assert result.removed_labels == []
    assert result.unchanged_labels == [
        "Depreciation & Amortization",
        "Stock-Based Compensation",
    ]
    assert result.prior_node_id == "node_2022"


def test_exact_string_matching_preserves_special_characters_and_whitespace() -> None:
    prior_node = MetricDefinitionNode(
        node_id="node_2022",
        entity="GLOBAL_CORP",
        target_metric="Adjusted EBITDA",
        filing_year=2022,
        component_labels=["M&A Expenses (Pre-tax)", "R&D Tax Credit / (Rebate)"],
        created_at="2026-08-17T10:00:00Z",
    )

    # Subtle difference in label string
    current_labels = ["M&A Expenses (Pre-Tax)", "R&D Tax Credit / (Rebate)"]

    result = compare_metric_components(
        entity="GLOBAL_CORP",
        target_metric="Adjusted EBITDA",
        filing_year=2023,
        current_labels=current_labels,
        prior_node=prior_node,
    )

    assert result.has_discrepancy is True
    assert result.added_labels == ["M&A Expenses (Pre-Tax)"]
    assert result.removed_labels == ["M&A Expenses (Pre-tax)"]
    assert result.unchanged_labels == ["R&D Tax Credit / (Rebate)"]


def test_zero_locked_records_with_prior_node() -> None:
    prior_node = MetricDefinitionNode(
        node_id="node_2022",
        entity="ACME_CORP",
        target_metric="Adjusted EBITDA",
        filing_year=2022,
        component_labels=["Stock-Based Compensation"],
        created_at="2026-08-17T10:00:00Z",
    )

    result = compare_metric_components(
        entity="ACME_CORP",
        target_metric="Adjusted EBITDA",
        filing_year=2023,
        current_labels=[],
        prior_node=prior_node,
    )

    assert result.has_discrepancy is True
    assert result.added_labels == []
    assert result.removed_labels == ["Stock-Based Compensation"]
    assert result.unchanged_labels == []
    assert result.current_labels == []


def test_comparator_purity_and_determinism() -> None:
    prior_node = MetricDefinitionNode(
        node_id="node_2022",
        entity="TEST_ENT",
        target_metric="Adjusted EBITDA",
        filing_year=2022,
        component_labels=["A", "B", "C"],
        created_at="2026-08-17T10:00:00Z",
    )

    current_labels = ["C", "D", "B"]

    res1 = compare_metric_components("TEST_ENT", "Adjusted EBITDA", 2023, current_labels, prior_node)
    res2 = compare_metric_components("TEST_ENT", "Adjusted EBITDA", 2023, current_labels, prior_node)

    assert res1.model_dump() == res2.model_dump()
    assert res1.added_labels == ["D"]
    assert res1.removed_labels == ["A"]
    assert res1.unchanged_labels == ["B", "C"]
