"""
PyMuPDF coordinate normalizer for Feature 2, Step 2.

Scope:
    Takes DoclingItem objects with raw PDF point coordinates and normalizes
    their bounding boxes into 0-1000 coordinate space relative to page dimensions
    using PyMuPDF.

Isolation (CONSTITUTION §3.8, §3.2):
    This module must NEVER import from classification/, formula_engine/, excel_export/,
    or audit_report/.
"""

import logging
from pathlib import Path

import pymupdf

from app.extraction.models import DoclingItem, NormalizedBbox, NormalizedItem

logger = logging.getLogger(__name__)


class CoordinateNormalizationError(Exception):
    """Raised when coordinate resolution or page dimension retrieval fails."""


def normalize_item_bbox(
    item: DoclingItem,
    page_width: float,
    page_height: float,
) -> NormalizedItem:
    """
    Normalize a single DoclingItem's bounding box into 0-1000 coordinate space.

    Args:
        item: The intermediate DoclingItem with point coordinates.
        page_width: Total page width in points.
        page_height: Total page height in points.

    Returns:
        A NormalizedItem with 0-1000 normalized bbox coordinates.

    Raises:
        CoordinateNormalizationError: If page_width or page_height is <= 0.
    """
    if page_width <= 0.0 or page_height <= 0.0:
        raise CoordinateNormalizationError(
            f"Invalid page dimensions ({page_width}x{page_height}) for source file {item.source_file}"
        )

    # Scale raw points to 0-1000 space
    x0_raw = (item.bbox.x0 / page_width) * 1000.0
    y0_raw = (item.bbox.y0 / page_height) * 1000.0
    x1_raw = (item.bbox.x1 / page_width) * 1000.0
    y1_raw = (item.bbox.y1 / page_height) * 1000.0

    # Ensure min <= max ordering
    x_min = min(x0_raw, x1_raw)
    x_max = max(x0_raw, x1_raw)
    y_min = min(y0_raw, y1_raw)
    y_max = max(y0_raw, y1_raw)

    # Clamp to [0.0, 1000.0] interval
    x0_clamped = round(max(0.0, min(1000.0, x_min)), 2)
    x1_clamped = round(max(0.0, min(1000.0, x_max)), 2)
    y0_clamped = round(max(0.0, min(1000.0, y_min)), 2)
    y1_clamped = round(max(0.0, min(1000.0, y_max)), 2)

    return NormalizedItem(
        value=item.value,
        label=item.label,
        page=item.page,
        bbox=NormalizedBbox(
            x0=x0_clamped,
            y0=y0_clamped,
            x1=x1_clamped,
            y1=y1_clamped,
        ),
        source_file=item.source_file,
    )


def normalize_coordinates(
    pdf_path: Path,
    items: list[DoclingItem],
) -> list[NormalizedItem]:
    """
    Normalize bounding boxes for all extracted items in a PDF filing using PyMuPDF.

    Args:
        pdf_path: Path to the PDF file on disk.
        items: List of DoclingItem objects from the Docling structural parse.

    Returns:
        List of NormalizedItem objects with 0-1000 normalized bboxes.

    Raises:
        FileNotFoundError: If pdf_path does not exist.
        CoordinateNormalizationError: If page index is invalid or PyMuPDF fails.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found at path: {pdf_path}")

    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception as err:
        logger.error("Failed to open PDF %s with PyMuPDF: %s", pdf_path, err)
        raise CoordinateNormalizationError(
            f"PyMuPDF failed to open {pdf_path}: {err}"
        ) from err

    try:
        total_pages = len(doc)
        page_dims: dict[int, tuple[float, float]] = {}

        normalized_items: list[NormalizedItem] = []

        for item in items:
            try:
                # Page number in DoclingItem is 1-indexed
                if item.page < 1 or item.page > total_pages:
                    raise CoordinateNormalizationError(
                        f"Item page {item.page} is out of bounds for PDF with {total_pages} pages"
                    )

                if item.page not in page_dims:
                    # PyMuPDF uses 0-indexed page access
                    page = doc.load_page(item.page - 1)
                    rect = page.rect
                    page_dims[item.page] = (float(rect.width), float(rect.height))

                p_width, p_height = page_dims[item.page]
                norm_item = normalize_item_bbox(item, p_width, p_height)
                normalized_items.append(norm_item)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Coordinate normalization failed for item '%s' on page %d: %s",
                    item.value,
                    item.page,
                    exc,
                )
                err_item = NormalizedItem(
                    value=item.value,
                    label=item.label,
                    page=item.page,
                    bbox=NormalizedBbox(x0=0.0, y0=0.0, x1=0.0, y1=0.0),
                    source_file=item.source_file,
                    is_error=True,
                    error_detail=str(exc),
                )
                normalized_items.append(err_item)

        return normalized_items
    finally:
        doc.close()
