"""
Unit tests for 8-K Item 2.02 / EX-99.1 earnings release detection and extraction.
"""

from app.ingestion.edgar.models import FilingExhibit, FilingRef
from app.ingestion.exhibit_99.detector import (
    classify_exhibit_format,
    detect_earnings_release_exhibit,
    is_guidance_text,
    is_item_2_02_text,
)
from app.ingestion.exhibit_99.extractor import Exhibit99Extractor
from app.ingestion.exhibit_99.models import ExhibitFormat

SAMPLE_8K_EX99_HTML = """
<html>
<body>
    <h1>Q3 2024 Press Release</h1>
    <p>Non-GAAP Adjusted EBITDA Reconciliation</p>
    <table>
        <tr><th>Metric</th><th>Three Months Ended Sep 30, 2024</th></tr>
        <tr><td>Net Income</td><td>26,301</td></tr>
        <tr><td>Depreciation & Amortization</td><td>3,450</td></tr>
        <tr><td>Stock-based compensation</td><td>5,120</td></tr>
        <tr><td>Restructuring</td><td>150</td></tr>
        <tr><td>Adjusted EBITDA</td><td>35,021</td></tr>
    </table>

    <p>Full Year 2024 Outlook Guidance Reconciliation</p>
    <table>
        <tr><th>Metric</th><th>FY 2024 Guidance</th></tr>
        <tr><td>Projected Net Income</td><td>100,000</td></tr>
        <tr><td>Projected Adjusted EBITDA</td><td>140,000</td></tr>
    </table>
</body>
</html>
"""


def test_item_2_02_and_ex99_detection() -> None:
    # 8-K text with Item 2.02
    text = "Item 2.02 Results of Operations and Financial Condition. On October 29, 2024, Alphabet released..."
    assert is_item_2_02_text(text) is True
    assert is_item_2_02_text("Item 5.02 Departure of Directors") is False

    # FilingRef with EX-99.1
    filing = FilingRef(
        cik="0001652044",
        accession="0001652044-24-000005",
        form="8-K",
        filed_at="2024-10-29",
        primary_document="goog-8k.htm",
        primary_url="https://sec.gov/...",
        exhibits=[
            FilingExhibit(
                exhibit_number="EX-99.1",
                filename="goog-ex991.htm",
                description="Earnings Release Q3 2024",
                url="https://sec.gov/goog-ex991.htm",
            )
        ],
    )

    metadata = detect_earnings_release_exhibit(filing, raw_8k_content=text)
    assert metadata is not None
    assert metadata.has_item_2_02 is True
    assert metadata.exhibit_number == "EX-99.1"
    assert metadata.exhibit_filename == "goog-ex991.htm"
    assert metadata.format == ExhibitFormat.HTML


def test_classify_exhibit_format() -> None:
    assert classify_exhibit_format("press_release.htm") == ExhibitFormat.HTML
    assert classify_exhibit_format("release.html") == ExhibitFormat.HTML
    assert classify_exhibit_format("deck.pdf") == ExhibitFormat.PDF
    assert classify_exhibit_format("chart.png") == ExhibitFormat.IMAGE


def test_guidance_text_detection() -> None:
    assert is_guidance_text("Full Year 2024 Financial Outlook") is True
    assert is_guidance_text("Forward-Looking Non-GAAP Guidance") is True
    assert is_guidance_text("Three Months Ended September 30, 2024") is False


def test_exhibit_99_extractor_html() -> None:
    extractor = Exhibit99Extractor()
    records = extractor.extract_from_content(
        content=SAMPLE_8K_EX99_HTML,
        filename="goog-ex991.htm",
        accession="0001652044-24-000005",
    )

    assert len(records) > 0
    # Should contain items from historical table
    historical_labels = [
        r.label
        for r in records
        if "Outlook" not in r.label and "Guidance" not in r.label
    ]
    assert any("Adjusted EBITDA" in l for l in historical_labels)

    # Should contain tagged guidance records
    guidance_labels = [
        r.label for r in records if "Guidance" in r.label or "Outlook" in r.label
    ]
    assert len(guidance_labels) > 0
