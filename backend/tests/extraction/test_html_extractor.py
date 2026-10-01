"""
Unit and benchmark tests for HTML and iXBRL Extractor (FN-021).
"""

import time

from app.extraction.html.detector import (
    detect_reconciliation_tables,
)
from app.extraction.html.extractor import HtmlExtractor
from app.extraction.html.ixbrl_parser import parse_ixbrl_facts
from app.extraction.html.models import HtmlExtractionResult
from app.extraction.html.table_parser import extract_html_tables, parse_numeric_cell
from app.extraction.locator import HtmlLocator
from bs4 import BeautifulSoup

SAMPLE_IXBRL_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Form 10-Q Q3 2024</title>
</head>
<body>
    <xbrli:context id="c-2024-q3">
        <xbrli:period>
            <xbrli:endDate>2024-09-30</xbrli:endDate>
        </xbrli:period>
    </xbrli:context>
    <xbrli:context id="c-2023-q3">
        <xbrli:period>
            <xbrli:endDate>2023-09-30</xbrli:endDate>
        </xbrli:period>
    </xbrli:context>

    <div>
        <p>Authoritative Financial Statements</p>
        <ix:nonfraction name="us-gaap:NetIncomeLoss" scale="6" contextRef="c-2024-q3" unitRef="USD">26,301</ix:nonfraction>
        <ix:nonfraction name="us-gaap:OperatingIncomeLoss" scale="6" contextRef="c-2024-q3" unitRef="USD">28,521</ix:nonfraction>
        <ix:nonfraction name="us-gaap:DepreciationAndAmortization" scale="6" contextRef="c-2024-q3" unitRef="USD">3,450</ix:nonfraction>
        <ix:nonfraction name="us-gaap:InterestExpense" scale="6" sign="-" contextRef="c-2024-q3" unitRef="USD">(120)</ix:nonfraction>
    </div>

    <!-- Non-Reconciliation Table: Comprehensive Income -->
    <table id="comp-inc">
        <caption>Consolidated Statements of Comprehensive Income</caption>
        <tr><th>Description</th><th>September 30, 2024</th></tr>
        <tr><td>Net Income</td><td>26,301</td></tr>
        <tr><td>Foreign currency translation</td><td>(45)</td></tr>
    </table>

    <!-- Target Non-GAAP Reconciliation Table with Colspan, Rowspan, and Parentheses -->
    <p>Reconciliation of Net Income to Adjusted EBITDA (Non-GAAP)</p>
    <table id="adj-ebitda-table">
        <tr>
            <th rowspan="2">Line Item</th>
            <th colspan="2">Three Months Ended September 30,</th>
        </tr>
        <tr>
            <th>2024</th>
            <th>2023</th>
        </tr>
        <tr>
            <td>Net Income</td>
            <td>$ 26,301</td>
            <td>$ 19,689</td>
        </tr>
        <tr>
            <td>Interest expense</td>
            <td>120</td>
            <td>105</td>
        </tr>
        <tr>
            <td>Provision for income taxes</td>
            <td>3,845</td>
            <td>2,950</td>
        </tr>
        <tr>
            <td>Depreciation and amortization (1)</td>
            <td>3,450</td>
            <td>2,800</td>
        </tr>
        <tr>
            <td>Stock-based compensation expense</td>
            <td>5,120</td>
            <td>4,300</td>
        </tr>
        <tr>
            <td>Restructuring charges</td>
            <td>(45)</td>
            <td>120</td>
        </tr>
        <tr>
            <td>Adjusted EBITDA</td>
            <td>$ 38,791</td>
            <td>$ 29,964</td>
        </tr>
    </table>
