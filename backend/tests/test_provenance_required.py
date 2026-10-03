"""
AUD-025: a record without provenance must be rejected, never given fabricated provenance.

Before the fix, ReviewItem / FormulaInputNode with no locator and no page/bbox/source_file
validated as PdfLocator(page=1, whole page, "unknown.pdf"), and ExtractedRecord silently
dropped a locator it failed to build (`except Exception: pass`). Records that carry provenance
(an explicit locator, or explicit page + bbox + source_file as stored by older jobs) still load.
"""

import pytest
from app.extraction.locator import HtmlLocator, PdfLocator
from app.extraction.models import ConfidenceBand, ExtractedRecord
from app.formula_engine.models import FormulaInputNode
from app.review.models import ReviewItem, ReviewStatus
from pydantic import ValidationError

BOX = {"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 220.0}
REVIEW_BASE = {
    "id": "r1",
    "value": "1,000",
    "label": "Synthetic row",
    "confidence_band": ConfidenceBand.needs_review,
    "confidence_score": 0.9,
    "status": ReviewStatus.needs_review,
}
FORMULA_BASE = {"node_id": "n1", "normalized_label": "Synthetic", "value": "1,000", "label": "Synthetic row", "record_index": 0}


@pytest.mark.parametrize(
    ("model", "base"),
    [(ReviewItem, REVIEW_BASE), (FormulaInputNode, FORMULA_BASE), (ExtractedRecord, {"value": "1,000", "label": "Synthetic row"})],
)
def test_record_without_any_provenance_is_rejected(model: type, base: dict) -> None:  # type: ignore[type-arg]
    with pytest.raises(ValidationError, match="provenance"):
        model(**base)


@pytest.mark.parametrize(
    ("model", "base"),
    [(ReviewItem, REVIEW_BASE), (FormulaInputNode, FORMULA_BASE), (ExtractedRecord, {"value": "1,000", "label": "Synthetic row"})],
)
def test_partial_legacy_provenance_is_rejected(model: type, base: dict) -> None:  # type: ignore[type-arg]
    """A page with no source file (or no box) is not provenance; it must not be padded out."""
    with pytest.raises(ValidationError, match="provenance"):
        model(**base, page=3, bbox=BOX)
    with pytest.raises(ValidationError, match="provenance"):
        model(**base, page=3, source_file="synthetic.pdf")


@pytest.mark.parametrize(
    ("model", "base"),
    [(ReviewItem, REVIEW_BASE), (FormulaInputNode, FORMULA_BASE), (ExtractedRecord, {"value": "1,000", "label": "Synthetic row"})],
)
def test_explicit_legacy_fields_build_the_pdf_locator(model: type, base: dict) -> None:  # type: ignore[type-arg]
    rec = model(**base, page=3, bbox=BOX, source_file="synthetic.pdf")
    assert rec.locator == PdfLocator(page=3, bbox=BOX, source_file="synthetic.pdf")


@pytest.mark.parametrize(
    ("model", "base"),
    [(ReviewItem, REVIEW_BASE), (FormulaInputNode, FORMULA_BASE), (ExtractedRecord, {"value": "1,000", "label": "Synthetic row"})],
)
def test_locator_alone_is_enough(model: type, base: dict) -> None:  # type: ignore[type-arg]
    pdf = model(**base, locator=PdfLocator(page=2, bbox=BOX, source_file="synthetic.pdf"))
    assert (pdf.page, pdf.bbox, pdf.source_file) == (2, BOX, "synthetic.pdf")
    html = model(
        **base,
        locator=HtmlLocator(accession="0009999999-26-000001", document="synthetic.htm", element_path="/html/body/table[1]/tr[1]/td[2]"),
    )
    assert html.locator is not None and html.locator.type == "html"


def test_extracted_record_does_not_swallow_an_invalid_locator() -> None:
    """The old validator caught the PdfLocator error and left locator=None (I3)."""
    with pytest.raises(ValidationError):
        ExtractedRecord(value="1,000", label="Synthetic row", page=0, bbox=BOX, source_file="synthetic.pdf")
