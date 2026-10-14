"""
Tests for the P0-01 issuer-shortlist tool. All HTML and submissions data here
are synthetic fixtures with zero CIKs; they do not describe real filings.
"""

from datetime import date

from tools.gold.propose_issuers import (
    ReleaseRef,
    TableFinding,
    VerifiedRelease,
    find_ebitda_table,
    item_202_releases,
    pick_consecutive,
)

HIGHLIGHTS_AND_BRIDGE = """
<html><body>
<table>
  <tr><td>Highlights</td><td>Q2</td></tr>
  <tr><td>Revenue</td><td>1,000</td></tr>
  <tr><td>Adjusted EBITDA</td><td>200</td></tr>
  <tr><td>Adjusted EBITDA margin</td><td>20%</td></tr>
</table>
<table>
  <tr><td>Reconciliation</td><td>Q2</td></tr>
  <tr><td>Net income (loss)</td><td>50</td></tr>
  <tr><td>Interest expense</td><td>40</td></tr>
  <tr><td>Depreciation and amortization</td><td>60</td></tr>
  <tr><td>EBITDA</td><td>150</td></tr>
  <tr><td>Restructuring</td><td>50</td></tr>
  <tr><td>Adjusted EBITDA</td><td>200</td></tr>
  <tr><td>Adjusted EBITDA margin</td><td>20%</td></tr>
</table>
</body></html>
"""


def test_find_ebitda_table_prefers_bridge_over_highlights() -> None:
    finding = find_ebitda_table(HIGHLIGHTS_AND_BRIDGE)
    assert finding is not None
    assert finding.table_index == 1
    assert finding.metric_label == "Adjusted EBITDA"


def test_find_ebitda_table_requires_gaap_start() -> None:
    html = """<table><tr><td>Segment</td><td>Q2</td></tr>
    <tr><td>Segment Adjusted EBITDA</td><td>10</td></tr></table>"""
    assert find_ebitda_table(html) is None


def test_find_ebitda_table_rejects_kpi_highlights() -> None:
    # Shape of a KPI table seen in a real release: net income and Adjusted EBITDA
    # are listed, but nothing is added back between them.
    html = """<table><tr><td>Consolidated</td><td>Q2</td></tr>
    <tr><td>Total revenues</td><td>2,000</td></tr>
    <tr><td>Net income (loss)</td><td>-10</td></tr>
    <tr><td>Adjusted Corporate EBITDA</td><td>150</td></tr>
    <tr><td>Depreciation Per Unit Per Month</td><td>300</td></tr>
    <tr><td>Adjusted EBITDA</td><td>90</td></tr></table>"""
    assert find_ebitda_table(html) is None


def test_find_ebitda_table_accepts_titled_reconciliation() -> None:
    # Indented add-back labels may not be captured as row headers; an explicit
    # "Reconciliation ... to Adjusted EBITDA" title still qualifies the table.
    html = """<table>
    <tr><td>Reconciliation of GAAP Net Income (Loss) to Adjusted EBITDA</td></tr>
    <tr><td>Net income (loss)</td><td>-5</td></tr>
    <tr><td></td><td></td><td>Interest expense</td><td>40</td></tr>
    <tr><td>Adjusted EBITDA</td><td>100</td></tr></table>"""
    finding = find_ebitda_table(html)
    assert finding is not None
    assert finding.metric_label == "Adjusted EBITDA"


def test_find_ebitda_table_skips_ltm_totals() -> None:
    html = """<table><tr><td>LTM</td><td>Q</td></tr>
    <tr><td>Net income (loss)</td><td>1</td></tr>
    <tr><td>Interest expense</td><td>1</td></tr>
    <tr><td>Income tax provision</td><td>1</td></tr>
    <tr><td>LTM Adjusted EBITDA</td><td>3</td></tr></table>"""
    assert find_ebitda_table(html) is None


def test_item_202_releases_filters_and_sorts() -> None:
    submissions = {
        "filings": {
            "recent": {
                "form": ["8-K", "10-Q", "8-K", "8-K"],
                "items": ["2.02,9.01", "", "5.02", "2.02,9.01"],
                "accessionNumber": [
                    "0000000000-26-000003",
                    "0000000000-26-000002",
                    "0000000000-26-000001",
                    "0000000000-26-000004",
                ],
                "filingDate": ["2026-05-01", "2026-05-02", "2026-06-01", "2026-08-01"],
                "primaryDocument": ["a.htm", "b.htm", "c.htm", "d.htm"],
            }
        }
    }
    releases = item_202_releases(submissions)
    assert [r.accession for r in releases] == [
        "0000000000-26-000004",
        "0000000000-26-000003",
    ]


def _verified(filed: str) -> VerifiedRelease:
    return VerifiedRelease(
        accession="0000000000-26-000001",
        filed=date.fromisoformat(filed),
        exhibit="ex991.htm",
        url="https://example.com/ex991.htm",
        finding=TableFinding(0, "t", "Adjusted EBITDA", 1),
    )


def test_pick_consecutive_skips_close_filings() -> None:
    # A preliminary-results 8-K 3 weeks before the real release is skipped.
    releases = [
        _verified("2026-08-04"),
        _verified("2026-07-14"),
        _verified("2026-05-05"),
    ]
    pair = pick_consecutive(releases)
    assert pair is not None
    assert (pair[0].filed.isoformat(), pair[1].filed.isoformat()) == (
        "2026-08-04",
        "2026-05-05",
    )


def test_pick_consecutive_none_when_no_quarterly_gap() -> None:
    assert pick_consecutive([_verified("2026-08-04")]) is None
    assert ReleaseRef  # imported for completeness of the public surface
