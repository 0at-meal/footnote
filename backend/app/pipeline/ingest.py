"""
Ingest pipeline (P1-09): EDGAR earnings releases -> headline bridge -> store.

For every issuer in the universe it reads the EDGAR submissions feed, takes the
Item 2.02 8-Ks filed within the history window, finds each one's EX-99.1
press release, extracts the headline EBITDA bridge with its sum tie-out and
GAAP anchor (XBRL companyfacts), and stores the result as append-only
observations.

Re-running is idempotent: a bridge already stored for the engine version is
skipped and nothing is written twice. Every skip and failure is recorded in
``failures`` with a stage and a reason. Nothing is retried silently or
defaulted.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.extraction.bridge.engine import HeadlineBridge, extract_headline_bridge
from app.extraction.bridge.keys import line_key
from app.extraction.locator import sec_archives_url
from app.extraction.scale_and_sign import UnitScale
from app.ingestion.edgar.client import EdgarClient
from app.ingestion.edgar.models import EdgarClientError, FilingExhibit, FilingRef
from app.store.db import (
    BridgeRow,
    CheckRow,
    FilingRow,
    IssuerRow,
    ObservationRow,
    PeriodRow,
    Store,
)

logger = logging.getLogger(__name__)

ENGINE_VERSION = "bridge-5"
_SCALE_NAMES = {
    UnitScale.UNITS: "units",
    UnitScale.THOUSANDS: "thousands",
    UnitScale.MILLIONS: "millions",
    UnitScale.BILLIONS: "billions",
}
_PRESS_RELEASE_TYPES = ("EX-99.1", "EX-99.01", "EX-99")


@dataclass(frozen=True)
class UniverseEntry:
    ticker: str
    cik: str
    sector: str = ""


@dataclass
class RunStats:
    issuers: int = 0
    filings_seen: int = 0
    bridges_written: int = 0
    bridges_skipped_existing: int = 0
    status: Counter[str] = field(default_factory=Counter)
    failures: Counter[str] = field(default_factory=Counter)

    def as_dict(self) -> dict[str, Any]:
        return {
            "issuers": self.issuers,
            "filings_seen": self.filings_seen,
            "bridges_written": self.bridges_written,
            "bridges_skipped_existing": self.bridges_skipped_existing,
            "status": dict(self.status),
            "failures_by_stage": dict(self.failures),
        }


def pick_press_release(exhibits: list[FilingExhibit]) -> FilingExhibit | None:
    """The HTML EX-99.1 (or EX-99.01 / EX-99 when no EX-99.1 exists)."""
    html = [e for e in exhibits if e.filename.lower().endswith((".htm", ".html"))]
    for kind in _PRESS_RELEASE_TYPES:
        hits = [e for e in html if e.exhibit_number.upper() == kind]
        if hits:
            return hits[0]
    return None


def bridge_row(hb: HeadlineBridge, accession: str, cik: str, exhibit: str) -> BridgeRow:
    """Convert an engine result into store rows; values stay as reported."""
    row = BridgeRow(
        accession=accession,
        engine_version=ENGINE_VERSION,
        status=hb.status,
        reason=hb.reason,
        table_index=hb.table_index,
        table_title=hb.table_title or None,
        table_xpath=hb.table_xpath or None,
        candidates=hb.candidates,
    )
    draft = hb.draft
    if draft is None:
        return row
    row.scale = _SCALE_NAMES.get(draft.scale)
    row.scale_quote = draft.scale_quote or None
    row.direction = draft.direction
    row.exceptions = list(draft.exceptions)
    row.notes = list(draft.notes)
    total = next((ln for ln in draft.lines if ln.role.value == "total"), None)
    row.metric_label = total.label if total else None
    multiplier = int(draft.scale) if draft.scale is not UnitScale.UNKNOWN else None
    row.periods = [
        PeriodRow(
            col=i,
            period_id=p.period_id,
            months=p.months,
            end_date=p.end_date.isoformat() if p.end_date else None,
            header=p.header,
        )
        for i, p in enumerate(draft.periods)
    ]
    for order, line in enumerate(draft.lines):
        url = sec_archives_url(cik, accession, exhibit, text=line.label)
        for i, period in enumerate(draft.periods):
            raw = line.raw[i] if i < len(line.raw) else None
            if period.period_id is None or raw is None:
                continue
            value = line.values[i]
            row.observations.append(
                ObservationRow(
                    row_order=order,
                    label=line.label,
                    line_key=line_key(line.label),
                    role=line.role.value,
                    sign=line.sign,
                    period_id=period.period_id,
                    value_raw=raw,
                    value=None if value is None else str(value),
                    value_usd=(
                        None
                        if value is None or multiplier is None
                        else str(value * Decimal(multiplier))
                    ),
                    xpath=line.xpaths[i] if i < len(line.xpaths) else None,
                    url=url,
                )
            )
    stored = {p.period_id for p in draft.periods if p.period_id}
    checked: set[tuple[str, str]] = set()
    for check in draft.sum_checks:
        if check.period_id not in stored or ("sum", check.period_id) in checked:
            continue
        checked.add(("sum", check.period_id))
        row.checks.append(
            CheckRow(
                kind="sum",
                period_id=check.period_id,
                status="pass" if check.passed else "fail",
                detail={
                    "expected": str(check.expected),
                    "computed": str(check.computed),
                    "tolerance": str(check.tolerance),
                    "lines_summed": check.lines_summed,
                },
            )
        )
    for anchor in draft.anchor_checks:
        pid = str(anchor.get("period_id"))
        if pid not in stored or ("anchor", pid) in checked:
            continue
        checked.add(("anchor", pid))
        row.checks.append(
            CheckRow(
                kind="anchor",
                period_id=str(anchor.get("period_id")),
                status=str(anchor["status"]),
                detail={k: v for k, v in anchor.items() if k != "status"},
            )
        )
    return row


def ingest_issuer(
    client: EdgarClient,
    store: Store,
    entry: UniverseEntry,
    run_id: int,
    stats: RunStats,
    since: date,
    max_filings: int,
) -> None:
    cik = entry.cik
    try:
        submissions = client.get_submissions(cik)
    except EdgarClientError as exc:
        store.add_failure(run_id, "submissions", str(exc), cik=cik)
        stats.failures["submissions"] += 1
        return
    fye = str(submissions.get("fiscalYearEnd") or "")
    store.upsert_issuer(
        IssuerRow(
            cik=cik,
            ticker=entry.ticker,
            name=str(submissions.get("name") or entry.ticker),
            fiscal_year_end=fye,
            sector=entry.sector,
        )
    )
    stats.issuers += 1
    try:
        filings = client.get_filings(
            cik, forms=["8-K"], items=["2.02"], limit=200, submissions=submissions
        )
    except EdgarClientError as exc:
        store.add_failure(run_id, "submissions", str(exc), cik=cik)
        stats.failures["submissions"] += 1
        return
    filings = [f for f in filings if date.fromisoformat(f.filed_at) >= since]
    filings = filings[:max_filings]
    if not filings:
        store.add_failure(
            run_id, "submissions", f"no Item 2.02 8-K filed since {since}", cik=cik
        )
        stats.failures["submissions"] += 1
        return

    facts: dict[str, Any] | None = None
    if any(not store.has_bridge(f.accession, ENGINE_VERSION) for f in filings):
        try:
            facts = client.get_company_facts(cik)
        except EdgarClientError as exc:
            store.add_failure(run_id, "facts", str(exc), cik=cik)
            stats.failures["facts"] += 1

    for filing in filings:
        stats.filings_seen += 1
        if store.has_bridge(filing.accession, ENGINE_VERSION):
            stats.bridges_skipped_existing += 1
            continue
        _ingest_filing(client, store, filing, fye, facts, run_id, stats)


def _ingest_filing(
    client: EdgarClient,
    store: Store,
    filing: FilingRef,
    fye: str,
    facts: dict[str, Any] | None,
    run_id: int,
    stats: RunStats,
) -> None:
    cik, acc = filing.cik, filing.accession
    try:
        exhibits = client.get_filing_directory_index(filing)
    except EdgarClientError as exc:
        store.add_failure(run_id, "index", str(exc), cik=cik, accession=acc)
        stats.failures["index"] += 1
        return
    exhibit = pick_press_release(exhibits)
    if exhibit is None:
        types = sorted({e.exhibit_number for e in exhibits}) or ["none"]
        reason = f"no HTML EX-99.1 press release (exhibits: {', '.join(types)})"
        store.add_filing(
            FilingRow(
                acc,
                cik,
                filing.form,
                ",".join(filing.items),
                filing.filed_at,
                None,
                None,
                None,
                None,
            ),
            run_id,
        )
        store.add_failure(run_id, "index", reason, cik=cik, accession=acc)
        stats.failures["index"] += 1
        return
    try:
        doc = client.get_document(acc, exhibit.filename, cik=cik)
    except EdgarClientError as exc:
        store.add_failure(run_id, "exhibit", str(exc), cik=cik, accession=acc)
        stats.failures["exhibit"] += 1
        return
    url = sec_archives_url(cik, acc, exhibit.filename)
    store.add_filing(
        FilingRow(
            accession=acc,
            cik=cik,
            form=filing.form,
            items=",".join(filing.items),
            filed=filing.filed_at,
            exhibit=exhibit.filename,
            url=url,
            sha256=hashlib.sha256(doc.content).hexdigest(),
            bytes=len(doc.content),
        ),
        run_id,
    )
    try:
        hb = extract_headline_bridge(
            doc.content,
            accession=acc,
            fiscal_year_end=fye,
            filed=date.fromisoformat(filing.filed_at),
            company_facts=facts,
        )
    except Exception as exc:  # recorded, never swallowed: the run continues
        logger.exception("extraction crashed for %s", acc)
        store.add_failure(
            run_id, "extract", f"{type(exc).__name__}: {exc}", cik=cik, accession=acc
        )
        stats.failures["extract"] += 1
        return
    if hb.status == "not_found":
        store.add_failure(
            run_id, "extract", hb.reason or "not found", cik=cik, accession=acc
        )
        stats.failures["extract"] += 1
    try:
        store.add_bridge(
            bridge_row(hb, acc, cik, exhibit.filename), cik, filing.filed_at, run_id
        )
    except sqlite3.Error as exc:
        store.add_failure(
            run_id, "store", f"{type(exc).__name__}: {exc}", cik=cik, accession=acc
        )
        stats.failures["store"] += 1
        return
    stats.bridges_written += 1
    stats.status[hb.status] += 1


def run_ingest(
    client: EdgarClient,
    store: Store,
    universe: list[UniverseEntry],
    quarters: int = 8,
    today: date | None = None,
    command: str = "ingest",
) -> RunStats:
    """Ingest ``quarters`` of earnings releases for each issuer (~92 days each)."""
    today = today or datetime.now(UTC).date()
    since = today - timedelta(days=92 * quarters + 30)
    run_id = store.start_run(command)
    stats = RunStats()
    for entry in universe:
        logger.info("ingesting %s (%s)", entry.ticker, entry.cik)
        ingest_issuer(
            client, store, entry, run_id, stats, since, max_filings=quarters + 4
        )
    store.finish_run(run_id, stats.as_dict())
    return stats
