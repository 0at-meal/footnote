"""
Unit tests for app.extraction.docling_parser.

All tests mock DocumentConverter so no live Docling model download occurs.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from app.extraction.docling_parser import DoclingParseError, parse_pdf
from app.extraction.models import DoclingBbox, DoclingItem
from app.ingestion.repository import JobRepository

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
    prov = SimpleNamespace(
        page_no=page_no,
        bbox=SimpleNamespace(
            l=bbox_tuple[0],
            t=bbox_tuple[1],
            r=bbox_tuple[2],
            b=bbox_tuple[3],
        ),
    )
    return SimpleNamespace(
        text=text,
        start_row_offset_idx=row,
        start_col_offset_idx=col,
        column_header=is_col_header,
        row_header=is_row_header,
        row_section_header=False,
        prov=[prov],
    )


def _make_mock_table(cells: list[SimpleNamespace]) -> SimpleNamespace:
    table_data = SimpleNamespace(
        grid=[[1]],
        table_cells=cells,
    )
    return SimpleNamespace(data=table_data)


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
    data_cell = _make_mock_cell("$1,000", row=1, col=1, page_no=1, bbox_tuple=(50, 100, 80, 120))

    table = _make_mock_table([col_header, row_header, data_cell])
    mock_doc = SimpleNamespace(tables=[table])

    with patch("app.extraction.docling_parser.DocumentConverter") as MockConverter:
        MockConverter.return_value.convert.return_value = SimpleNamespace(document=mock_doc)
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
        MockConverter.return_value.convert.return_value = SimpleNamespace(document=mock_doc)
        items = parse_pdf(pdf_file, "multi.pdf")

    assert len(items) == 1
    assert items[0].label == "Operating Expenses / Fiscal Year"


def test_page_number_is_1_indexed(tmp_path: Path) -> None:
    pdf_file = tmp_path / "p2.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    cell = _make_mock_cell("Val", row=0, col=0, page_no=3)
    table = _make_mock_table([cell])

    with patch("app.extraction.docling_parser.DocumentConverter") as MockConverter:
        MockConverter.return_value.convert.return_value = SimpleNamespace(document=SimpleNamespace(tables=[table]))
        items = parse_pdf(pdf_file, "p2.pdf")

    assert items[0].page == 3


def test_output_order_is_deterministic(tmp_path: Path) -> None:
    pdf_file = tmp_path / "order.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    c1 = _make_mock_cell("Page2", row=0, col=0, page_no=2, bbox_tuple=(10, 10, 20, 20))
    c2 = _make_mock_cell("Page1_Lower", row=1, col=0, page_no=1, bbox_tuple=(10, 50, 20, 60))
    c3 = _make_mock_cell("Page1_Upper", row=0, col=0, page_no=1, bbox_tuple=(10, 10, 20, 20))

    table = _make_mock_table([c1, c2, c3])

    with patch("app.extraction.docling_parser.DocumentConverter") as MockConverter:
        MockConverter.return_value.convert.return_value = SimpleNamespace(document=SimpleNamespace(tables=[table]))
        items1 = parse_pdf(pdf_file, "order.pdf")
        items2 = parse_pdf(pdf_file, "order.pdf")

    assert [i.value for i in items1] == ["Page1_Upper", "Page1_Lower", "Page2"]
    assert items1 == items2


def test_per_cell_error_raises_not_swallowed(tmp_path: Path) -> None:
    pdf_file = tmp_path / "bad_cell.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    bad_cell = MagicMock()
    type(bad_cell).text = property(lambda self: (_ for _ in ()).throw(RuntimeError("Bad text")))

    table = SimpleNamespace(data=SimpleNamespace(grid=[[1]], table_cells=[bad_cell]))

    with patch("app.extraction.docling_parser.DocumentConverter") as MockConverter:
        MockConverter.return_value.convert.return_value = SimpleNamespace(document=SimpleNamespace(tables=[table]))
        with pytest.raises(DoclingParseError, match="Table structure extraction failed"):
            parse_pdf(pdf_file, "bad_cell.pdf")


def test_source_file_preserved_verbatim(tmp_path: Path) -> None:
    pdf_file = tmp_path / "utf8.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    cell = _make_mock_cell("100", row=0, col=0)
    table = _make_mock_table([cell])

    unicode_filename = "filing_年度_2023.pdf"

    with patch("app.extraction.docling_parser.DocumentConverter") as MockConverter:
        MockConverter.return_value.convert.return_value = SimpleNamespace(document=SimpleNamespace(tables=[table]))
        items = parse_pdf(pdf_file, unicode_filename)

    assert items[0].source_file == unicode_filename


# ── Repository Extension Tests ───────────────────────────────────────────────

def test_repository_get_pdf_path(tmp_path: Path) -> None:
    repo = JobRepository(data_dir=tmp_path)
    job_id = "test-uuid-123"
    expected_path = tmp_path / "uploads" / f"{job_id}.pdf"
    assert repo.get_pdf_path(job_id) == expected_path


def test_repository_get_job(tmp_path: Path) -> None:
    repo = JobRepository(data_dir=tmp_path)
    job = repo.save_job("report.pdf", b"%PDF-1.4", "Adjusted EBITDA")

    found = repo.get_job(job.job_id)
    assert found is not None
    assert found.filename == "report.pdf"

    not_found = repo.get_job("non-existent-uuid")
    assert not_found is None


def test_repository_save_docling_items(tmp_path: Path) -> None:
    repo = JobRepository(data_dir=tmp_path)
    job_id = "job-docling-test"
    item = DoclingItem(
        value="500",
        label="Net Sales",
        page=1,
        bbox=DoclingBbox(x0=1, y0=2, x1=3, y1=4),
        source_file="sales.pdf",
    )

    dest_path = repo.save_docling_items(job_id, [item])
    assert dest_path.exists()
    assert dest_path.name == f"{job_id}_docling.json"

    # Verify contents
    text = dest_path.read_text(encoding="utf-8")
    assert "Net Sales" in text
    assert "500" in text
