"""
Tests for the P0-05 auto-draft tool. All tables, numbers and XBRL facts here are
synthetic fixtures; none describe a real filing.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from app.extraction.html.models import HtmlCell
from app.extraction.html.table_parser import extract_html_tables
from bs4 import BeautifulSoup
from tools.gold.draft import (
    Draft,
    PeriodColumn,
    anchor_check,
    derived_ltm,
    extract_bridge,
    merge_split_parentheses,
    parse_period,
    tolerance,
)
from tools.gold.labels import LineRole


def _table(html: str) -> Any:
    return extract_html_tables(BeautifulSoup(html, "html.parser"))[0]


def _draft(html: str, metric: str = "Adjusted EBITDA", fye: str = "1231") -> Draft:
    draft = Draft(accession="0000000000-26-000001")
    extract_bridge(_table(html), metric, draft, fye)
    return draft


HEADER = """
<tr><td></td><td colspan="2">Three Months Ended June 30,</td></tr>
<tr><td>(in millions)</td><td>2026</td><td>2025</td></tr>
"""


def test_parse_period_variants() -> None:
    assert parse_period("Three Months Ended June 30, 2026") == (3, date(2026, 6, 30))
    assert parse_period("Thirty-Nine Week Periods Ended June 27, 2026") == (
        9,
        date(2026, 6, 27),
    )
    assert parse_period("Actual QTD 1Q26", "1231") == (3, date(2026, 3, 31))
    assert parse_period("YTD Q3 2026", "1231") == (9, date(2026, 9, 30))
    # Quarter notation is not resolved for non-calendar fiscal years.
    assert parse_period("Q1 2026", "0930") == (None, None)


def test_tolerance_scales_with_line_count() -> None:
    assert tolerance(1, Decimal(1)) == 1
    assert tolerance(7, Decimal(1)) == 4
    assert tolerance(4, Decimal("0.1")) == Decimal("0.2")


def test_split_parentheses_merge() -> None:
    cells = [
        HtmlCell(row_idx=0, col_idx=0, text="Other income"),
        HtmlCell(row_idx=0, col_idx=1, text="(7"),
        HtmlCell(row_idx=0, col_idx=2, text=")"),
    ]
    merged = merge_split_parentheses(cells)
    assert [c.text for c in merged] == ["Other income", "(7)"]
    assert merged[1].numeric_value == -7.0


def test_bottom_up_bridge_with_subtotals() -> None:
    # 50 + 40 + 10 = 100 (EBITDA, running subtotal); 15 + 5 = 20 (block subtotal);
    # Adjusted EBITDA = 120.
    html = f"""<table>{HEADER}
    <tr><td>Net income</td><td>50</td><td>45</td></tr>
    <tr><td>Interest expense</td><td>40</td><td>40</td></tr>
    <tr><td>Depreciation and amortization</td><td>10</td><td>9</td></tr>
    <tr><td>EBITDA</td><td>100</td><td>94</td></tr>
    <tr><td>Adjustments:</td></tr>
    <tr><td>Restructuring</td><td>15</td><td>2</td></tr>
    <tr><td>Stock-based compensation</td><td>5</td><td>4</td></tr>
    <tr><td>Total adjustments</td><td>20</td><td>6</td></tr>
    <tr><td>Adjusted EBITDA</td><td>120</td><td>100</td></tr>
    </table>"""
    draft = _draft(html)
    assert [p.period_id for p in draft.periods] == ["3M-2026-06-30", "3M-2025-06-30"]
    roles = {ln.label: ln.role for ln in draft.lines}
    assert roles["EBITDA"] is LineRole.subtotal
    assert roles["Total adjustments"] is LineRole.subtotal
    assert roles["Restructuring"] is LineRole.adjustment
    assert all(c.passed for c in draft.sum_checks)
    assert draft.direction == 1
    assert draft.exceptions == []


def test_data_row_above_start_is_not_header() -> None:
    # A memo row above the start line (CC Q1 2026) must not leak into the
    # period labels: "Three Months Ended June 30, 2026 (22" was the bug.
    html = f"""<table>{HEADER}
    <tr><td>Income before income taxes</td><td>(22)</td><td>38</td></tr>
    <tr><td>Net income</td><td>50</td><td>45</td></tr>
    <tr><td>Interest expense</td><td>40</td><td>40</td></tr>
    <tr><td>Adjusted EBITDA</td><td>90</td><td>85</td></tr>
    </table>"""
    draft = _draft(html)
    assert [p.header for p in draft.periods] == [
        "Three Months Ended June 30, 2026",
        "Three Months Ended June 30, 2025",
    ]
    assert all(c.passed for c in draft.sum_checks)


def test_top_down_bridge_direction() -> None:
    # Items shown with income-statement signs: EBITDA = start - sum(items).
    html = f"""<table>{HEADER}
    <tr><td>Net income</td><td>50</td><td>40</td></tr>
    <tr><td>Income tax expense</td><td>(20)</td><td>(10)</td></tr>
    <tr><td>Depreciation and amortization</td><td>(30)</td><td>(25)</td></tr>
    <tr><td>Adjusted EBITDA</td><td>100</td><td>75</td></tr>
    </table>"""
    draft = _draft(html)
    assert draft.direction == -1
    assert all(c.passed for c in draft.sum_checks)
    signs = {ln.label: ln.sign for ln in draft.lines}
    assert signs["Income tax expense"] == -1


def test_single_sign_repair_is_reported_as_note() -> None:
    # The NCI line is deducted although shown positive without "Less:".
    html = f"""<table>{HEADER}
    <tr><td>Net income</td><td>50</td><td>40</td></tr>
    <tr><td>Interest expense</td><td>30</td><td>30</td></tr>
    <tr><td>Depreciation and amortization</td><td>20</td><td>15</td></tr>
    <tr><td>Net income attributable to noncontrolling interests</td><td>10</td><td>5</td></tr>
    <tr><td>Adjusted EBITDA</td><td>90</td><td>80</td></tr>
    </table>"""
    draft = _draft(html)
    assert all(c.passed for c in draft.sum_checks)
    assert len(draft.notes) == 1 and "noncontrolling" in draft.notes[0]


def test_failed_tieout_is_an_exception() -> None:
    html = f"""<table>{HEADER}
    <tr><td>Net income</td><td>50</td><td>40</td></tr>
    <tr><td>Interest expense</td><td>30</td><td>30</td></tr>
    <tr><td>Depreciation and amortization</td><td>20</td><td>15</td></tr>
    <tr><td>Adjusted EBITDA</td><td>999</td><td>85</td></tr>
    </table>"""
    draft = _draft(html)
    assert [c.passed for c in draft.sum_checks] == [False, True]
    assert any("sum tie-out failed for 3M-2026-06-30" in e for e in draft.exceptions)


def test_misaligned_headers_assigned_by_column_order() -> None:
    # Phrase cells sit left of the value columns they describe (misaligned spans).
    html = """<table>
    <tr><td></td><td>Three Months Ended March 31,</td><td>Last Twelve Months Ended March 31,</td>
        <td></td><td></td></tr>
    <tr><td></td><td></td><td>2026</td><td>2025</td><td>2026</td><td>2025</td></tr>
    <tr><td>Net income</td><td></td><td>10</td><td>9</td><td>40</td><td>35</td></tr>
    <tr><td>Interest expense</td><td></td><td>5</td><td>5</td><td>20</td><td>20</td></tr>
    <tr><td>Income tax expense</td><td></td><td>1</td><td>1</td><td>4</td><td>4</td></tr>
    <tr><td>Adjusted EBITDA</td><td></td><td>16</td><td>15</td><td>64</td><td>59</td></tr>
    </table>"""
    draft = _draft(html)
    assert [p.period_id for p in draft.periods] == [
        "3M-2026-03-31",
        "3M-2025-03-31",
        "12M-2026-03-31",
        "12M-2025-03-31",
    ]
    assert all("assigned by column order" in p.header for p in draft.periods)


FACTS: dict[str, Any] = {
    "facts": {
        "us-gaap": {
            "NetIncomeLoss": {
                "units": {
                    "USD": [
                        {
                            "start": "2026-04-01",
                            "end": "2026-06-30",
                            "val": 50_000_000,
                            "accn": "a1",
                            "filed": "2026-08-01",
                        },
                        {
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "val": 200_000_000,
                            "accn": "a2",
                            "filed": "2026-02-01",
                        },
                        {
                            "start": "2026-01-01",
                            "end": "2026-06-30",
                            "val": 90_000_000,
                            "accn": "a1",
                            "filed": "2026-08-01",
                        },
                        {
                            "start": "2025-01-01",
                            "end": "2025-06-30",
                            "val": 80_000_000,
                            "accn": "a3",
                            "filed": "2025-08-01",
                        },
                    ]
                }
            }
        }
    }
}


def _col(months: int, end: date) -> PeriodColumn:
    return PeriodColumn(span=(1, 2), header="", months=months, end_date=end)


def test_anchor_direct_match_and_mismatch() -> None:
    col = _col(3, date(2026, 6, 30))
    ok = anchor_check(FACTS, "Net income", col, Decimal(50), 1_000_000, Decimal(1))
    assert ok["status"] == "pass" and ok["concept"] == "NetIncomeLoss"
    bad = anchor_check(FACTS, "Net income", col, Decimal(52), 1_000_000, Decimal(1))
    assert bad["status"] == "mismatch" and bad["xbrl_value"] == "50"
    none = anchor_check(
        FACTS,
        "Net income",
        _col(3, date(2024, 6, 30)),
        Decimal(1),
        1_000_000,
        Decimal(1),
    )
    assert none["status"] == "unavailable"


def test_anchor_derived_ltm() -> None:
    # LTM to 2026-06-30 = FY2025 200 + YTD 90 - prior YTD 80 = 210.
    assert derived_ltm(FACTS, ["NetIncomeLoss"], date(2026, 6, 30))[0][1] == Decimal(
        210_000_000
    )
    col = _col(12, date(2026, 6, 30))
    ok = anchor_check(FACTS, "Net income", col, Decimal(210), 1_000_000, Decimal(1))
    assert ok["status"] == "pass" and "derived" in ok
    bad = anchor_check(FACTS, "Net income", col, Decimal(212), 1_000_000, Decimal(1))
    assert bad["status"] == "mismatch"
