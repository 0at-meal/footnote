"""
Unit tests for app.extraction.coordinate_normalizer.
"""

from pathlib import Path

import pymupdf
import pytest
from app.extraction.coordinate_normalizer import (
    CoordinateNormalizationError,
    count_image_only_pages,
    normalize_coordinates,
    normalize_item_bbox,
)
from app.extraction.models import DoclingBbox, DoclingItem


def make_sample_pdf(
    tmp_path: Path, num_pages: int = 2, width: float = 600.0, height: float = 800.0
) -> Path:
    """Create a minimal real PDF using pymupdf with specified page count and dimensions."""
    pdf_path = tmp_path / "test_sample.pdf"
    doc = pymupdf.open()
    for _ in range(num_pages):
        page = doc.new_page(width=width, height=height)
        page.insert_text((50, 50), "Sample Text")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_normalize_item_bbox_exact_scaling() -> None:
    item = DoclingItem(
        value="100",
        label="Revenue",
        page=1,
        bbox=DoclingBbox(x0=60.0, y0=80.0, x1=300.0, y1=400.0),
        source_file="test.pdf",
        parser_used="pymupdf",  # Use pymupdf so we test direct scaling without Y-inversion
    )
    # 600x800 page
    norm = normalize_item_bbox(item, page_width=600.0, page_height=800.0)

    # 60/600 * 1000 = 100.0, 80/800 * 1000 = 100.0
    # 300/600 * 1000 = 500.0, 400/800 * 1000 = 500.0
    # PyMuPDF: no inversion, so values map directly
    assert norm.bbox.x0 == 100.0
    assert norm.bbox.y0 == 100.0
    assert norm.bbox.x1 == 500.0
    assert norm.bbox.y1 == 500.0
    assert norm.value == "100"
    assert norm.label == "Revenue"
    assert norm.page == 1
    assert norm.source_file == "test.pdf"



def test_normalize_item_bbox_clamping_and_inverted() -> None:
    # Point coords outside page boundaries and inverted
    item = DoclingItem(
        value="200",
        label="Expense",
        page=1,
        bbox=DoclingBbox(x0=700.0, y0=900.0, x1=-50.0, y1=-10.0),
        source_file="test.pdf",
        parser_used="pymupdf",  # Test clamping behavior explicitly without Y-inversion
    )
    norm = normalize_item_bbox(item, page_width=600.0, page_height=800.0)

    # x_min = -50 (clamped to 0.0), x_max = 700 (700/600 * 1000 = 1166.67 clamped to 1000.0)
    assert norm.bbox.x0 == 0.0
    assert norm.bbox.x1 == 1000.0
    assert norm.bbox.y0 == 0.0
    assert norm.bbox.y1 == 1000.0


def test_normalize_item_bbox_invalid_page_dimensions() -> None:
    item = DoclingItem(
        value="10",
        label="Tax",
        page=1,
        bbox=DoclingBbox(x0=0.0, y0=0.0, x1=10.0, y1=10.0),
        source_file="test.pdf",
    )
    with pytest.raises(CoordinateNormalizationError, match="Invalid page dimensions"):
        normalize_item_bbox(item, page_width=0.0, page_height=800.0)


def test_normalize_coordinates_success(tmp_path: Path) -> None:
    pdf_path = make_sample_pdf(tmp_path, num_pages=2, width=600.0, height=800.0)

    items = [
        DoclingItem(
            value="100",
            label="Header 1",
            page=1,
            bbox=DoclingBbox(x0=60.0, y0=80.0, x1=300.0, y1=400.0),
            source_file="test.pdf",
            parser_used="pymupdf",  # No Y-inversion for direct scaling check
        ),
        DoclingItem(
            value="200",
            label="Header 2",
            page=2,
            bbox=DoclingBbox(x0=120.0, y0=160.0, x1=480.0, y1=640.0),
            source_file="test.pdf",
            parser_used="pymupdf",  # No Y-inversion for direct scaling check
        ),
    ]

    normalized = normalize_coordinates(pdf_path, items)
    assert len(normalized) == 2

    assert normalized[0].page == 1
    assert normalized[0].bbox.x0 == 100.0
    assert normalized[0].bbox.y1 == 500.0

    assert normalized[1].page == 2
    assert normalized[1].bbox.x0 == 200.0
    assert normalized[1].bbox.y1 == 800.0


def test_normalize_coordinates_nonexistent_pdf(tmp_path: Path) -> None:
    missing_path = tmp_path / "nonexistent.pdf"
    items: list[DoclingItem] = []
    with pytest.raises(FileNotFoundError, match="PDF file not found"):
        normalize_coordinates(missing_path, items)


def test_normalize_coordinates_page_out_of_bounds(tmp_path: Path) -> None:
    pdf_path = make_sample_pdf(tmp_path, num_pages=1)
    items = [
        DoclingItem(
            value="50",
            label="Item",
            page=5,  # Document has only 1 page
            bbox=DoclingBbox(x0=0.0, y0=0.0, x1=10.0, y1=10.0),
            source_file="test.pdf",
        )
    ]
    normalized = normalize_coordinates(pdf_path, items)
    assert len(normalized) == 1
    assert normalized[0].is_error is True
    assert normalized[0].error_detail is not None
    assert "out of bounds" in normalized[0].error_detail


def test_count_image_only_pages(tmp_path: Path) -> None:
    pdf_path = tmp_path / "mixed.pdf"
    doc = pymupdf.open()
    # Page 1 has text
    p1 = doc.new_page(width=600, height=800)
    p1.insert_text((50, 50), "Hello world")
    # Page 2 is empty/image-only (no selectable text)
    doc.new_page(width=600, height=800)
    doc.save(str(pdf_path))
    doc.close()

    image_pages = count_image_only_pages(pdf_path)
    assert image_pages == 1


