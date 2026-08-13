"""
Unit tests for app.extraction.coordinate_normalizer.
"""

from pathlib import Path

import pymupdf
import pytest
from app.extraction.coordinate_normalizer import (
    CoordinateNormalizationError,
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
    )
    # 600x800 page
    norm = normalize_item_bbox(item, page_width=600.0, page_height=800.0)

    # 60/600 * 1000 = 100.0, 80/800 * 1000 = 100.0
    # 300/600 * 1000 = 500.0, 400/800 * 1000 = 500.0
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
        ),
        DoclingItem(
            value="200",
            label="Header 2",
            page=2,
            bbox=DoclingBbox(x0=120.0, y0=160.0, x1=480.0, y1=640.0),
            source_file="test.pdf",
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
    with pytest.raises(CoordinateNormalizationError, match="out of bounds"):
        normalize_coordinates(pdf_path, items)
