"""
Unit tests for app.extraction.assembler.
"""

from app.extraction.assembler import assemble_record, assemble_records
from app.extraction.models import ExtractedRecord, NormalizedBbox, NormalizedItem


def test_extracted_record_schema_fields_frozen() -> None:
    """Verify ExtractedRecord schema fields match the frozen specification plus metadata."""
    expected_fields = {
        "value",
        "label",
        "page",
        "bbox",
        "source_file",
        "is_reconciliation_candidate",
    }
    actual_fields = set(ExtractedRecord.model_fields.keys())
    assert actual_fields == expected_fields


def test_assemble_record_propagates_reconciliation_candidate() -> None:
    item_true = NormalizedItem(
        value="100",
        label="Adjusted EBITDA",
        page=1,
        bbox=NormalizedBbox(x0=0.0, y0=0.0, x1=10.0, y1=10.0),
        source_file="test.pdf",
        is_reconciliation_candidate=True,
    )
    rec_true = assemble_record(item_true)
    assert rec_true.is_reconciliation_candidate is True

    item_false = NormalizedItem(
        value="200",
        label="Cash",
        page=1,
        bbox=NormalizedBbox(x0=0.0, y0=0.0, x1=10.0, y1=10.0),
        source_file="test.pdf",
        is_reconciliation_candidate=False,
    )
    rec_false = assemble_record(item_false)
    assert rec_false.is_reconciliation_candidate is False


def test_assemble_record_converts_bbox_to_dict() -> None:
    item = NormalizedItem(
        value="125.5",
        label="Operating Income",
        page=3,
        bbox=NormalizedBbox(x0=50.0, y0=100.0, x1=400.0, y1=250.0),
        source_file="report_2024.pdf",
    )

    record = assemble_record(item)

    assert record.value == "125.5"
    assert record.label == "Operating Income"
    assert record.page == 3
    assert record.source_file == "report_2024.pdf"

    # Verify bbox is a dictionary with W3C keys
    assert isinstance(record.bbox, dict)
    assert record.bbox == {"x0": 50.0, "y0": 100.0, "x1": 400.0, "y1": 250.0}


def test_assemble_records_preserves_ordering() -> None:
    items = [
        NormalizedItem(
            value="10",
            label="Item 1",
            page=1,
            bbox=NormalizedBbox(x0=0.0, y0=0.0, x1=10.0, y1=10.0),
            source_file="test.pdf",
        ),
        NormalizedItem(
            value="20",
            label="Item 2",
            page=1,
            bbox=NormalizedBbox(x0=0.0, y0=20.0, x1=10.0, y1=30.0),
            source_file="test.pdf",
        ),
    ]

    records = assemble_records(items)
    assert len(records) == 2
    assert records[0].value == "10"
    assert records[1].value == "20"
