"""
Unit tests for app.extraction.confidence.
"""

from app.extraction.confidence import (
    assign_confidence_band,
    compute_confidence_score,
    score_record,
    score_records,
)
from app.extraction.models import ConfidenceBand, ExtractedRecord


def _make_record(
    value: str = "100.0",
    label: str = "Operating Expenses / Stock-Based Compensation",
) -> ExtractedRecord:
    return ExtractedRecord(
        value=value,
        label=label,
        page=1,
        bbox={"x0": 10.0, "y0": 20.0, "x1": 100.0, "y1": 50.0},
        source_file="test.pdf",
    )


def test_assign_confidence_band_exact_boundaries() -> None:
    """Verify inclusive boundary conditions per Spec EC-8."""
    assert assign_confidence_band(1.0) == ConfidenceBand.auto_accepted
    assert assign_confidence_band(0.95) == ConfidenceBand.auto_accepted
    assert assign_confidence_band(0.94) == ConfidenceBand.needs_review
    assert assign_confidence_band(0.65) == ConfidenceBand.needs_review
    assert assign_confidence_band(0.64) == ConfidenceBand.manual_required
    assert assign_confidence_band(0.0) == ConfidenceBand.manual_required


def test_compute_confidence_score_clean_record() -> None:
    rec = _make_record(
        value="500",
        label="Revenues / Net Sales / Product Sales",
    )
    score, flags = compute_confidence_score(rec)
    assert score == 1.0
    assert flags == []

    scored = score_record(rec)
    assert scored.confidence_band == ConfidenceBand.auto_accepted


def test_compute_confidence_score_missing_header_hierarchy() -> None:
    rec = _make_record(
        value="500",
        label="Net Sales",  # No ' / ' hierarchy separator
    )
    score, flags = compute_confidence_score(rec)
    assert score == 0.85
    assert "missing_header_hierarchy" in flags

    scored = score_record(rec)
    assert scored.confidence_band == ConfidenceBand.needs_review


def test_compute_confidence_score_label_ambiguity() -> None:
    rec = _make_record(
        value="300",
        label="Operating Expenses / Merged Cell",
    )
    score, flags = compute_confidence_score(rec)
    assert "label_ambiguity" in flags
    assert score < 0.95


def test_compute_confidence_score_footnote_marker() -> None:
    rec = _make_record(
        value="1,234 (1)",
        label="Expenses / SBC*",
    )
    _score, flags = compute_confidence_score(rec)

    assert "footnote_marker_present" in flags


def test_score_records_preserves_ordering() -> None:
    records = [
        _make_record(value="10", label="Section / Item 1"),
        _make_record(value="20", label="Section / Item 2"),
    ]
    scored_list = score_records(records)
    assert len(scored_list) == 2
    assert scored_list[0].record.value == "10"
    assert scored_list[1].record.value == "20"


def test_score_record_propagates_reconciliation_candidate_from_record() -> None:
    rec_true = ExtractedRecord(
        value="100",
        label="Adjusted EBITDA / Tax",
        page=1,
        bbox={"x0": 0.0, "y0": 0.0, "x1": 10.0, "y1": 10.0},
        source_file="test.pdf",
        is_reconciliation_candidate=True,
    )
    scored_true = score_record(rec_true)
    assert scored_true.is_reconciliation_candidate is True

    rec_false = ExtractedRecord(
        value="200",
        label="Cash and Equivalents",
        page=1,
        bbox={"x0": 0.0, "y0": 0.0, "x1": 10.0, "y1": 10.0},
        source_file="test.pdf",
        is_reconciliation_candidate=False,
    )
    scored_false = score_record(rec_false)
    assert scored_false.is_reconciliation_candidate is False
