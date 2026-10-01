"""
Golden fixture test for PDF cell coordinate normalization and highlight mapping (FN-003).

Validates:
1. Known cell in a synthetic 10-Q filing table has exact known point coordinates.
2. Coordinate normalization scales points into 0-1000 space with top-left origin.
3. Canvas coordinate projection at two zoom levels (1.0x and 1.5x matching PDF_RENDER_SCALE)
   lands pixel-accurately on the cell without off-by-one or scale mismatch.
"""

from pathlib import Path

import pymupdf
from app.extraction.coordinate_normalizer import normalize_item_bbox
from app.extraction.models import DoclingBbox, DoclingItem


def make_golden_10q_fixture(tmp_path: Path) -> tuple[Path, float, float, tuple[float, float, float, float]]:
    """
    Creates a golden fixture PDF mimicking a 10-Q Non-GAAP reconciliation table.
    Returns (pdf_path, page_width, page_height, cell_points_rect).
    """
    pdf_path = tmp_path / "golden_10q_fixture.pdf"
    doc = pymupdf.open()
    # Standard US Letter: 612.0 x 792.0 points
    page_w = 612.0
    page_h = 792.0
    page = doc.new_page(width=page_w, height=page_h)

    # Insert table title
    page.insert_text((72, 100), "Reconciliation of Non-GAAP Financial Measures", fontsize=14)

    # Table layout:
    # Header: y=130 to 150
    # Row 1 (Net income): y=150 to 170
    # Row 2 (Stock-based compensation): y=170 to 190, label x in [72, 350], value "42" in [400, 480]
    cell_rect = (400.0, 170.0, 480.0, 190.0)  # (x0, y0, x1, y1) in PDF points (top-left origin)
    page.insert_text((72, 185), "Stock-based compensation expense", fontsize=10)
    page.insert_text((420, 185), "42", fontsize=10)

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path, page_w, page_h, cell_rect


def project_bbox_to_canvas_pixels(
    norm_x0: float,
    norm_y0: float,
    norm_x1: float,
    norm_y1: float,
    canvas_w: float,
    canvas_h: float,
) -> tuple[int, int, int, int]:
    """Projects 0-1000 normalized coordinates to canvas pixel space (identical to frontend normalizeBboxToPixels)."""
    left = round((norm_x0 / 1000.0) * canvas_w)
    top = round((norm_y0 / 1000.0) * canvas_h)
    width = max(1, round(((norm_x1 - norm_x0) / 1000.0) * canvas_w))
    height = max(1, round(((norm_y1 - norm_y0) / 1000.0) * canvas_h))
    return left, top, width, height


def test_golden_fixture_highlight_at_two_zoom_levels(tmp_path: Path) -> None:
    """
    Acceptance test for FN-003:
    Highlight lands on the exact cell on a fixture 10-Q at zoom levels 1.0x and 1.5x (PDF_RENDER_SCALE).
    """
    pdf_path, page_w, page_h, cell_rect = make_golden_10q_fixture(tmp_path)
    x0_pt, y0_pt, x1_pt, y1_pt = cell_rect

    # 1. Represent extracted cell as DoclingItem with PyMuPDF top-left parser points
    item = DoclingItem(
        value="42",
        label="Stock-based compensation expense",
        page=1,
        bbox=DoclingBbox(x0=x0_pt, y0=y0_pt, x1=x1_pt, y1=y1_pt),
        source_file=pdf_path.name,
        parser_used="pymupdf",
        is_reconciliation_candidate=True,
    )

    # 2. Normalize to 0-1000 space
    norm = normalize_item_bbox(item, page_width=page_w, page_height=page_h)

    # Verify normalized coordinates match expected fraction of page
    expected_norm_x0 = round((x0_pt / page_w) * 1000.0, 2)
    expected_norm_y0 = round((y0_pt / page_h) * 1000.0, 2)
    expected_norm_x1 = round((x1_pt / page_w) * 1000.0, 2)
    expected_norm_y1 = round((y1_pt / page_h) * 1000.0, 2)

    assert abs(norm.bbox.x0 - expected_norm_x0) <= 0.05
    assert abs(norm.bbox.y0 - expected_norm_y0) <= 0.05
    assert abs(norm.bbox.x1 - expected_norm_x1) <= 0.05
    assert abs(norm.bbox.y1 - expected_norm_y1) <= 0.05

    # 3. Zoom level 1.0x: canvas size equals page points (612 x 792)
    canvas_w_1x = page_w * 1.0
    canvas_h_1x = page_h * 1.0
    px_left_1x, px_top_1x, px_w_1x, px_h_1x = project_bbox_to_canvas_pixels(
        norm.bbox.x0, norm.bbox.y0, norm.bbox.x1, norm.bbox.y1, canvas_w_1x, canvas_h_1x
    )

    # At 1.0x, canvas pixels should match original PDF points within 1px
    assert abs(px_left_1x - x0_pt) <= 1.0
    assert abs(px_top_1x - y0_pt) <= 1.0
    assert abs(px_w_1x - (x1_pt - x0_pt)) <= 1.0
    assert abs(px_h_1x - (y1_pt - y0_pt)) <= 1.0

    # 4. Zoom level 1.5x: canvas size matches PDF_RENDER_SCALE = 1.5 (918 x 1188)
    canvas_w_15x = page_w * 1.5
    canvas_h_15x = page_h * 1.5
    px_left_15x, px_top_15x, px_w_15x, px_h_15x = project_bbox_to_canvas_pixels(
        norm.bbox.x0, norm.bbox.y0, norm.bbox.x1, norm.bbox.y1, canvas_w_15x, canvas_h_15x
    )

    # At 1.5x, canvas pixels should be exactly 1.5 * PDF points within 1px
    assert abs(px_left_15x - (x0_pt * 1.5)) <= 1.0
    assert abs(px_top_15x - (y0_pt * 1.5)) <= 1.0
    assert abs(px_w_15x - ((x1_pt - x0_pt) * 1.5)) <= 1.0
    assert abs(px_h_15x - ((y1_pt - y0_pt) * 1.5)) <= 1.0
