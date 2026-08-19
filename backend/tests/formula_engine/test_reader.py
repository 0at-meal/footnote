"""
Unit tests for Formula Engine reader and input validation (Feature 4 Step 1).

Tests pure function behavior, schema preservation, exclusion logic, and edge cases:
- AC-8: Exclusion of unconfirmed/pending records
- AC-9: Missing provenance surfaces as FormulaInputError
- EC-1: Preserving duplicate normalized_labels as separate nodes
- EC-2: Non-numeric strings passed through unmodified
- EC-3: Parenthesized negative numbers preserved
- EC-5: Zero confirmed records error
- EC-8: Out-of-bounds bbox coordinates flagged
- CONSTITUTION §1.4: Purity & idempotence
"""

import copy

from app.classification.models import ClassifiedRecord, TaxonomyStatus
from app.extraction.models import ConfidenceBand, ExtractedRecord, ScoredRecord
from app.formula_engine.models import FormulaInputBatch
from app.formula_engine.reader import read_formula_inputs


def _create_classified_record(
    value: str = "1,500.00",
    label: str = "Operating Expenses / Stock-based compensation",
    normalized_label: str | None = "Stock-Based Compensation",
    is_confirmed: bool = True,
    taxonomy_status: TaxonomyStatus = TaxonomyStatus.matched,
    page: int = 42,
    bbox: dict[str, float] | None = None,
    source_file: str = "annual_report.pdf",
    confidence_score: float = 0.98,
    status: str = "ok",
) -> ClassifiedRecord:
    if bbox is None:
        bbox = {"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 250.0}

    extracted = ExtractedRecord(
        value=value,
        label=label,
        page=page,
        bbox=bbox,
        source_file=source_file,
    )
    scored = ScoredRecord(
        record=extracted,
        confidence_score=confidence_score,
        confidence_band=ConfidenceBand.auto_accepted,
        flags=[],
        status="ok" if status == "ok" else "extraction_error",
    )
    return ClassifiedRecord(
        record=scored,
        normalized_label=normalized_label,
        taxonomy_status=taxonomy_status,
        classifier_confidence=0.99,
        is_confirmed=is_confirmed,
    )


def test_read_formula_inputs_confirmed_only() -> None:
    """Verifies that only confirmed records with valid normalized labels are extracted."""
    records = [
        _create_classified_record(
            value="100.0",
            normalized_label="Revenue",
            is_confirmed=True,
        ),
        _create_classified_record(
            value="50.0",
            normalized_label=None,
            is_confirmed=False,
            taxonomy_status=TaxonomyStatus.pending_taxonomy_confirmation,
        ),
        _create_classified_record(
            value="25.0",
            normalized_label="Operating Income",
            is_confirmed=True,
        ),
    ]

    batch = read_formula_inputs(records)

    assert isinstance(batch, FormulaInputBatch)
    assert batch.total_records_received == 3
    assert batch.confirmed_count == 2
    assert batch.excluded_count == 1
    assert len(batch.nodes) == 2
    assert len(batch.errors) == 0
    assert batch.error_message is None

    assert batch.nodes[0].normalized_label == "Revenue"
    assert batch.nodes[0].value == "100.0"
    assert batch.nodes[0].record_index == 0

    assert batch.nodes[1].normalized_label == "Operating Income"
    assert batch.nodes[1].value == "25.0"
    assert batch.nodes[1].record_index == 2


def test_read_formula_inputs_excludes_pending_and_errors() -> None:
    """Verifies that pending_taxonomy_confirmation, extraction errors, and empty labels are excluded (AC-8)."""
    records = [
        _create_classified_record(
            value="10.0",
            normalized_label="SBC",
            is_confirmed=False,
            taxonomy_status=TaxonomyStatus.pending_taxonomy_confirmation,
        ),
        _create_classified_record(
            value="20.0",
            normalized_label="",
            is_confirmed=True,
        ),
        _create_classified_record(
            value="30.0",
            normalized_label=None,
            is_confirmed=False,
        ),
    ]

    batch = read_formula_inputs(records)

    assert batch.total_records_received == 3
    assert batch.confirmed_count == 0
    assert batch.excluded_count == 3
    assert len(batch.nodes) == 0
    assert batch.error_message == "No confirmed records available for formula generation."


def test_read_formula_inputs_duplicate_labels_preserved() -> None:
    """Verifies that duplicate normalized labels are preserved as separate nodes (EC-1)."""
    records = [
        _create_classified_record(
            value="10.0",
            normalized_label="Stock-Based Compensation",
            page=12,
            is_confirmed=True,
        ),
        _create_classified_record(
            value="15.0",
            normalized_label="Stock-Based Compensation",
            page=45,
            is_confirmed=True,
        ),
    ]

    batch = read_formula_inputs(records)

    assert len(batch.nodes) == 2
    assert batch.nodes[0].normalized_label == "Stock-Based Compensation"
    assert batch.nodes[0].page == 12
    assert batch.nodes[0].value == "10.0"

    assert batch.nodes[1].normalized_label == "Stock-Based Compensation"
    assert batch.nodes[1].page == 45
    assert batch.nodes[1].value == "15.0"
    assert batch.nodes[0].node_id != batch.nodes[1].node_id


def test_read_formula_inputs_raw_value_preserved() -> None:
    """Verifies that non-numeric strings and negative numbers in parentheses are untouched (EC-2, EC-3)."""
    records = [
        _create_classified_record(
            value="(1,234.56)",
            normalized_label="Interest Expense",
            is_confirmed=True,
        ),
        _create_classified_record(
            value="N/A",
            normalized_label="Other Adjustments",
            is_confirmed=True,
        ),
        _create_classified_record(
            value="—",
            normalized_label="Restructuring Charges",
            is_confirmed=True,
        ),
    ]

    batch = read_formula_inputs(records)

    assert len(batch.nodes) == 3
    assert batch.nodes[0].value == "(1,234.56)"
    assert batch.nodes[1].value == "N/A"
    assert batch.nodes[2].value == "—"


def test_read_formula_inputs_bbox_out_of_bounds() -> None:
    """Verifies that out-of-bounds coordinates (<0 or >1000) trigger FormulaInputError (EC-8, AC-9)."""
    records = [
        _create_classified_record(
            value="100.0",
            normalized_label="Revenue",
            bbox={"x0": -5.0, "y0": 100.0, "x1": 200.0, "y1": 200.0},
            is_confirmed=True,
        ),
        _create_classified_record(
            value="50.0",
            normalized_label="EBITDA",
            bbox={"x0": 100.0, "y0": 100.0, "x1": 1200.0, "y1": 200.0},
            is_confirmed=True,
        ),
        _create_classified_record(
            value="25.0",
            normalized_label="Valid Item",
            bbox={"x0": 100.0, "y0": 100.0, "x1": 200.0, "y1": 200.0},
            is_confirmed=True,
        ),
    ]

    batch = read_formula_inputs(records)

    assert len(batch.nodes) == 1
    assert batch.nodes[0].normalized_label == "Valid Item"
    assert len(batch.errors) == 2
    assert batch.errors[0].record_index == 0
    assert "EC-8" in batch.errors[0].reason
    assert batch.errors[1].record_index == 1
    assert "EC-8" in batch.errors[1].reason


def test_read_formula_inputs_missing_provenance() -> None:
    """Verifies that missing or invalid provenance metadata is caught and surfaced (AC-9)."""
    records = [
        _create_classified_record(
            value="100.0",
            normalized_label="Item 1",
            source_file="",
            is_confirmed=True,
        ),
        _create_classified_record(
            value="200.0",
            normalized_label="Item 2",
            page=0,
            is_confirmed=True,
        ),
        _create_classified_record(
            value="300.0",
            normalized_label="Item 3",
            bbox={"x0": 100.0, "y0": 100.0, "x1": 50.0, "y1": 200.0},  # x0 > x1
            is_confirmed=True,
        ),
    ]

    batch = read_formula_inputs(records)

    assert len(batch.nodes) == 0
    assert len(batch.errors) == 3
    assert "source_file" in batch.errors[0].reason
    assert "page" in batch.errors[1].reason
    assert "x0 (100.0) cannot be greater than x1 (50.0)" in batch.errors[2].reason


def test_read_formula_inputs_empty_records() -> None:
    """Verifies that an empty input list returns a valid batch with appropriate message (EC-5)."""
    batch = read_formula_inputs([])

    assert batch.total_records_received == 0
    assert batch.confirmed_count == 0
    assert batch.excluded_count == 0
    assert len(batch.nodes) == 0
    assert batch.error_message == "No confirmed records available for formula generation."


def test_read_formula_inputs_purity() -> None:
    """Verifies pure function idempotence and absence of input mutation (CONSTITUTION §1.4)."""
    records = [
        _create_classified_record(
            value="500.0",
            normalized_label="Adjusted EBITDA",
            is_confirmed=True,
        )
    ]
    records_snapshot = copy.deepcopy(records)

    batch1 = read_formula_inputs(records)
    batch2 = read_formula_inputs(records)

    assert batch1 == batch2
    assert records == records_snapshot


def test_read_formula_inputs_mixed_confirmed_unconfirmed_and_errors() -> None:
    """Verifies that read_formula_inputs correctly separates confirmed, pending, and error items."""
    records = [
        _create_classified_record(value="100.0", normalized_label="Revenue", is_confirmed=True),
        _create_classified_record(
            value="20.0",
            normalized_label=None,
            is_confirmed=False,
            taxonomy_status=TaxonomyStatus.pending_taxonomy_confirmation,
        ),
        _create_classified_record(
            value="30.0",
            normalized_label="Operating Expenses",
            is_confirmed=True,
        ),
        _create_classified_record(
            value="40.0",
            normalized_label="Corrupted",
            is_confirmed=False,
            status="extraction_error",
        ),
        _create_classified_record(
            value="50.0",
            normalized_label="",
            is_confirmed=True,
        ),
    ]

    batch = read_formula_inputs(records)

    assert batch.total_records_received == 5
    assert batch.confirmed_count == 2
    assert batch.excluded_count == 3
    assert len(batch.nodes) == 2
    assert [n.normalized_label for n in batch.nodes] == ["Revenue", "Operating Expenses"]
    assert [n.value for n in batch.nodes] == ["100.0", "30.0"]
