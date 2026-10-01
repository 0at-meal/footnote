"""
Quality of Earnings (QoE) tabular diff engine and analytics (FN-034).

Enforces:
- 100% pure functions: no I/O, no networkx, no global mutable state (CONSTITUTION §1.4).
- Tabular row representation: (company, period, component, category, label, value).
- Metrics:
  - Add-backs as a share of reported Adjusted EBITDA
  - Trend: period-over-period add-back growth
  - Category mix: standard category breakdown (SBC, Restructuring, Impairment, etc.)
  - "Recurring non-recurring" flag: same category in >= N of last M periods (default: >= 2 of last 4 periods)
  - Cosmetic relabel detection: auto-detected by category continuity and value proximity
  - Threshold detection: flags if 'Other' exceeds specified share (default: 10%)
"""

from typing import Any
from pydantic import BaseModel, Field

from app.classification.taxonomy import (
    StandardAddBackCategory,
    classify_addback_category,
)


class QoERow(BaseModel):
    """Authoritative tabular record for a single add-back or reconciliation component."""

    company: str
    period: str
    component: str
    category: str
    label: str
    value: float
    is_recurring: bool = False
    is_relabeled: bool = False
    relabeled_from: str | None = None


class QoEDiffReport(BaseModel):
    """Quality of Earnings comparative diff report across periods."""

    company: str
    prior_period: str | None = None
    current_period: str
    reported_ebitda: float | None = None
    total_addbacks: float
    addback_share_of_ebitda: float | None = None
    category_mix: dict[str, float] = Field(default_factory=dict)
    trend_pct: float | None = None
    recurring_categories: list[str] = Field(default_factory=list)
    added_components: list[QoERow] = Field(default_factory=list)
    removed_components: list[QoERow] = Field(default_factory=list)
    relabeled_components: list[QoERow] = Field(default_factory=list)
    other_threshold_exceeded: bool = False
    other_share_pct: float = 0.0
    rows: list[QoERow] = Field(default_factory=list)


def create_qoe_rows_from_leaves(
    company: str,
    period: str,
    leaves: list[Any],
) -> list[QoERow]:
    """Pure helper converting FormulaNode leaves into standardized QoERow objects."""
    rows: list[QoERow] = []
    for leaf in leaves:
        src = getattr(leaf, "source_node", None)
        raw_val = getattr(src, "value", "0") if src else "0"
        try:
            val_clean = str(raw_val).replace(",", "").replace("$", "").strip()
            val = float(val_clean) if val_clean else 0.0
        except ValueError:
            val = 0.0

        lbl = (
            getattr(src, "normalized_label", None)
            or getattr(leaf, "label", "")
        )
        cat = classify_addback_category(lbl).value
        comp_id = getattr(leaf, "node_id", f"comp_{lbl.lower().replace(' ', '_')}")

        rows.append(
            QoERow(
                company=company,
                period=period,
                component=comp_id,
                category=cat,
                label=lbl,
                value=val,
            )
        )
    return rows


