"""
Extraction flagging and summary reporting for Feature 2, Step 5.

Scope:
    Provides queryable filtering for non-auto-accepted items and compiles
    job-level extraction summary statistics including the 15% failure threshold evaluation.

Isolation (CONSTITUTION §3.8, §3.2):
    This module must NEVER import from classification/, formula_engine/, excel_export/,
    or audit_report/.
"""

from app.extraction.models import ConfidenceBand, ExtractionSummary, ScoredRecord


def filter_flagged_records(records: list[ScoredRecord]) -> list[ScoredRecord]:
    """
    Filter scored extraction records to return only non-auto-accepted items.

    Items in 'needs_review' or 'manual_required' are visibly flagged (Spec §5, AC-5).
    Zero items below 0.95 confidence reach auto_accepted.

    Args:
        records: List of ScoredRecord objects from the confidence scoring stage.

    Returns:
        List of ScoredRecord objects requiring review or manual entry.
    """
    return [r for r in records if r.confidence_band != ConfidenceBand.auto_accepted]


def create_extraction_summary(records: list[ScoredRecord]) -> ExtractionSummary:
    """
    Compute aggregate summary statistics and threshold evaluation for an extraction job.

    Per Plan §6.1 Item 4 and Feature 9 spec:
        A filing fails extraction if > 15.0% of its line items fall outside
        the auto-accept confidence band.

    Args:
        records: List of all ScoredRecord objects produced for a job.

    Returns:
        An ExtractionSummary Pydantic model instance.
    """
    total_items = len(records)
    auto_accepted_count = sum(
        1 for r in records if r.confidence_band == ConfidenceBand.auto_accepted
    )
    needs_review_count = sum(
        1 for r in records if r.confidence_band == ConfidenceBand.needs_review
    )
    manual_required_count = sum(
        1 for r in records if r.confidence_band == ConfidenceBand.manual_required
    )
    flagged_count = needs_review_count + manual_required_count

    if total_items > 0:
        flagged_percentage = round((flagged_count / total_items) * 100.0, 2)
    else:
        flagged_percentage = 0.0

    passed_threshold = flagged_percentage <= 15.0

    return ExtractionSummary(
        total_items=total_items,
        auto_accepted_count=auto_accepted_count,
        needs_review_count=needs_review_count,
        manual_required_count=manual_required_count,
        flagged_count=flagged_count,
        flagged_percentage=flagged_percentage,
        passed_threshold=passed_threshold,
    )
