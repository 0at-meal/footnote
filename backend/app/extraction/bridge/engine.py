"""
Headline-bridge selection for a whole earnings release (P2-04).

``extract_headline_bridge`` runs the single-table engine (``core``) on every
table that has an EBITDA-labelled row and a GAAP starting line above it, then
ranks the candidates. The ranking uses only properties of the bridge itself:

1. every period column ties out (sum tie-out passes in all periods);
2. the table has a three-month column ending 0-120 days before the filing date
   (the quarter being reported, not a trailing or outlook table);
3. the bridge starts from a net income line, not a segment or operating line;
4. the bridge with more lines (consolidated over a segment excerpt);
5. the earlier table (releases put the headline reconciliation first).

The result always carries a status. ``not_found`` has a reason; ``exceptions``
lists every check that did not pass. Nothing is defaulted to look clean.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from app.extraction.bridge.core import (
    Draft,
    build_rows,
    detect_scale,
    extract_bridge,
    run_anchor,
)
from app.extraction.bridge.patterns import GAAP_START, NOT_A_TOTAL
from app.extraction.html.models import HtmlTable
from app.extraction.html.table_parser import extract_html_tables
from bs4 import BeautifulSoup

# EBITDA-labelled rows that name a component of the bridge, not its total.
_NOT_HEADLINE = re.compile(
    r"adjustments? (?:to|in)\b|special items impacting|^\s*(?:less|plus)\b"
    r"|\bper\b|same[- ](?:facility|store)|\bsegments?\b",
    re.IGNORECASE,
)
_NET_START = re.compile(r"^\s*(?:gaap\s+)?net\b", re.IGNORECASE)
# Columns that hold estimates or ranges, not reported results.
_ESTIMATE = re.compile(
    r"\b(?:estimated?|outlook|guidance|forecast|expected|low|high|range)\b",
    re.IGNORECASE,
)
_CURRENT_QUARTER_DAYS = (0, 120)

Status = Literal["ok", "exceptions", "not_found"]


@dataclass
class Candidate:
    table_index: int
    table_title: str
    draft: Draft
    ties_out: bool
    current_quarter: bool
    net_start: bool

    total_row: int = 0

    @property
    def rank(self) -> tuple[bool, bool, bool, int, int, int]:
        return (
            self.ties_out,
            self.current_quarter,
            self.net_start,
            len(self.draft.lines),
            -self.table_index,
            self.total_row,
        )

    def summary(self) -> dict[str, Any]:
        total = next(
            (ln.label for ln in self.draft.lines if ln.role.value == "total"), None
        )
        return {
            "table_index": self.table_index,
            "ties_out": self.ties_out,
            "current_quarter": self.current_quarter,
            "net_start": self.net_start,
            "lines": len(self.draft.lines),
            "periods": len(self.draft.periods),
            "total_label": total,
        }


@dataclass
class HeadlineBridge:
    status: Status
    reason: str | None = None
    table_index: int | None = None
    table_title: str = ""
    table_xpath: str = ""
    draft: Draft | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)

    @property
    def exceptions(self) -> list[str]:
        return self.draft.exceptions if self.draft else []


def headline_rows(table: HtmlTable) -> list[tuple[int, str]]:
    """Rows that can be the bridge total: EBITDA-labelled, not a ratio or part."""
    return [
        (r.idx, r.label)
        for r in build_rows(table)
        if r.value_cells
        and r.label
        and "ebitda" in r.label.lower()
        and not NOT_A_TOTAL.search(r.label)
        and not _NOT_HEADLINE.search(r.label)
    ]


def headline_label(table: HtmlTable) -> str | None:
    """The last candidate total of a table (the usual layout)."""
    rows = headline_rows(table)
    return rows[-1][1] if rows else None


def _candidate(
    table: HtmlTable,
    total_idx: int,
    label: str,
    fiscal_year_end: str,
    filed: date | None,
) -> Candidate | None:
    rows = [r for r in build_rows(table) if r.value_cells and r.label]
    if not any(r.idx < total_idx and GAAP_START.search(r.label) for r in rows):
        return None
    draft = Draft(accession="")
    extract_bridge(table, label, draft, fiscal_year_end, total_row=total_idx)
    if not draft.lines:
        return None
    checks = draft.sum_checks
    ties_out = bool(checks) and all(c.passed for c in checks)
    lo, hi = _CURRENT_QUARTER_DAYS
    current = filed is not None and any(
        p.months == 3
        and p.end_date is not None
        and lo <= (filed - p.end_date).days <= hi
        for p in draft.periods
    )
    return Candidate(
        table_index=table.index,
        table_title=table.title,
        draft=draft,
        ties_out=ties_out,
        current_quarter=current,
        net_start=bool(_NET_START.search(draft.lines[0].label)),
        total_row=total_idx,
    )


def extract_headline_bridge(
    html: bytes | str,
    *,
    accession: str,
    fiscal_year_end: str = "",
    filed: date | None = None,
    company_facts: dict[str, Any] | None = None,
) -> HeadlineBridge:
    """
    The headline EBITDA bridge of one earnings release, with its checks.

    ``company_facts`` is the SEC ``companyfacts`` JSON for the issuer; without it
    the GAAP anchor is not run and the result records that as an exception.
    """
    soup = BeautifulSoup(html, "lxml")
    tables = extract_html_tables(soup)
    candidates: list[Candidate] = []
    for table in tables:
        # Every EBITDA row is tried as the total: tables often reconcile to
        # the headline and then repeat it under a segment breakdown.
        for total_idx, label in headline_rows(table):
            cand = _candidate(table, total_idx, label, fiscal_year_end, filed)
            if cand is not None:
                candidates.append(cand)
    if not candidates:
        reason = (
            "no table has an EBITDA total with a GAAP starting line above it"
            if tables
            else "document has no tables"
        )
        return HeadlineBridge(status="not_found", reason=reason)

    best = max(candidates, key=lambda c: c.rank)
    draft = best.draft
    draft.accession = accession
    _drop_unusable_columns(draft)
    if not any(p.period_id for p in draft.periods):
        return HeadlineBridge(
            status="not_found",
            reason="headline table has only estimate, outlook or duplicate columns",
            table_index=best.table_index,
            table_title=best.table_title,
            candidates=[c.summary() for c in candidates],
        )
    tags = soup.find_all("table")
    tag = tags[best.table_index]
    preceding = " ".join(
        s.strip()
        for s in list(tag.find_all_previous(string=True, limit=40))
        if s.strip()
    )
    detect_scale(
        next(t for t in tables if t.index == best.table_index),
        draft.lines[0].row_idx,
        preceding,
        draft,
    )
    if company_facts is not None:
        run_anchor(draft, company_facts)
    else:
        draft.exceptions.append("XBRL company facts not supplied; GAAP anchor not run")
    if not best.ties_out:
        draft.exceptions.append(
            "no candidate table ties out in every period; best available kept"
        )
    if filed is not None and not best.current_quarter:
        draft.exceptions.append("selected table has no current-quarter column")
    table = next(t for t in tables if t.index == best.table_index)
    return HeadlineBridge(
        status="ok" if not draft.exceptions else "exceptions",
        table_index=best.table_index,
        table_title=best.table_title,
        table_xpath=table.xpath,
        draft=draft,
        candidates=[
            c.summary() for c in sorted(candidates, key=lambda c: c.rank, reverse=True)
        ],
    )


def _drop_unusable_columns(draft: Draft) -> None:
    """
    Estimate / outlook columns and repeated periods are not observations of a
    reported result. Their period is unset (so nothing is stored for them) and
    each one is listed as an exception.
    """
    seen: set[str] = set()
    for col in draft.periods:
        pid = col.period_id
        if pid is None:
            continue
        if _ESTIMATE.search(col.header):
            draft.exceptions.append(f"estimate column not stored: {col.header!r}")
        elif pid in seen:
            draft.exceptions.append(
                f"duplicate period column not stored: {col.header!r}"
            )
        else:
            seen.add(pid)
            continue
        col.end_date = None
