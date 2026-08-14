"""
Unit tests for app.extraction.flagger.
"""

from app.extraction.flagger import create_extraction_summary, filter_flagged_records
from app.extraction.models import (
    ConfidenceBand,
    ExtractedRecord,
    ScoredRecord,
)


def _make_scored(
    band: ConfidenceBand,
    value: str = "100",
    label: str = "Revenues / Sales",
) -> ScoredRecord:
    rec = ExtractedRecord(
        value=value,
        label=label,
        page=1,
        bbox={"x0": 0.0, "y0": 0.0, "x1": 10.0, "y1": 10.0},
        source_file="test.pdf",
    )
    score = (
        1.0
        if band == ConfidenceBand.auto_accepted
        else (0.8 if band == ConfidenceBand.needs_review else 0.5)
    )
    return ScoredRecord(
        record=rec,
        confidence_score=score,
        confidence_band=band,
        flags=[],
    )


def test_filter_flagged_records_excludes_auto_accepted() -> None:
    records = [
        _make_scored(ConfidenceBand.auto_accepted, value="1"),
        _make_scored(ConfidenceBand.needs_review, value="2"),
        _make_scored(ConfidenceBand.manual_required, value="3"),
    ]

    flagged = filter_flagged_records(records)
    assert len(flagged) == 2
    assert flagged[0].record.value == "2"
    assert flagged[1].record.value == "3"


def test_create_extraction_summary_all_auto_accepted() -> None:
    records = [_make_scored(ConfidenceBand.auto_accepted) for _ in range(10)]

    summary = create_extraction_summary(records)
    assert summary.total_items == 10
    assert summary.auto_accepted_count == 10
    assert summary.needs_review_count == 0
    assert summary.manual_required_count == 0
    assert summary.flagged_count == 0
    assert summary.flagged_percentage == 0.0
    assert summary.passed_threshold is True


def test_create_extraction_summary_exceeds_threshold() -> None:
    # 8 auto_accepted, 2 needs_review (2 out of 10 = 20.0% > 15.0%)
    records = [_make_scored(ConfidenceBand.auto_accepted) for _ in range(8)]
    records.extend([_make_scored(ConfidenceBand.needs_review) for _ in range(2)])

    summary = create_extraction_summary(records)
    assert summary.total_items == 10
    assert summary.flagged_count == 2
    assert summary.flagged_percentage == 20.0
    assert summary.passed_threshold is False


def test_create_extraction_summary_empty_list() -> None:
    summary = create_extraction_summary([])
    assert summary.total_items == 0
    assert summary.flagged_count == 0
    assert summary.flagged_percentage == 0.0
    assert summary.passed_threshold is True
    assert summary.image_only_page_count == 0


def test_create_extraction_summary_with_image_only_pages() -> None:
    records = [_make_scored(ConfidenceBand.auto_accepted) for _ in range(5)]
    summary = create_extraction_summary(records, image_only_page_count=3)
    assert summary.total_items == 5
    assert summary.image_only_page_count == 3
