"""
P0-01: propose the gold-set issuer shortlist, verified against EDGAR.

For each candidate ticker (primaries first, then alternates) this checks:

1. the issuer resolves to a CIK and is not a foreign filer;
2. it has Item 2.02 8-Ks whose filing index lists an HTML EX-99.1;
3. that EX-99.1 contains a table with an EBITDA-type reconciliation;
4. two such releases exist for consecutive quarters (filed 60-120 days apart).

Passing issuers are kept until 15 are found. Every candidate, passing or not, is
written to ``eval/gold/issuers.yaml`` with its reasons, accession numbers and
CIK-qualified sec.gov URLs, for the owner to approve (P0-02).

Usage (from ``backend/``, with ``SEC_USER_AGENT`` set)::

    python -m tools.gold.propose_issuers
"""

from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml
from app.extraction.bridge.patterns import (
    BRIDGE_TERMS,
    GAAP_START,
    NOT_A_TOTAL,
    RECON_TITLE,
)
from app.extraction.html.table_parser import extract_html_tables
from app.ingestion.edgar.client import EdgarClient
from app.ingestion.edgar.models import (
    EdgarClientError,
    FilingRef,
    ForeignFilerUnsupportedError,
)
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

TARGET_COUNT = 15
MIN_GAP_DAYS = 60
MAX_GAP_DAYS = 120
MAX_RELEASES_TO_SCAN = 6

# (ticker, why it is useful for the gold set). Unverified until this tool runs.
PRIMARY_CANDIDATES: list[tuple[str, str]] = [
    ("TDG", "'EBITDA As Defined'; highly levered; September fiscal year end"),
    ("CZR", "gaming; heavy leverage; large bridge"),
    ("WYNN", "property-level EBITDAR naming edge case"),
    ("HTZ", "'Adjusted Corporate EBITDA' (fleet-interest treatment)"),
    ("CAR", "peer to Hertz for definition comparison"),
    ("THC", "healthcare HY; net-income start; NCI lines"),
    ("CYH", "distressed-ish healthcare; many add-backs"),
    ("IHRT", "highly levered media; reports in thousands"),
    ("LUMN", "telecom; special items and restructuring"),
    ("CHTR", "large-cap HY; simple bridge (control case)"),
    ("CVNA", "many adjustments; fast-changing definitions"),
    ("BHC", "heavy add-backs; domestic-filer status to confirm"),
    ("CC", "chemicals HY; litigation add-backs"),
    ("RXT", "distressed tech; SBC and restructuring heavy"),
    ("FUN", "post-merger integration costs"),
]
ALTERNATE_CANDIDATES: list[tuple[str, str]] = [
    ("CCL", "cruise; crossover credit"),
    ("CLVT", "levered information services"),
    ("WOOF", "levered retail"),
    ("USFD", "food distribution; BB credit"),
    ("SIRI", "media; crossover credit"),
    ("COTY", "June fiscal year end"),
]


@dataclass
class ReleaseRef:
    """An Item 2.02 8-K from the submissions feed."""

    accession: str
    filed: date
    primary_document: str


@dataclass
class TableFinding:
    """An EBITDA-type reconciliation table found in an exhibit."""

    table_index: int
    table_title: str
    metric_label: str
    numeric_cells: int


@dataclass
class VerifiedRelease:
    accession: str
    filed: date
    exhibit: str
    url: str
    finding: TableFinding


@dataclass
class CandidateResult:
    ticker: str
    rationale: str
    role: str
    cik: str | None = None
    name: str | None = None
    fiscal_year_end: str | None = None
    status: str = "rejected"
    reasons: list[str] = field(default_factory=list)
    releases: list[VerifiedRelease] = field(default_factory=list)


def item_202_releases(submissions: dict[str, Any]) -> list[ReleaseRef]:
    """Item 2.02 8-Ks from ``filings.recent``, newest first."""
    recent = submissions.get("filings", {}).get("recent", {})
    forms: list[str] = recent.get("form", [])
    out: list[ReleaseRef] = []
    for i, form in enumerate(forms):
        items = str(recent.get("items", [""] * len(forms))[i] or "")
        if form != "8-K" or "2.02" not in items.split(","):
            continue
        out.append(
            ReleaseRef(
                accession=recent["accessionNumber"][i],
                filed=date.fromisoformat(recent["filingDate"][i]),
                primary_document=recent["primaryDocument"][i],
            )
        )
    out.sort(key=lambda r: r.filed, reverse=True)
    return out


