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
    assert "value_is_numeric" in flags

    scored = score_record(rec)
    assert scored.confidence_band == ConfidenceBand.auto_accepted


def test_compute_confidence_score_missing_header_hierarchy() -> None:
    rec = _make_record(
        value="500",
        label="Net Sales",  # No ' / ' hierarchy separator
    )
    score, flags = compute_confidence_score(rec)
    assert score == 0.90
    assert "missing_header_hierarchy" in flags
    assert "value_is_numeric" in flags

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


def test_reconciliation_candidate_flat_label_receives_bonus() -> None:
    """Ticket 3.3: Flat label in reconciliation candidate table scores >= 0.95 (auto_accepted)."""
    rec = ExtractedRecord(
        value="500",
        label="Stock-based compensation",  # Flat label without ' / '
        page=1,
        bbox={"x0": 0.0, "y0": 0.0, "x1": 10.0, "y1": 10.0},
        source_file="test.pdf",
        is_reconciliation_candidate=True,
    )
    score, _ = compute_confidence_score(rec)
    assert score >= 0.95
    scored = score_record(rec)
    assert scored.confidence_band == ConfidenceBand.auto_accepted

    # Non-reconciliation table flat label with non-numeric value remains 0.85 (needs_review)
    rec_non_rec = ExtractedRecord(
        value="N/A",
        label="Stock-based compensation",
        page=1,
        bbox={"x0": 0.0, "y0": 0.0, "x1": 10.0, "y1": 10.0},
        source_file="test.pdf",
        is_reconciliation_candidate=False,
    )
    score_non_rec, _ = compute_confidence_score(rec_non_rec)
    assert score_non_rec == 0.85
    scored_non_rec = score_record(rec_non_rec)
    assert scored_non_rec.confidence_band == ConfidenceBand.needs_review


def test_numeric_value_signal_parenthetical_negative() -> None:
    """Ticket 6.1: A cell with parenthetical negative (123,456) scores 0.05 higher than non-numeric."""
    from app.extraction.confidence import is_well_formed_numeric_value

    assert is_well_formed_numeric_value("(123,456)") is True
    assert is_well_formed_numeric_value("$1,234.50") is True
    assert is_well_formed_numeric_value("12.5%") is True
    assert is_well_formed_numeric_value(" ( 500 ) ") is True
    assert is_well_formed_numeric_value("N/A") is False
    assert is_well_formed_numeric_value("Text Label") is False
    assert is_well_formed_numeric_value("") is False

    rec_num = _make_record(
        value="(123,456)",
        label="Miscellaneous Expenses",
    )
    score_num, flags_num = compute_confidence_score(rec_num)
    assert "value_is_numeric" in flags_num
    assert score_num == 0.90

    rec_non_num = _make_record(
        value="Unknown",
        label="Miscellaneous Expenses",
    )
    score_non_num, flags_non_num = compute_confidence_score(rec_non_num)
    assert "value_is_numeric" not in flags_non_num
    assert score_non_num == 0.85

    assert round(score_num - score_non_num, 2) == 0.05


def test_table_consistency_boost() -> None:
    """Ticket 6.2: If >= 70% of items in table score >= 0.80, remaining items get +0.10 boost."""
    from app.extraction.models import NormalizedItem

    # Table with 10 items: 7 items have hierarchy (score 1.0), 3 items have ambiguity (score 0.70)
    records: list[ExtractedRecord] = []
    normalized: list[NormalizedItem] = []

    for i in range(7):
        rec = ExtractedRecord(
            value=f"{100 + i}",
            label=f"Section / Item {i}",
            page=1,
            bbox={"x0": 0.0, "y0": float(i * 10), "x1": 100.0, "y1": float(i * 10 + 8)},
            source_file="test.pdf",
        )
        records.append(rec)
        normalized.append(
            NormalizedItem(
                id=f"item_{i}",
                value=rec.value,
                label=rec.label,
                page=rec.page,
                bbox={"x0": 0.0, "y0": 0.0, "x1": 100.0, "y1": 100.0},
                source_file=rec.source_file,
                table_name="Table_Reconciliation",
            )
        )

    for i in range(7, 10):
        rec = ExtractedRecord(
            value=f"{100 + i}",
            label=f"Merged Cell Ambiguity {i}",  # missing hierarchy (-0.15) + ambiguity (-0.35) + numeric (+0.05) = 0.55 (manual_required)
            page=1,
            bbox={"x0": 0.0, "y0": float(i * 10), "x1": 100.0, "y1": float(i * 10 + 8)},
            source_file="test.pdf",
        )
        records.append(rec)
        normalized.append(
            NormalizedItem(
                id=f"item_{i}",
                value=rec.value,
                label=rec.label,
                page=rec.page,
                bbox={"x0": 0.0, "y0": 0.0, "x1": 100.0, "y1": 100.0},
                source_file=rec.source_file,
                table_name="Table_Reconciliation",
            )
        )

    # 7 out of 10 = 70% >= 0.80
    scored = score_records(records, normalized)

    # First 7 items should be 1.0 / auto_accepted
    for i in range(7):
        assert scored[i].confidence_score == 1.0
        assert scored[i].confidence_band == ConfidenceBand.auto_accepted

    # Last 3 items initially 0.55, boosted by +0.10 to 0.65 -> needs_review!
    for i in range(7, 10):
        assert scored[i].confidence_score == 0.65
        assert scored[i].confidence_band == ConfidenceBand.needs_review
        assert "table_consistency_boost" in scored[i].flags


def test_reconciliation_bonus_scores_ge_95_and_non_rec_unaffected() -> None:
    """
    Test B-6: A reconciliation table item with flat label scores >= 0.95 (auto_accepted),
    while a non-reconciliation table item with flat label is unaffected by the +0.15 bonus (score 0.90, needs_review).
    """
    rec_rec = ExtractedRecord(
        value="1,200",
        label="Stock-Based Compensation",  # flat label: -0.15 hierarchy, +0.15 is_rec, +0.05 numeric -> 1.0
        page=1,
        bbox={"x0": 0.0, "y0": 0.0, "x1": 10.0, "y1": 10.0},
        source_file="test.pdf",
        is_reconciliation_candidate=True,
    )
    score_rec, _ = compute_confidence_score(rec_rec)
    assert score_rec >= 0.95
    assert score_rec == 1.0
    scored_rec = score_record(rec_rec)
    assert scored_rec.confidence_band == ConfidenceBand.auto_accepted

    rec_non_rec = ExtractedRecord(
        value="1,200",
        label="Stock-Based Compensation",  # flat label: -0.15 hierarchy, 0 is_rec, +0.05 numeric -> 0.90
        page=1,
        bbox={"x0": 0.0, "y0": 0.0, "x1": 10.0, "y1": 10.0},
        source_file="test.pdf",
        is_reconciliation_candidate=False,
    )
    score_non_rec, _ = compute_confidence_score(rec_non_rec)
    assert score_non_rec == 0.90
    scored_non_rec = score_record(rec_non_rec)
    assert scored_non_rec.confidence_band == ConfidenceBand.needs_review
