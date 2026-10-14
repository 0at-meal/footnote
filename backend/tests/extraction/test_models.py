"""
ExtractedRecord provenance rules: a record without provenance is rejected,
never given fabricated provenance (page 1, whole-page box, "unknown.pdf").
"""

import pytest
from app.extraction.locator import HtmlLocator, PdfLocator
from app.extraction.models import ExtractedRecord
from pydantic import ValidationError

BOX = {"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 220.0}
BASE = {"value": "1,000", "label": "Synthetic row"}


def test_record_without_any_provenance_is_rejected() -> None:
    with pytest.raises(ValidationError, match="provenance"):
        ExtractedRecord(**BASE)


def test_partial_legacy_provenance_is_rejected() -> None:
    with pytest.raises(ValidationError, match="provenance"):
        ExtractedRecord(**BASE, page=3, bbox=BOX)
    with pytest.raises(ValidationError, match="provenance"):
        ExtractedRecord(**BASE, page=3, source_file="synthetic.pdf")


def test_explicit_legacy_fields_build_the_pdf_locator() -> None:
    rec = ExtractedRecord(**BASE, page=3, bbox=BOX, source_file="synthetic.pdf")
    assert rec.locator == PdfLocator(page=3, bbox=BOX, source_file="synthetic.pdf")


def test_locator_alone_is_enough() -> None:
    rec = ExtractedRecord(
        **BASE,
        locator=HtmlLocator(
            accession="0000000000-26-000001",
            document="synthetic.htm",
            element_path="/html/body/table[1]/tr[1]/td[2]",
        ),
    )
    assert rec.locator is not None and rec.locator.type == "html"


def test_invalid_locator_is_not_swallowed() -> None:
    with pytest.raises(ValidationError):
        ExtractedRecord(**BASE, page=0, bbox=BOX, source_file="synthetic.pdf")
