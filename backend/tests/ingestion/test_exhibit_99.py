"""
Unit tests for 8-K EX-99.1 Earnings Release Support (FN-022).
"""


from app.extraction.locator import HtmlLocator
from app.extraction.models import ExtractedRecord
from app.ingestion.edgar.models import FilingExhibit, FilingRef
from app.ingestion.exhibit_99.detector import (
    classify_exhibit_format,
    detect_earnings_release_exhibit,
    is_guidance_text,
    is_item_2_02_text,
)
from app.ingestion.exhibit_99.differ import diff_bridges, merge_dedupe_bridges
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
    historical_labels = [r.label for r in records if "Outlook" not in r.label and "Guidance" not in r.label]
    assert any("Adjusted EBITDA" in l for l in historical_labels)

    # Should contain tagged guidance records
    guidance_labels = [r.label for r in records if "Guidance" in r.label or "Outlook" in r.label]
    assert len(guidance_labels) > 0


def test_diff_bridges_and_latest_filed_wins() -> None:
    loc_8k = HtmlLocator(
        accession="0001652044-24-000005",
        document="goog-ex991.htm",
        element_path="/html/body/table[1]/tr[5]/td[2]",
    )
    loc_10q = HtmlLocator(
        accession="0001652044-24-000088",
        document="goog-10q.htm",
        element_path="/html/body/table[2]/tr[5]/td[2]",
    )

    # 8-K records
    rec_8k_net_inc = ExtractedRecord(
        value="26,301",
        label="Reconciliation > Net Income",
        page=1,
        bbox={"x0": 0.0, "y0": 0.0, "x1": 1000.0, "y1": 1000.0},
        source_file="goog-ex991.htm",
        locator=loc_8k,
    )
    rec_8k_restruct = ExtractedRecord(
        value="150",
        label="Reconciliation > Restructuring charges",
        page=1,
        bbox={"x0": 0.0, "y0": 0.0, "x1": 1000.0, "y1": 1000.0},
        source_file="goog-ex991.htm",
        locator=loc_8k,
    )
    rec_8k_ebitda = ExtractedRecord(
        value="35,021",
        label="Reconciliation > Adjusted EBITDA",
        page=1,
        bbox={"x0": 0.0, "y0": 0.0, "x1": 1000.0, "y1": 1000.0},
        source_file="goog-ex991.htm",
        locator=loc_8k,
    )
    release_records = [rec_8k_net_inc, rec_8k_restruct, rec_8k_ebitda]

    # Subsequent 10-Q records with a slight restatement on restructuring (120 instead of 150)
    rec_10q_net_inc = ExtractedRecord(
        value="26,301",
        label="10-Q > Net Income",
        page=1,
        bbox={"x0": 0.0, "y0": 0.0, "x1": 1000.0, "y1": 1000.0},
        source_file="goog-10q.htm",
        locator=loc_10q,
    )
    rec_10q_restruct = ExtractedRecord(
        value="120",  # Discrepancy!
        label="10-Q > Restructuring charges",
        page=1,
        bbox={"x0": 0.0, "y0": 0.0, "x1": 1000.0, "y1": 1000.0},
        source_file="goog-10q.htm",
        locator=loc_10q,
    )
    rec_10q_ebitda = ExtractedRecord(
        value="34,991",  # Adjusted accordingly
        label="10-Q > Adjusted EBITDA",
        page=1,
        bbox={"x0": 0.0, "y0": 0.0, "x1": 1000.0, "y1": 1000.0},
        source_file="goog-10q.htm",
        locator=loc_10q,
    )
    filing_records = [rec_10q_net_inc, rec_10q_restruct, rec_10q_ebitda]

    # Run diff
    diff_report = diff_bridges(
        release_records=release_records,
        filing_records=filing_records,
        cik="0001652044",
        period="2024-09-30",
        release_accession="0001652044-24-000005",
        filing_accession="0001652044-24-000088",
    )

    assert diff_report.has_discrepancies is True
    assert len(diff_report.items) == 3

    # Check match on Net Income
    net_inc_diff = next(i for i in diff_report.items if "netincome" in i.metric_name.lower().replace(" ", ""))
    assert net_inc_diff.is_match is True
    assert net_inc_diff.status == "match"
    # Preserves dual provenance
    assert net_inc_diff.release_locator == loc_8k
    assert net_inc_diff.filing_locator == loc_10q

    # Check discrepancy on Restructuring
    restruct_diff = next(i for i in diff_report.items if "restructuring" in i.metric_name.lower())
    assert restruct_diff.is_match is False
    assert restruct_diff.status == "discrepancy"
    assert restruct_diff.release_value == 150.0
    assert restruct_diff.filing_value == 120.0
    assert restruct_diff.difference == -30.0

    # Run merge_dedupe_bridges: 10-Q should be canonical
    res = merge_dedupe_bridges(
        release_records=release_records,
        filing_records=filing_records,
        cik="0001652044",
        period="2024-09-30",
        release_accession="0001652044-24-000005",
        filing_accession="0001652044-24-000088",
    )

    assert len(res.canonical_records) == 3
    # Authoritative canonical record has 10-Q locator and value
    canonical_restruct = next(r for r in res.canonical_records if "restructuring" in r.label.lower())
    assert canonical_restruct.value == "120"
    assert canonical_restruct.locator == loc_10q
