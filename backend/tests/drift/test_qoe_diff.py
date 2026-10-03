"""
Unit tests for Quality of Earnings (QoE) diff engine and standard add-backs (FN-033, FN-034).

Covers:
- Add-back classification to standard categories (SBC, Restructuring, Impairment, M&A, Litigation, FX, Other)
- Pure diff function on tabular rows (company, period, component, category, label, value)
- Automatic detection of cosmetic relabels by category & value continuity
- "Recurring non-recurring" flag across historical periods
- Add-backs as share of reported Adjusted EBITDA and category mix
- Threshold flagging when 'Other' add-backs exceed 10%
- Verification that zero NetworkX imports remain
"""

import sys

from app.classification.taxonomy import (
    StandardAddBackCategory,
    classify_addback_category,
)
from app.drift.qoe_diff import (
    QoERow,
    diff_qoe_components,
)


def test_no_networkx_in_sys_modules() -> None:
    """Verifies that NetworkX is completely excised and not imported (FN-034)."""
    assert "networkx" not in sys.modules


def test_standard_addback_category_classification() -> None:
    """Verifies deterministic mapping to standard add-back categories (FN-033)."""
    assert classify_addback_category("Stock-based compensation expense") == StandardAddBackCategory.SBC
    assert classify_addback_category("Share-based payment") == StandardAddBackCategory.SBC
    assert classify_addback_category("Severance and restructuring charges") == StandardAddBackCategory.RESTRUCTURING
    assert classify_addback_category("Facility exit costs") == StandardAddBackCategory.RESTRUCTURING
    assert classify_addback_category("Goodwill impairment charge") == StandardAddBackCategory.IMPAIRMENT
    assert classify_addback_category("Asset write-down") == StandardAddBackCategory.IMPAIRMENT
    assert classify_addback_category("M&A transaction and advisory fees") == StandardAddBackCategory.MA_INTEGRATION
    assert classify_addback_category("Acquisition integration costs") == StandardAddBackCategory.MA_INTEGRATION
    assert classify_addback_category("Legal settlement expense") == StandardAddBackCategory.LITIGATION
    assert classify_addback_category("Litigation dispute reserve") == StandardAddBackCategory.LITIGATION
    assert classify_addback_category("Foreign currency transaction loss") == StandardAddBackCategory.FX
    assert classify_addback_category("Foreign exchange gain / loss") == StandardAddBackCategory.FX
    assert classify_addback_category("Sponsor advisory management fee") == StandardAddBackCategory.OTHER


def test_qoe_diff_metrics_and_cosmetic_relabel() -> None:
    """Verifies pure diffing, cosmetic relabel detection, and EBITDA share metrics (FN-034)."""
    prior_rows = [
        QoERow(
            company="Acme",
            period="FY2022",
            component="c1",
            category=StandardAddBackCategory.SBC.value,
            label="Stock-based compensation",
            value=100.0,
        ),
        QoERow(
            company="Acme",
            period="FY2022",
            component="c2",
            category=StandardAddBackCategory.RESTRUCTURING.value,
            label="Severance and exit costs",
            value=50.0,
        ),
    ]

    current_rows = [
        QoERow(
            company="Acme",
            period="FY2023",
            component="c1",
            category=StandardAddBackCategory.SBC.value,
            label="Stock-based compensation",
            value=120.0,
        ),
        # Cosmetic relabel: same category (Restructuring) and identical value ($50)
        QoERow(
            company="Acme",
            period="FY2023",
            component="c2_new",
            category=StandardAddBackCategory.RESTRUCTURING.value,
            label="Workforce rationalization charges",
            value=50.0,
        ),
        # Added component
        QoERow(
            company="Acme",
            period="FY2023",
            component="c3",
            category=StandardAddBackCategory.LITIGATION.value,
            label="Legal settlement",
            value=30.0,
        ),
    ]

    report = diff_qoe_components(
        current_rows=current_rows,
        prior_rows=prior_rows,
        reported_ebitda=1000.0,
    )

    # 1. Total add-backs: 120 + 50 + 30 = 200.0
    assert report.total_addbacks == 200.0
    # 2. Add-back share of reported EBITDA: 200 / 1000 = 20.0%
    assert report.addback_share_of_ebitda == 0.20
    # 3. Trend vs prior total ($150): (200 - 150) / 150 = 33.33%
    assert report.trend_pct == 0.3333
    # 4. Cosmetic relabel detected
    assert len(report.relabeled_components) == 1
    relabeled = report.relabeled_components[0]
    assert relabeled.label == "Workforce rationalization charges"
    assert relabeled.relabeled_from == "Severance and exit costs"
    assert relabeled.is_relabeled is True
    # 5. Added components: only Legal settlement (since severance was matched as cosmetic relabel)
    assert len(report.added_components) == 1
    assert report.added_components[0].label == "Legal settlement"


def test_qoe_recurring_non_recurring_and_other_threshold() -> None:
    """Verifies that categories appearing in >= 2 of last 4 periods are flagged recurring (FN-034)."""
    p1 = [
        QoERow(company="Beta", period="Q1", component="1", category="Restructuring", label="Exit costs", value=20.0),
        QoERow(company="Beta", period="Q1", component="2", category="Other", label="Miscellaneous", value=50.0),
    ]
    p2 = [
        QoERow(company="Beta", period="Q2", component="1", category="Restructuring", label="Severance", value=15.0),
        QoERow(company="Beta", period="Q2", component="2", category="Other", label="Miscellaneous", value=40.0),
    ]
    current = [
        QoERow(company="Beta", period="Q3", component="1", category="Restructuring", label="Plant closure", value=25.0),
        QoERow(company="Beta", period="Q3", component="2", category="Other", label="Miscellaneous", value=60.0),
    ]

    report = diff_qoe_components(
        current_rows=current,
        prior_rows=p2,
        history_periods=[p1, p2, current],
        other_threshold=0.10,
    )

    # Restructuring appeared in Q1, Q2, Q3 -> flagged as recurring non-recurring
    assert "Restructuring" in report.recurring_categories
    # Other share: 60 / (25 + 60) = 60 / 85 = 70.5% > 10% threshold -> flagged!
    assert report.other_threshold_exceeded is True
    assert report.other_share_pct > 0.70