_MONTH_DAY = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+\d{1,2}\b"
)
_YEAR = re.compile(r"\b(20\d{2})\b")
_GAAP_START = GAAP_START
_NOT_A_TOTAL = NOT_A_TOTAL
_BRIDGE_TERMS = BRIDGE_TERMS
_MIN_BRIDGE_TERMS = 2
# RECON_TITLE is the fallback when indented bridge labels are not captured as
# row headers (known table-parser gap).
_RECON_TITLE = RECON_TITLE


def _covers_recent_period(header: str, filed: date) -> bool:
    """True if the header names a period end 0-120 days before ``filed``."""
    years = {int(y) for y in _YEAR.findall(header)}
    for month_day in _MONTH_DAY.findall(header):
        for year in years:
            try:
                end = datetime.strptime(f"{month_day} {year}", "%B %d %Y").date()  # noqa: DTZ007
            except ValueError:
                continue
            if 0 <= (filed - end).days <= 120:
                return True
    return False


def find_ebitda_table(
    html: str | bytes, filed: date | None = None
) -> TableFinding | None:
    """
    The table most likely to be the EBITDA reconciliation (bridge).

    A table qualifies only if it has numeric cells, a GAAP starting line (net
    income/loss, operating income/loss, income before taxes) and, *below* it, an
    EBITDA-type total that is not a margin or per-share row, with at least two
    distinct bridge items (interest, tax, depreciation, amortization) between
    them, or a row/title that explicitly says it reconciles to EBITDA. LTM /
    trailing-twelve-month totals are skipped (not the quarterly headline). That
    excludes KPI/highlight tables that merely list net income and Adjusted
    EBITDA. Among qualifying tables, one whose header names a period ending
    0-120 days before ``filed`` (the current quarter) is preferred over
    trailing or historical tables; ties go to the most rows between start and
    total. Returns None when no table qualifies; the caller records that.
    """
    soup = BeautifulSoup(html, "lxml")
    best: tuple[tuple[bool, int], TableFinding] | None = None
    for table in extract_html_tables(soup):
        numeric = sum(1 for c in table.cells if c.numeric_value is not None)
        if numeric == 0:
            continue
        rows = sorted(table.row_headers.items())
        start_rows = [r for r, label in rows if _GAAP_START.search(label)]
        if not start_rows:
            continue
        first_start = start_rows[0]
        totals = [
            (r, label)
            for r, label in rows
            if r > first_start
            and "ebitda" in label.lower()
            and not _NOT_A_TOTAL.search(label)
        ]
        if not totals:
            continue
        total_row, total_label = totals[-1]
        between = " ".join(
            label.lower() for r, label in rows if first_start < r < total_row
        )
        titled = any(_RECON_TITLE.search(label) for _, label in rows) or bool(
            _RECON_TITLE.search(table.title)
        )
        bridge_terms = sum(term in between for term in _BRIDGE_TERMS)
        if bridge_terms < _MIN_BRIDGE_TERMS and not titled:
            continue
        span = total_row - first_start
        finding = TableFinding(
            table_index=table.index,
            table_title=table.title,
            metric_label=total_label,
            numeric_cells=numeric,
        )
        header = " ".join(c.text for c in table.cells if c.row_idx < first_start)
        key = (filed is not None and _covers_recent_period(header, filed), span)
        if best is None or key > best[0]:
            best = (key, finding)
    return best[1] if best else None


def pick_consecutive(
    releases: list[VerifiedRelease],
) -> tuple[VerifiedRelease, VerifiedRelease] | None:
    """The newest pair of verified releases filed 60-120 days apart."""
    ordered = sorted(releases, key=lambda r: r.filed, reverse=True)
    for i, newer in enumerate(ordered):
        for older in ordered[i + 1 :]:
            gap = (newer.filed - older.filed).days
            if MIN_GAP_DAYS <= gap <= MAX_GAP_DAYS:
                return newer, older
    return None


