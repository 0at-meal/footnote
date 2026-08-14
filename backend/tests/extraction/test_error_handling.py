"""
Unit tests for per-item extraction error handling & exception surfacing (Spec AC-6, AC-7).
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.extraction.assembler import assemble_records
from app.extraction.confidence import score_records
from app.extraction.coordinate_normalizer import normalize_coordinates
from app.extraction.flagger import create_extraction_summary, filter_flagged_records
from app.extraction.models import (
    ConfidenceBand,
    DoclingBbox,
    DoclingItem,
    ExtractedRecord,
    NormalizedBbox,
    NormalizedItem,
    ScoredRecord,
)


def test_coordinate_normalizer_captures_item_exception(tmp_path: Path) -> None:
    """A PyMuPDF exception on one item returns NormalizedItem with is_error=True (AC-6, AC-7)."""
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    good_item = DoclingItem(
        value="100",
        label="Revenue",
        page=1,
        bbox=DoclingBbox(x0=10.0, y0=20.0, x1=30.0, y1=40.0),
        source_file="test.pdf",
    )
    bad_item = DoclingItem(
        value="200",
        label="Expenses",
        page=999,  # Out of range / broken page
        bbox=DoclingBbox(x0=10.0, y0=20.0, x1=30.0, y1=40.0),
        source_file="test.pdf",
    )

    mock_doc = MagicMock()
    mock_page = MagicMock()
    mock_page.rect = MagicMock(width=100.0, height=200.0)

    # Page 1 returns valid page; Page 999 raises IndexError
    def load_page(idx: int) -> MagicMock:
        if idx == 0:
            return mock_page
        raise IndexError("Page number 998 out of range")

    mock_doc.load_page.side_effect = load_page
    mock_doc.__len__.return_value = 1

    with patch("pymupdf.open", return_value=mock_doc):
        normalized = normalize_coordinates(pdf_file, [good_item, bad_item])

    assert len(normalized) == 2
    assert normalized[0].is_error is False
    assert normalized[0].error_detail is None

    assert normalized[1].is_error is True
    assert normalized[1].error_detail is not None
    assert "out of bounds" in normalized[1].error_detail
    assert normalized[1].bbox.x0 == 0.0


def test_confidence_scoring_routes_error_item_to_manual_required() -> None:
    """An error item is scored 0.0, assigned manual_required, and status=extraction_error."""
    err_normalized = NormalizedItem(
        value="Corrupted",
        label="Header",
        page=1,
        bbox=NormalizedBbox(x0=0.0, y0=0.0, x1=0.0, y1=0.0),
        source_file="test.pdf",
        is_error=True,
        error_detail="PyMuPDF render failure",
    )

    scored_list = score_records(
        [
            ExtractedRecord(
                value=err_normalized.value,
                label=err_normalized.label,
                page=err_normalized.page,
                bbox=err_normalized.bbox.model_dump(),
                source_file=err_normalized.source_file,
            )
        ],
        normalized_items=[err_normalized],
    )

    assert len(scored_list) == 1
    scored = scored_list[0]
    assert scored.confidence_score == 0.0
    assert scored.confidence_band == ConfidenceBand.manual_required
    assert scored.status == "extraction_error"
    assert scored.error_detail == "PyMuPDF render failure"
    assert "extraction_error" in scored.flags


def test_flagger_counts_extraction_errors_in_summary() -> None:
    """ExtractionSummary includes extraction_error_count and includes them in flagged items."""
    good_record = ScoredRecord(
        record=ExtractedRecord(
            value="100",
            label="Rev",
            page=1,
            bbox={"x0": 10.0, "y0": 20.0, "x1": 30.0, "y1": 40.0},
            source_file="test.pdf",
        ),
        confidence_score=1.0,
        confidence_band=ConfidenceBand.auto_accepted,
        flags=[],
    )
    error_record = ScoredRecord(
        record=ExtractedRecord(
            value="Bad",
            label="Err",
            page=1,
            bbox={"x0": 0.0, "y0": 0.0, "x1": 0.0, "y1": 0.0},
            source_file="test.pdf",
        ),
        confidence_score=0.0,
        confidence_band=ConfidenceBand.manual_required,
        flags=["extraction_error"],
        status="extraction_error",
        error_detail="Docling cell parse failed",
    )

    scored_records = [good_record, error_record]
    flagged = filter_flagged_records(scored_records)
    summary = create_extraction_summary(scored_records)

    assert len(flagged) == 1
    assert flagged[0] == error_record
    assert summary.total_items == 2
    assert summary.auto_accepted_count == 1
    assert summary.manual_required_count == 1
    assert summary.extraction_error_count == 1
    assert summary.flagged_count == 1


def test_docling_cell_error_propagates_through_pipeline(tmp_path: Path) -> None:
    """A DoclingItem with is_error=True propagates through normalizer, assembler, confidence, and summary."""
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    good_item = DoclingItem(
        value="100",
        label="Operating / Revenue",
        page=1,
        bbox=DoclingBbox(x0=10.0, y0=20.0, x1=30.0, y1=40.0),
        source_file="test.pdf",
    )
    docling_err_item = DoclingItem(
        value="",
        label="Error / Unparsed Cell",
        page=1,
        bbox=DoclingBbox(x0=0.0, y0=0.0, x1=0.0, y1=0.0),
        source_file="test.pdf",
        is_error=True,
        error_detail="Docling cell parse failed",
    )

    mock_doc = MagicMock()
    mock_page = MagicMock()
    mock_page.rect = MagicMock(width=100.0, height=200.0)
    mock_doc.load_page.return_value = mock_page
    mock_doc.__len__.return_value = 1

    with patch("pymupdf.open", return_value=mock_doc):
        normalized = normalize_coordinates(pdf_file, [good_item, docling_err_item])

    assert len(normalized) == 2
    assert normalized[1].is_error is True
    assert normalized[1].error_detail == "Docling cell parse failed"

    extracted_records = assemble_records(normalized)
    scored_records = score_records(extracted_records, normalized)
    summary = create_extraction_summary(scored_records)

    assert len(scored_records) == 2
    assert scored_records[0].status == "ok"
    assert scored_records[1].status == "extraction_error"
    assert scored_records[1].confidence_score == 0.0
    assert scored_records[1].confidence_band == ConfidenceBand.manual_required
    assert scored_records[1].error_detail == "Docling cell parse failed"

    assert summary.total_items == 2
    assert summary.extraction_error_count == 1
    assert summary.manual_required_count == 1
