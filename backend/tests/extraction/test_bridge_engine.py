"""
Tests for headline-bridge selection (P2-04). Every table and number here is a
synthetic fixture; none describes a real filing.
"""

from datetime import date

from app.extraction.bridge.engine import extract_headline_bridge, headline_label
from app.extraction.html.table_parser import extract_html_tables
from bs4 import BeautifulSoup

HEADER = """
<tr><td></td><td colspan="2">Three Months Ended June 30,</td></tr>
<tr><td>(in millions)</td><td>2026</td><td>2025</td></tr>
"""

SEGMENT = f"""<table>{HEADER}
<tr><td>Operating income</td><td>30</td><td>20</td></tr>
<tr><td>Depreciation and amortization</td><td>10</td><td>10</td></tr>
<tr><td>Adjusted EBITDA</td><td>40</td><td>30</td></tr>
</table>"""

HEADLINE = f"""<table>{HEADER}
<tr><td>Net income</td><td>50</td><td>45</td></tr>
<tr><td>Interest expense</td><td>40</td><td>40</td></tr>
<tr><td>Income tax expense</td><td>12</td><td>10</td></tr>
<tr><td>Depreciation and amortization</td><td>10</td><td>9</td></tr>
<tr><td>Restructuring</td><td>15</td><td>2</td></tr>
<tr><td>Adjusted EBITDA</td><td>127</td><td>106</td></tr>
</table>"""

BROKEN = f"""<table>{HEADER}
<tr><td>Net income</td><td>50</td><td>45</td></tr>
<tr><td>Interest expense</td><td>40</td><td>40</td></tr>
<tr><td>Adjusted EBITDA</td><td>999</td><td>999</td></tr>
</table>"""


def _doc(*tables: str) -> str:
    return "<html><body><p>(in millions)</p>" + "".join(tables) + "</body></html>"


def test_selects_net_income_bridge_over_segment_table() -> None:
    hb = extract_headline_bridge(
        _doc(SEGMENT, HEADLINE),
        accession="0000000000-26-000001",
        fiscal_year_end="1231",
        filed=date(2026, 7, 30),
    )
    assert hb.table_index == 1
    assert hb.draft is not None
    assert hb.draft.lines[0].label == "Net income"
    assert all(c.passed for c in hb.draft.sum_checks)
    assert hb.candidates[0]["table_index"] == 1
    # No XBRL facts were supplied: that is an explicit exception, not silence.
    assert any("GAAP anchor not run" in e for e in hb.exceptions)


def test_tieout_outranks_size() -> None:
    hb = extract_headline_bridge(
        _doc(BROKEN, SEGMENT), accession="x", fiscal_year_end="1231", filed=None
    )
    assert hb.table_index == 1


def test_not_found_has_a_reason() -> None:
    hb = extract_headline_bridge(
        "<html><body><table><tr><td>Revenue</td><td>1</td></tr></table></body></html>",
        accession="x",
    )
    assert hb.status == "not_found"
    assert hb.reason


def test_estimate_columns_are_not_stored() -> None:
    est = """<table>
    <tr><td></td><td>Three Months Ended June 30, 2026 Low (Estimated)</td>
        <td>Three Months Ended June 30, 2026 High (Estimated)</td></tr>
    <tr><td>Net income</td><td>10</td><td>12</td></tr>
    <tr><td>Interest expense</td><td>5</td><td>5</td></tr>
    <tr><td>Adjusted EBITDA</td><td>15</td><td>17</td></tr>
    </table>"""
    hb = extract_headline_bridge(_doc(est), accession="x", fiscal_year_end="1231")
    assert hb.status == "not_found"
    assert "estimate" in (hb.reason or "")


def test_headline_label_skips_ratios_and_parts() -> None:
    html = f"""<table>{HEADER}
    <tr><td>Net income</td><td>1</td><td>1</td></tr>
    <tr><td>Adjusted EBITDA</td><td>5</td><td>4</td></tr>
    <tr><td>Adjusted EBITDA margin</td><td>10%</td><td>9%</td></tr>
    </table>"""
    table = extract_html_tables(BeautifulSoup(html, "lxml"))[0]
    assert headline_label(table) == "Adjusted EBITDA"


def test_line_key_ignores_invisible_characters_and_footnotes() -> None:
    from app.extraction.bridge.keys import line_key

    zw = "\u200b"
    assert line_key(f"Attributable EBITDA (4) {zw} {zw}") == "attributable ebitda"
    assert line_key("Other income (6)\N{NO-BREAK SPACE}") == "other income"


def test_line_key_bracket_footnotes_and_hyphens() -> None:
    from app.extraction.bridge.keys import line_key

    assert line_key("Normalized depreciation and amortization [2] [4] [5]") == (
        "normalized depreciation and amortization"
    )
    assert line_key("Stock-based compensation [4]") == line_key(
        "Stock based compensation"
    )
    assert line_key("Adjusted EBITDA 3") == "adjusted ebitda"
