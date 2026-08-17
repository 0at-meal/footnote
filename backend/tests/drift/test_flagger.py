"""
Unit tests for drift flagger module (Feature 7, Step 2).

Governed by CONSTITUTION §1.1 (mypy --strict), §1.4 (pure functions).
"""

from app.drift.flagger import generate_drift_flag
from app.drift.models import DriftComparisonResult


def test_generate_drift_flag_creates_flag_when_discrepancy_exists() -> None:
    comparison = DriftComparisonResult(
        entity="ACME_CORP",
        target_metric="Adjusted EBITDA",
        filing_year=2023,
        is_baseline=False,
        added_labels=["Legal Settlement", "COVID-19 Relief"],
        removed_labels=["Restructuring Charges"],
        unchanged_labels=["Depreciation & Amortization", "Stock-Based Compensation"],
        current_labels=["COVID-19 Relief", "Depreciation & Amortization", "Legal Settlement", "Stock-Based Compensation"],
        prior_node_id="node_2022_acme",
        has_discrepancy=True,
    )

    flag = generate_drift_flag("job_456", comparison)
    assert flag is not None
    assert flag.job_id == "job_456"
    assert flag.entity == "ACME_CORP"
    assert flag.target_metric == "Adjusted EBITDA"
    assert flag.filing_year == 2023
    assert flag.added_labels == ["Legal Settlement", "COVID-19 Relief"]
    assert flag.removed_labels == ["Restructuring Charges"]
    assert flag.prior_node_id == "node_2022_acme"
    assert flag.flag_id != ""
    assert flag.created_at != ""


def test_generate_drift_flag_returns_none_for_baseline_year() -> None:
    comparison = DriftComparisonResult(
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

    flag = generate_drift_flag("job_123", comparison)
    assert flag is None


def test_generate_drift_flag_returns_none_for_identical_components() -> None:
    comparison = DriftComparisonResult(
        entity="ACME_CORP",
        target_metric="Adjusted EBITDA",
        filing_year=2023,
        is_baseline=False,
        added_labels=[],
        removed_labels=[],
        unchanged_labels=["Stock-Based Compensation"],
        current_labels=["Stock-Based Compensation"],
        prior_node_id="node_2022_acme",
        has_discrepancy=False,
    )

    flag = generate_drift_flag("job_789", comparison)
    assert flag is None


def test_generate_drift_flag_returns_none_when_no_prior_node_id() -> None:
    comparison = DriftComparisonResult(
        entity="ACME_CORP",
        target_metric="Adjusted EBITDA",
        filing_year=2023,
        is_baseline=False,
        added_labels=["New Label"],
        removed_labels=[],
        unchanged_labels=[],
        current_labels=["New Label"],
        prior_node_id=None,
        has_discrepancy=True,
    )

    flag = generate_drift_flag("job_999", comparison)
    assert flag is None