def evaluate(
    client: EdgarClient, ticker: str, rationale: str, role: str
) -> CandidateResult:
    result = CandidateResult(ticker=ticker, rationale=rationale, role=role)
    try:
        cik = client.resolve_cik(ticker)
        submissions = client.get_submissions(cik)
        client.get_filings(cik, forms=["8-K"], limit=1)  # raises for foreign filers
    except ForeignFilerUnsupportedError as exc:
        result.reasons.append(f"foreign filer: {exc}")
        return result
    except EdgarClientError as exc:
        result.reasons.append(f"EDGAR lookup failed: {exc}")
        return result

    result.cik = cik
    result.name = submissions.get("name")
    result.fiscal_year_end = submissions.get("fiscalYearEnd")

    candidates = item_202_releases(submissions)[:MAX_RELEASES_TO_SCAN]
    if not candidates:
        result.reasons.append("no Item 2.02 8-K in filings.recent")
        return result

    verified: list[VerifiedRelease] = []
    for rel in candidates:
        filing = FilingRef(
            cik=cik,
            accession=rel.accession,
            form="8-K",
            filed_at=rel.filed.isoformat(),
            primary_url=EdgarClient._archive_url(
                cik, rel.accession, rel.primary_document
            ),
            primary_document=rel.primary_document,
        )
        try:
            exhibits = client.get_filing_directory_index(filing)
        except EdgarClientError as exc:
            result.reasons.append(f"{rel.accession}: index fetch failed: {exc}")
            continue
        ex991 = [
            e
            for e in exhibits
            if e.exhibit_number == "EX-99.1"
            and e.filename.lower().endswith((".htm", ".html"))
        ]
        if not ex991:
            types = sorted({e.exhibit_number for e in exhibits}) or ["none"]
            result.reasons.append(
                f"{rel.accession}: no HTML EX-99.1 (exhibits: {', '.join(types)})"
            )
            continue
        exhibit = ex991[0]
        try:
            doc = client.get_document(rel.accession, exhibit.filename, cik=cik)
        except EdgarClientError as exc:
            result.reasons.append(f"{rel.accession}: exhibit fetch failed: {exc}")
            continue
        finding = find_ebitda_table(doc.content, rel.filed)
        if finding is None:
            result.reasons.append(f"{rel.accession}: no EBITDA table in EX-99.1")
            continue
        verified.append(
            VerifiedRelease(
                accession=rel.accession,
                filed=rel.filed,
                exhibit=exhibit.filename,
                url=doc.url,
                finding=finding,
            )
        )

    pair = pick_consecutive(verified)
    if pair is None:
        result.reasons.append(
            f"no two verified releases {MIN_GAP_DAYS}-{MAX_GAP_DAYS} days apart "
            f"({len(verified)} verified)"
        )
        return result
    result.status = "pass"
    result.releases = list(pair)
    return result


def to_yaml_dict(results: list[CandidateResult]) -> dict[str, Any]:
    def release(r: VerifiedRelease) -> dict[str, Any]:
        return {
            "accession": r.accession,
            "filed": r.filed.isoformat(),
            "exhibit": r.exhibit,
            "url": r.url,
            "table_index": r.finding.table_index,
            "table_title": r.finding.table_title,
            "metric_label": r.finding.metric_label,
        }

    def entry(c: CandidateResult) -> dict[str, Any]:
        return {
            "ticker": c.ticker,
            "name": c.name,
            "cik": c.cik,
            "fiscal_year_end": c.fiscal_year_end,
            "role": c.role,
            "rationale": c.rationale,
            "status": c.status,
            "releases": [release(r) for r in c.releases],
            "reasons": c.reasons,
        }

    selected = [c for c in results if c.status == "pass"][:TARGET_COUNT]
    return {
        "ticket": "P0-01",
        "generated": datetime.now(UTC).date().isoformat(),
        "approved_by": None,  # P0-02: the owner fills this in after review
        "selection_rules": {
            "item": "8-K Item 2.02 with an HTML EX-99.1",
            "table": "EX-99.1 contains a table with EBITDA in its title or row labels",
            "quarters": f"two releases filed {MIN_GAP_DAYS}-{MAX_GAP_DAYS} days apart",
        },
        "selected": [entry(c) for c in selected],
        "not_selected": [entry(c) for c in results if c not in selected],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "eval" / "gold" / "issuers.yaml",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    client = EdgarClient()
    results: list[CandidateResult] = []
    queue = [(t, r, "primary") for t, r in PRIMARY_CANDIDATES] + [
        (t, r, "alternate") for t, r in ALTERNATE_CANDIDATES
    ]
    for ticker, rationale, role in queue:
        if role == "alternate" and (
            sum(1 for c in results if c.status == "pass") >= TARGET_COUNT
        ):
            break
        res = evaluate(client, ticker, rationale, role)
        print(f"{ticker:6} {res.status:8} {'; '.join(res.reasons)[:150]}")
        results.append(res)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        yaml.safe_dump(to_yaml_dict(results), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
