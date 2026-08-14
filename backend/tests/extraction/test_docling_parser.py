"""
Unit tests for app.extraction.docling_parser.

All tests mock DocumentConverter so no live Docling model download occurs.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from app.extraction.docling_parser import parse_pdf

# ── Helper Mocks ─────────────────────────────────────────────────────────────


def _make_mock_cell(
    text: str,
    row: int = 0,
    col: int = 0,
    is_col_header: bool = False,
    is_row_header: bool = False,
    page_no: int = 1,
    bbox_tuple: tuple[float, float, float, float] = (10.0, 20.0, 30.0, 40.0),
) -> SimpleNamespace:
    bbox_obj = SimpleNamespace(
        l=bbox_tuple[0],
        t=bbox_tuple[1],
        r=bbox_tuple[2],
        b=bbox_tuple[3],
    )
    prov = SimpleNamespace(
        page_no=page_no,
        bbox=bbox_obj,
    )
    return SimpleNamespace(
        text=text,
        start_row_offset_idx=row,
        start_col_offset_idx=col,
        column_header=is_col_header,
        row_header=is_row_header,
        row_section_header=False,
        bbox=bbox_obj,
        prov=[prov],
    )


def _make_mock_table(cells: list[SimpleNamespace], page_no: int = 1) -> SimpleNamespace:
    table_data = SimpleNamespace(
        grid=[[1]],
        table_cells=cells,
    )
    table_prov = SimpleNamespace(page_no=page_no)
    return SimpleNamespace(data=table_data, prov=[table_prov])


# ── Parser Tests ──────────────────────────────────────────────────────────────


def test_file_not_found_raises(tmp_path: Path) -> None:
    non_existent = tmp_path / "missing.pdf"
    with pytest.raises(FileNotFoundError, match="PDF file not found"):
        parse_pdf(non_existent, "missing.pdf")


def test_empty_document_returns_empty_list(tmp_path: Path) -> None:
    pdf_file = tmp_path / "empty.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    mock_doc = SimpleNamespace(tables=[])
    mock_result = SimpleNamespace(document=mock_doc)

    with patch("app.extraction.docling_parser.DocumentConverter") as MockConverter:
        MockConverter.return_value.convert.return_value = mock_result
        items = parse_pdf(pdf_file, "empty.pdf")

    assert items == []


def test_single_table_produces_items(tmp_path: Path) -> None:
    pdf_file = tmp_path / "sample.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    col_header = _make_mock_cell("Header 2023", row=0, col=1, is_col_header=True)
    row_header = _make_mock_cell("Revenue", row=1, col=0, is_row_header=True)
    data_cell = _make_mock_cell(
        "$1,000", row=1, col=1, page_no=1, bbox_tuple=(50, 100, 80, 120)
    )

    table = _make_mock_table([col_header, row_header, data_cell])
    mock_doc = SimpleNamespace(tables=[table])

    with patch("app.extraction.docling_parser.DocumentConverter") as MockConverter:
        MockConverter.return_value.convert.return_value = SimpleNamespace(
            document=mock_doc
        )
        items = parse_pdf(pdf_file, "sample.pdf")

    assert len(items) == 1
    item = items[0]
    assert item.value == "$1,000"
    assert "Revenue" in item.label
    assert "Header 2023" in item.label
    assert item.page == 1
    assert item.bbox.x0 == 50.0
    assert item.bbox.y0 == 100.0
    assert item.source_file == "sample.pdf"


def test_multi_level_header_path(tmp_path: Path) -> None:
    pdf_file = tmp_path / "multi.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    col_h1 = _make_mock_cell("Fiscal Year", row=0, col=1, is_col_header=True)
    row_h1 = _make_mock_cell("Operating Expenses", row=1, col=0, is_row_header=True)
    val_cell = _make_mock_cell("250", row=1, col=1)

    table = _make_mock_table([col_h1, row_h1, val_cell])
    mock_doc = SimpleNamespace(tables=[table])

    with patch("app.extraction.docling_parser.DocumentConverter") as MockConverter:
        MockConverter.return_value.convert.return_value = SimpleNamespace(
            document=mock_doc
        )
        items = parse_pdf(pdf_file, "multi.pdf")

    assert len(items) == 1
    assert items[0].label == "Operating Expenses / Fiscal Year"


def test_page_number_is_1_indexed(tmp_path: Path) -> None:
    pdf_file = tmp_path / "p2.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    cell = _make_mock_cell("Val", row=0, col=0, page_no=3)
    table = _make_mock_table([cell])

    with patch("app.extraction.docling_parser.DocumentConverter") as MockConverter:
        MockConverter.return_value.convert.return_value = SimpleNamespace(
            document=SimpleNamespace(tables=[table])
        )
        items = parse_pdf(pdf_file, "p2.pdf")

    assert items[0].page == 3


def test_output_order_is_deterministic(tmp_path: Path) -> None:
    pdf_file = tmp_path / "order.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    c1 = _make_mock_cell("Page2", row=0, col=0, page_no=2, bbox_tuple=(10, 10, 20, 20))
    c2 = _make_mock_cell(
        "Page1_Lower", row=1, col=0, page_no=1, bbox_tuple=(10, 50, 20, 60)
    )
    c3 = _make_mock_cell(
        "Page1_Upper", row=0, col=0, page_no=1, bbox_tuple=(10, 10, 20, 20)
    )

    table = _make_mock_table([c1, c2, c3])

    with patch("app.extraction.docling_parser.DocumentConverter") as MockConverter:
        MockConverter.return_value.convert.return_value = SimpleNamespace(
            document=SimpleNamespace(tables=[table])
        )
        items1 = parse_pdf(pdf_file, "order.pdf")
        items2 = parse_pdf(pdf_file, "order.pdf")

    assert [i.value for i in items1] == ["Page1_Upper", "Page1_Lower", "Page2"]
    assert items1 == items2


def test_per_cell_error_is_skipped_not_job_aborting(tmp_path: Path) -> None:
    """A single malformed cell must produce an error item without aborting the parse (spec AC-6, AC-7)."""
    pdf_file = tmp_path / "bad_cell.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    # A good cell that should survive
    good_cell = _make_mock_cell("200", row=0, col=1)

    # A bad cell whose .text property raises
    bad_cell = MagicMock()
    type(bad_cell).text = property(
        lambda self: (_ for _ in ()).throw(RuntimeError("Bad text"))
    )

    table = SimpleNamespace(
        data=SimpleNamespace(grid=[[1]], table_cells=[bad_cell, good_cell])
    )

    with patch("app.extraction.docling_parser.DocumentConverter") as MockConverter:
        MockConverter.return_value.convert.return_value = SimpleNamespace(
            document=SimpleNamespace(tables=[table])
        )
        # Must NOT raise — the bad cell produces an error DoclingItem, good cell is also returned
        items = parse_pdf(pdf_file, "bad_cell.pdf")

    # Both items should be present: the good cell and the error item
    assert len(items) == 2
    good_items = [i for i in items if not i.is_error]
    error_items = [i for i in items if i.is_error]

    assert len(good_items) == 1
    assert good_items[0].value == "200"

    assert len(error_items) == 1
    assert error_items[0].is_error is True
    assert error_items[0].error_detail is not None
    assert "Bad text" in error_items[0].error_detail


def test_source_file_preserved_verbatim(tmp_path: Path) -> None:
    pdf_file = tmp_path / "utf8.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    cell = _make_mock_cell("100", row=0, col=0)
    table = _make_mock_table([cell])

    unicode_filename = "filing_年度_2023.pdf"

    with patch("app.extraction.docling_parser.DocumentConverter") as MockConverter:
        MockConverter.return_value.convert.return_value = SimpleNamespace(
            document=SimpleNamespace(tables=[table])
        )
        items = parse_pdf(pdf_file, unicode_filename)

    assert items[0].source_file == unicode_filename
