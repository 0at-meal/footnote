"""
Unit tests for the Locator union schema and backward compatibility.

Tests:
1. PdfLocator schema, validation, and serialization.
2. HtmlLocator schema, XPath targeting, character ranges, and auto source_file.
3. Discriminated union deserialization via deserialize_locator.
4. ExtractedRecord backward compatibility (both PDF and HTML locators).
"""

from app.extraction.locator import (
    HtmlLocator,
    PdfLocator,
    deserialize_locator,
)
from app.extraction.models import ExtractedRecord


def test_pdf_locator_creation_and_bounds() -> None:
    """Verifies PdfLocator creation, validation, and serialization."""
    loc = PdfLocator(
        type="pdf",
        page=12,
        bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 400.0},
        source_file="10k_2023.pdf",
    )
    assert loc.type == "pdf"
    assert loc.page == 12
    assert loc.bbox["x0"] == 100.0
    assert loc.source_file == "10k_2023.pdf"

    serialized = loc.model_dump()
    assert serialized["type"] == "pdf"
    deserialized = deserialize_locator(serialized)
    assert isinstance(deserialized, PdfLocator)
    assert deserialized.page == 12


def test_html_locator_creation_and_auto_source_file() -> None:
    """Verifies HtmlLocator creation, XPath validation, and source_file auto-population."""
    loc = HtmlLocator(
        type="html",
        accession="0000320193-23-000106",
        document="aapl-20230930.htm",
        element_path="/html/body/div[2]/table[3]/tr[5]/td[2]",
        char_range=(140, 160),
        url="https://www.sec.gov/ix?doc=/Archives/edgar/data/0000320193/000032019323000106/aapl-20230930.htm",
    )
    assert loc.type == "html"
    assert loc.accession == "0000320193-23-000106"
    assert loc.document == "aapl-20230930.htm"
    assert loc.source_file == "aapl-20230930.htm"
    assert loc.char_range == (140, 160)

    serialized = loc.model_dump()
    assert serialized["type"] == "html"
    deserialized = deserialize_locator(serialized)
    assert isinstance(deserialized, HtmlLocator)
    assert deserialized.element_path == "/html/body/div[2]/table[3]/tr[5]/td[2]"


def test_legacy_locator_deserialization() -> None:
    """Verifies backward-compatible loading of legacy dicts missing 'type' discriminator."""
    legacy_pdf_dict = {
        "page": 5,
        "bbox": {"x0": 50.0, "y0": 60.0, "x1": 200.0, "y1": 150.0},
        "source_file": "old_filing.pdf",
    }
    loc = deserialize_locator(legacy_pdf_dict)
    assert isinstance(loc, PdfLocator)
    assert loc.page == 5
    assert loc.source_file == "old_filing.pdf"

    legacy_html_dict = {
        "accession": "0000104169-24-000020",
        "document": "wmt-20240131.htm",
        "element_path": "/html/body/table[1]/tr[2]/td[1]",
    }
    html_loc = deserialize_locator(legacy_html_dict)
    assert isinstance(html_loc, HtmlLocator)
    assert html_loc.accession == "0000104169-24-000020"


def test_extracted_record_backward_compatibility() -> None:
    """Verifies ExtractedRecord legacy constructor instantiates PdfLocator automatically."""
    rec = ExtractedRecord(
        value="1,500.00",
        label="Operating Income",
        page=8,
        bbox={"x0": 100.0, "y0": 150.0, "x1": 300.0, "y1": 200.0},
        source_file="filing.pdf",
    )
    assert rec.page == 8
    assert rec.source_file == "filing.pdf"
    assert isinstance(rec.locator, PdfLocator)
    assert rec.locator.page == 8
    assert rec.locator.bbox["x0"] == 100.0


def test_extracted_record_with_html_locator() -> None:
    """Verifies ExtractedRecord populated with HtmlLocator maintains valid legacy fallbacks."""
    html_loc = HtmlLocator(
        type="html",
        accession="0001018724-24-000008",
        document="amzn-20231231.htm",
        element_path="/html/body/table[4]/tr[2]/td[3]",
    )
    rec = ExtractedRecord(
        value="3,200.00",
        label="AWS Segment Income",
        locator=html_loc,
    )
    assert rec.locator == html_loc
    assert rec.source_file == "amzn-20231231.htm"
    assert rec.page == 1