def diff_qoe_components(
    current_rows: list[QoERow],
    prior_rows: list[QoERow] | None = None,
    reported_ebitda: float | None = None,
    history_periods: list[list[QoERow]] | None = None,
    other_threshold: float = 0.10,
    recurring_n: int = 2,
    recurring_m: int = 4,
) -> QoEDiffReport:
    """
    Pure diff function comparing reconciliation rows across periods (FN-034).

    Identifies:
    1. Added components (in current period but absent in prior period)
    2. Removed components (in prior period but absent in current period)
    3. Cosmetic relabels: matched by same category and value continuity (abs(delta) <= 1.0)
    4. Recurring non-recurring: category present in >= N of last M historical periods
    5. Category mix and 'Other' threshold warnings
    """
    if len(current_rows) == 0:
        return QoEDiffReport(
            company=prior_rows[0].company if prior_rows else "Unknown",
            current_period="Unknown",
            total_addbacks=0.0,
        )

    company = current_rows[0].company
    current_period = current_rows[0].period
    prior_period = prior_rows[0].period if prior_rows and len(prior_rows) > 0 else None

    # Calculate total addbacks (positive non-GAAP adjustments)
    total_addbacks = sum(max(0.0, r.value) for r in current_rows)

    # Category mix
    category_totals: dict[str, float] = {}
    for r in current_rows:
        category_totals[r.category] = category_totals.get(r.category, 0.0) + max(0.0, r.value)

    category_mix: dict[str, float] = {}
    if total_addbacks > 0.0:
        for cat, amount in category_totals.items():
            category_mix[cat] = round(amount / total_addbacks, 4)

    other_amount = category_totals.get(StandardAddBackCategory.OTHER.value, 0.0)
    other_share = (other_amount / total_addbacks) if total_addbacks > 0.0 else 0.0
    other_threshold_exceeded = other_share > other_threshold

    # Add-backs as share of reported adjusted EBITDA
    addback_share: float | None = None
    if reported_ebitda is not None and reported_ebitda > 0.0:
        addback_share = round(total_addbacks / reported_ebitda, 4)

    # Trend vs prior period
    trend_pct: float | None = None
    if prior_rows and len(prior_rows) > 0:
        prior_total = sum(max(0.0, r.value) for r in prior_rows)
        if prior_total > 0.0:
            trend_pct = round((total_addbacks - prior_total) / prior_total, 4)

    # Recurring non-recurring detection
    # Gather historical periods (including current)
    all_periods = list(history_periods or [])
    if current_rows not in all_periods:
        all_periods.append(current_rows)
    recent_m_periods = all_periods[-recurring_m:]

    category_occurrence_count: dict[str, int] = {}
    for period_items in recent_m_periods:
        seen_in_period = {item.category for item in period_items if item.value > 0.0}
        for cat in seen_in_period:
            category_occurrence_count[cat] = category_occurrence_count.get(cat, 0) + 1

    recurring_categories = [
        cat for cat, count in category_occurrence_count.items()
        if count >= recurring_n and cat != StandardAddBackCategory.OTHER.value
    ]

    # Component diffing vs prior period
    prior_map = {r.label.lower(): r for r in (prior_rows or [])}
    curr_map = {r.label.lower(): r for r in current_rows}

    unmatched_prior: list[QoERow] = []
    unmatched_curr: list[QoERow] = []

    for r in (prior_rows or []):
        if r.label.lower() not in curr_map:
            unmatched_prior.append(r)

    for r in current_rows:
        if r.label.lower() not in prior_map:
            unmatched_curr.append(r)

    # Detect cosmetic relabels: matched by category and value continuity (abs diff <= 1.0 or same value)
    relabeled_components: list[QoERow] = []
    consumed_prior_labels: set[str] = set()
    added_components: list[QoERow] = []

    for curr_r in unmatched_curr:
        matched = False
        for prior_r in unmatched_prior:
            if prior_r.label in consumed_prior_labels:
                continue
            # Cosmetic relabel heuristics: same standard category and close value
            if prior_r.category == curr_r.category and abs(prior_r.value - curr_r.value) <= 1.0:
                relabeled_r = curr_r.model_copy(
                    update={
                        "is_relabeled": True,
                        "relabeled_from": prior_r.label,
                    }
                )
                relabeled_components.append(relabeled_r)
                consumed_prior_labels.add(prior_r.label)
                matched = True
                break
        if not matched:
            added_components.append(curr_r)

    removed_components = [
        r for r in unmatched_prior if r.label not in consumed_prior_labels
    ]

    # Mark recurring flag on individual rows
    annotated_rows: list[QoERow] = []
    for r in current_rows:
        is_rec = r.category in recurring_categories
        relabeled_match = next((rc for rc in relabeled_components if rc.label == r.label), None)
        if relabeled_match:
            annotated_rows.append(relabeled_match.model_copy(update={"is_recurring": is_rec}))
        else:
            annotated_rows.append(r.model_copy(update={"is_recurring": is_rec}))

    return QoEDiffReport(
        company=company,
        prior_period=prior_period,
        current_period=current_period,
        reported_ebitda=reported_ebitda,
        total_addbacks=round(total_addbacks, 2),
        addback_share_of_ebitda=addback_share,
        category_mix=category_mix,
        trend_pct=trend_pct,
        recurring_categories=sorted(recurring_categories),
        added_components=added_components,
        removed_components=removed_components,
        relabeled_components=relabeled_components,
        other_threshold_exceeded=other_threshold_exceeded,
        other_share_pct=round(other_share, 4),
        rows=annotated_rows,
    )