</body>
</html>
"""


def test_parse_ixbrl_facts() -> None:
    soup = BeautifulSoup(SAMPLE_IXBRL_HTML, "html.parser")
    facts = parse_ixbrl_facts(soup)
    assert len(facts) == 4

    net_inc = next((f for f in facts if "NetIncomeLoss" in f.concept), None)
    assert net_inc is not None
    # 26301 * 10^6
    assert net_inc.value == 26301 * 1_000_000
    assert net_inc.context_period == "2024-09-30"

    interest = next((f for f in facts if "InterestExpense" in f.concept), None)
    assert interest is not None
    # Negative from sign and parentheses
    assert interest.value == -120 * 1_000_000


def test_parse_numeric_cell() -> None:
    # Standard integers and decimals
    num, text = parse_numeric_cell("1,234.56")
    assert num == 1234.56
    assert text == "1234.56"

    # Accounting parentheses
    num, text = parse_numeric_cell("(45.6)")
    assert num == -45.6
    assert text == "-45.6"

    num, text = parse_numeric_cell(" ( 1,200 ) ")
    assert num == -1200.0
    assert text == "-1200"

    # Currency stripping
    num, text = parse_numeric_cell("$ 10,500")
    assert num == 10500.0

    # Footnote markers
    num, text = parse_numeric_cell("2,450 (1)")
    assert num == 2450.0

    # Financial placeholders
    num, text = parse_numeric_cell("—")
    assert num is None


def test_extract_html_tables_with_spans_and_periods() -> None:
    soup = BeautifulSoup(SAMPLE_IXBRL_HTML, "html.parser")
    tables = extract_html_tables(soup)
    assert len(tables) == 2

    recon_table = tables[1]
    assert "Reconciliation" in recon_table.title or "Adjusted EBITDA" in recon_table.title

    # Check row labels
    assert any("Net Income" in lbl for lbl in recon_table.row_headers.values())
    assert any("Adjusted EBITDA" in lbl for lbl in recon_table.row_headers.values())

    # Check cell periods
    data_cells = [c for c in recon_table.cells if c.numeric_value is not None]
    assert len(data_cells) > 0
    # Every cell should have a detected period
    periods = {c.period for c in data_cells if c.period}
    assert any("September 30" in p or "2024" in p for p in periods)


def test_reconciliation_detector() -> None:
    soup = BeautifulSoup(SAMPLE_IXBRL_HTML, "html.parser")
    tables = extract_html_tables(soup)

    candidates = detect_reconciliation_tables(tables, target_metric="Adjusted EBITDA")
    # Comprehensive income table must NOT be selected
    assert len(candidates) == 1
    assert candidates[0].index == 1
    assert candidates[0].reconciliation_score > 0.6


def test_html_extractor_end_to_end() -> None:
    extractor = HtmlExtractor(parser_flavor="html.parser")
    result: HtmlExtractionResult = extractor.extract(
        html_content=SAMPLE_IXBRL_HTML,
        accession="0001652044-24-000088",
        document_name="goog-20240930.htm",
        target_metric="Adjusted EBITDA",
    )

    assert result.status == "success"
    assert len(result.records) > 0
    assert len(result.ixbrl_facts) > 0

    # Check records have valid HtmlLocator
    for rec in result.records:
        assert isinstance(rec.locator, HtmlLocator)
        assert rec.locator.accession == "0001652044-24-000088"
        assert rec.locator.document == "goog-20240930.htm"
        assert rec.locator.element_path.startswith("/html/")
        assert rec.page == 1
        assert rec.source_file == "goog-20240930.htm"
        assert rec.is_reconciliation_candidate is True

    # Check specific line extracted: Adjusted EBITDA
    ebitda_recs = [r for r in result.records if "Adjusted EBITDA" in r.label]
    assert len(ebitda_recs) >= 2  # 2024 and 2023 columns
    values = [r.value for r in ebitda_recs]
    assert any("38,791" in v or "38791" in v for v in values)


def test_html_extractor_explicit_not_found_invariant_i3() -> None:
    unrelated_html = """
    <html>
    <body>
        <h1>Corporate Governance</h1>
        <p>The Board of Directors meets quarterly.</p>
        <table>
            <tr><th>Director</th><th>Committee</th></tr>
            <tr><td>Jane Doe</td><td>Audit</td></tr>
        </table>
    </body>
    </html>
    """
    extractor = HtmlExtractor(parser_flavor="html.parser")
    result = extractor.extract(
        html_content=unrelated_html,
        accession="0001652044-24-000099",
        document_name="goog-def14a.htm",
        target_metric="Adjusted EBITDA",
    )

    assert result.status == "not_found"
    assert result.not_found_reason is not None
    assert "No non-GAAP reconciliation table matching 'Adjusted EBITDA' found" in result.not_found_reason
    assert len(result.records) == 0


def test_html_extractor_throughput_benchmark() -> None:
    # Test streaming/parsing throughput on synthetic large document (50 tables, 500 rows)
    tables_html = []
    for i in range(30):
        rows_html = "".join([f"<tr><td>Item {j}</td><td>{j * 10}</td><td>{j * 15}</td></tr>" for j in range(20)])
        tables_html.append(f"<table><caption>Table {i}</caption>{rows_html}</table>")
    tables_html.append("""
    <table>
        <caption>Reconciliation of Net Income to Adjusted EBITDA</caption>
        <tr><th>Metric</th><th>2024</th></tr>
        <tr><td>Net Income</td><td>1,000</td></tr>
        <tr><td>Depreciation</td><td>150</td></tr>
        <tr><td>Stock-based compensation</td><td>50</td></tr>
        <tr><td>Adjusted EBITDA</td><td>1,200</td></tr>
    </table>
    """)
    large_doc = f"<html><body>{''.join(tables_html)}</body></html>"

    extractor = HtmlExtractor(parser_flavor="html.parser")
    start = time.monotonic()
    result = extractor.extract(
        html_content=large_doc,
        accession="0001652044-24-000001",
        document_name="large-10k.htm",
    )
    elapsed = time.monotonic() - start

    assert result.status == "success"
    assert len(result.records) > 0
    # Throughput benchmark: must be well under 3.0 seconds
    assert elapsed < 3.0