def test_count_image_only_pages_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent.pdf"
    with pytest.raises(FileNotFoundError, match="PDF file not found"):
        count_image_only_pages(missing)


# ──────────────────────────────────────────────────────────────────────────────
# Ticket 1.4 Tests — Coordinate space inversion and per-cell flat_idx
# ──────────────────────────────────────────────────────────────────────────────


def test_normalize_item_bbox_docling_y_inversion() -> None:
    """
    Docling path: given a cell near the bottom of a 792pt-tall page
    (y0=50, y1=100), after Y-inversion the normalized y0 should be near 1000
    (close to the bottom of the 0-1000 screen space).

    Docling: y0=50 (top of cell, high in page), y1=100 (lower edge).
    After scaling to 0-1000 on a 792pt-tall page:
      y0_raw = 50/792 * 1000 ≈ 63.13
      y1_raw = 100/792 * 1000 ≈ 126.26
    After Docling inversion:
      y0_screen = 1000 - y1_raw ≈ 873.74  (top of cell in screen coords)
      y1_screen = 1000 - y0_raw ≈ 936.87  (bottom of cell in screen coords)
    """
    item = DoclingItem(
        value="50",
        label="Revenue",
        page=1,
        bbox=DoclingBbox(x0=10.0, y0=50.0, x1=200.0, y1=100.0),
        source_file="test.pdf",
        parser_used="docling",
    )
    page_width = 612.0
    page_height = 792.0

    norm = normalize_item_bbox(item, page_width=page_width, page_height=page_height)

    # After inversion: y0 ~ 1000 - (100/792*1000) and y1 ~ 1000 - (50/792*1000)
    expected_y0 = round(1000.0 - (100.0 / page_height) * 1000.0, 2)
    expected_y1 = round(1000.0 - (50.0 / page_height) * 1000.0, 2)

    assert abs(norm.bbox.y0 - expected_y0) < 0.1, f"y0={norm.bbox.y0} expected~{expected_y0}"
    assert abs(norm.bbox.y1 - expected_y1) < 0.1, f"y1={norm.bbox.y1} expected~{expected_y1}"
    # y0 should be much larger than 0 (near bottom of screen space for a cell at y=50-100 from bottom)
    assert norm.bbox.y0 > 800.0, f"Docling bottom cell should map to y0 > 800, got {norm.bbox.y0}"


def test_normalize_item_bbox_pymupdf_no_inversion() -> None:
    """
    PyMuPDF path: given top-left coordinates y0=50, y1=100 on a 792pt page,
    assert the normalized values are y0 ≈ 63 and y1 ≈ 126 (no inversion applied).
    """
    item = DoclingItem(
        value="50",
        label="Expense",
        page=1,
        bbox=DoclingBbox(x0=10.0, y0=50.0, x1=200.0, y1=100.0),
        source_file="test.pdf",
        parser_used="pymupdf",
    )
    page_width = 612.0
    page_height = 792.0

    norm = normalize_item_bbox(item, page_width=page_width, page_height=page_height)

    expected_y0 = round((50.0 / page_height) * 1000.0, 2)
    expected_y1 = round((100.0 / page_height) * 1000.0, 2)

    assert abs(norm.bbox.y0 - expected_y0) < 0.1, f"y0={norm.bbox.y0} expected~{expected_y0}"
    assert abs(norm.bbox.y1 - expected_y1) < 0.1, f"y1={norm.bbox.y1} expected~{expected_y1}"
    # y0 should be near 63, not near 1000
    assert norm.bbox.y0 < 100.0, f"PyMuPDF top cell should map to small y0, got {norm.bbox.y0}"


def test_pymupdf_flat_idx_per_cell_bbox() -> None:
    """
    Ticket 1.4: Per-cell flat_idx test for the PyMuPDF fallback table parser.
    Mock a 3-row x 4-col table. For cell at row_idx=1, col_idx=2:
      flat_idx = (1-1) * 4 + (2-1) = 1
    For cell at row_idx=2, col_idx=3:
      flat_idx = (2-1) * 4 + (3-1) = 6
    Verify each cell gets the correct bbox from table.cells.
    """
    # Build a flat cells list for a 3-row × 4-col logical table
    # Indices: 0..11
    # row_idx=1, col_idx=1 → flat 0
    # row_idx=1, col_idx=2 → flat 1
    # row_idx=2, col_idx=3 → flat 6
    num_rows = 3
    num_cols = 4
    cells = [(float(i * 10), float(i * 5), float(i * 10 + 50), float(i * 5 + 25)) for i in range(num_rows * num_cols)]

    def make_flat_idx(row_idx: int, col_idx: int, row_len: int) -> int:
        return (row_idx - 1) * row_len + (col_idx - 1)

    # Test (row=1, col=1) → idx 0
    flat = make_flat_idx(1, 1, num_cols)
    assert flat == 0, f"Expected 0, got {flat}"
    assert cells[flat] == (0.0, 0.0, 50.0, 25.0)

    # Test (row=1, col=2) → idx 1
    flat = make_flat_idx(1, 2, num_cols)
    assert flat == 1, f"Expected 1, got {flat}"
    assert cells[flat] == (10.0, 5.0, 60.0, 30.0)

    # Test (row=2, col=3) → idx 6
    flat = make_flat_idx(2, 3, num_cols)
    assert flat == 6, f"Expected 6, got {flat}"
    assert cells[flat] == (60.0, 30.0, 110.0, 55.0)

    # Test (row=3, col=4) → idx 11 (last cell)
    flat = make_flat_idx(3, 4, num_cols)
    assert flat == 11, f"Expected 11, got {flat}"
    assert cells[flat] == (110.0, 55.0, 160.0, 80.0)

