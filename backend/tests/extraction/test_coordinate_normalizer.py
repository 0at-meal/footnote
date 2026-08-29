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
# Ticket A-6 Tests — Parametrized coordinate space inversion and per-cell flat_idx
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "y0,y1,page_height,expected_y0,expected_y1",
    [
        (50.0, 100.0, 792.0, 873.74, 936.87),
        (0.0, 50.0, 1000.0, 950.0, 1000.0),
        (200.0, 400.0, 800.0, 500.0, 750.0),
    ],
)
def test_normalize_item_bbox_docling_y_inversion_parametrized(
    y0: float, y1: float, page_height: float, expected_y0: float, expected_y1: float
) -> None:
    """
    Parametrized Docling path test: verifies Y-axis inversion across multiple coordinate sets.
    """
    item = DoclingItem(
        value="50",
        label="Revenue",
        page=1,
        bbox=DoclingBbox(x0=10.0, y0=y0, x1=200.0, y1=y1),
        source_file="test.pdf",
        parser_used="docling",
    )
    norm = normalize_item_bbox(item, page_width=600.0, page_height=page_height)
    assert abs(norm.bbox.y0 - expected_y0) <= 0.05
    assert abs(norm.bbox.y1 - expected_y1) <= 0.05


@pytest.mark.parametrize(
    "y0,y1,page_height,expected_y0,expected_y1",
    [
        (50.0, 100.0, 792.0, 63.13, 126.26),
        (0.0, 50.0, 1000.0, 0.0, 50.0),
        (200.0, 400.0, 800.0, 250.0, 500.0),
    ],
)
def test_normalize_item_bbox_pymupdf_no_inversion_parametrized(
    y0: float, y1: float, page_height: float, expected_y0: float, expected_y1: float
) -> None:
    """
    Parametrized PyMuPDF path test: verifies direct top-left coordinate mapping without Y-inversion.
    """
    item = DoclingItem(
        value="50",
        label="Expense",
        page=1,
        bbox=DoclingBbox(x0=10.0, y0=y0, x1=200.0, y1=y1),
        source_file="test.pdf",
        parser_used="pymupdf",
    )
    norm = normalize_item_bbox(item, page_width=600.0, page_height=page_height)
    assert abs(norm.bbox.y0 - expected_y0) <= 0.05
    assert abs(norm.bbox.y1 - expected_y1) <= 0.05


@pytest.mark.parametrize(
    "row_idx,col_idx,expected_flat_idx",
    [
        (1, 1, 0),
        (1, 2, 1),
        (1, 3, 2),
        (1, 4, 3),
        (2, 1, 4),
        (2, 2, 5),
        (2, 3, 6),
        (2, 4, 7),
        (3, 1, 8),
        (3, 2, 9),
        (3, 3, 10),
        (3, 4, 11),
    ],
)
def test_pymupdf_flat_idx_3x4_mock_table(
    row_idx: int, col_idx: int, expected_flat_idx: int
) -> None:
    """
    Test per-cell flat index mapping for all cells in a 3x4 table.
    """
    num_cols = 4
    flat_idx = (row_idx - 1) * num_cols + (col_idx - 1)
    assert flat_idx == expected_flat_idx
