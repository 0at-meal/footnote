"""
AUD-002 golden test: REAL Docling parse + coordinate normalisation of a SYNTHETIC two-table PDF.
Every item's 0-1000 box must contain the location of its own value text, found independently
by PyMuPDF's text search. Before the fix every Docling box was mirrored vertically.

(A golden fixture cut from a public filing is blocked until SEC_USER_AGENT is configured; see
docs/audit/FIX_PROGRESS.md.)
"""

from pathlib import Path

import pymupdf
import pytest
from app.extraction.coordinate_normalizer import normalize_coordinates
from app.extraction.docling_parser import parse_pdf_with_report

from tests.fixtures.synthetic.pdfs import (
    SYNTHETIC_BALANCE_SHEET,
    SYNTHETIC_EBITDA_BRIDGE,
    write_synthetic_pdf,
)


@pytest.fixture(scope="module")
def golden(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, list]:  # type: ignore[type-arg]
    pdf = write_synthetic_pdf(
        tmp_path_factory.mktemp("golden") / "synthetic_two_page.pdf",
        [SYNTHETIC_BALANCE_SHEET, SYNTHETIC_EBITDA_BRIDGE],
    )
    items, report = parse_pdf_with_report(pdf, pdf.name, target_metric="Adjusted EBITDA")
    assert report.parser_used == "docling"
    return pdf, normalize_coordinates(pdf, items)


def test_docling_boxes_contain_their_value_text(golden: tuple[Path, list]) -> None:  # type: ignore[type-arg]
    pdf, normalized = golden
    assert len(normalized) == 24
    doc = pymupdf.open(str(pdf))
    misses = []
    for item in normalized:
        page = doc[item.page - 1]
        w, h = page.rect.width, page.rect.height
        centres = [((r.x0 + r.x1) / 2 / w * 1000, (r.y0 + r.y1) / 2 / h * 1000) for r in page.search_for(item.value)]
        assert centres, item.value
        b = item.bbox
        if not any(b.x0 - 5 <= cx <= b.x1 + 5 and b.y0 - 5 <= cy <= b.y1 + 5 for cx, cy in centres):
            misses.append((item.page, item.value, round(b.y0), round(b.y1), [round(c[1]) for c in centres]))
    doc.close()
    assert misses == []


def test_docling_rows_keep_document_order(golden: tuple[Path, list]) -> None:  # type: ignore[type-arg]
    """Rows lower on the page must have larger y (top-left screen space)."""
    _pdf, normalized = golden
    first_page = [i for i in normalized if i.page == 1 and i.label.endswith("December 31, 2024")]
    labels = [i.label.split(" / ")[0] for i in sorted(first_page, key=lambda i: i.bbox.y0)]
    assert labels[0] == "Cash and cash equivalents"
    assert labels[-1] == "Total assets"
