"""
Local observation store (P1-01, SQLite edition; ADR 0006).

The store holds public filing data only. Writes are idempotent: a filing or a
bridge already stored for the same engine version is never written twice, and
no reported value is ever updated in place. Every skip or failure of a run is
recorded in ``failures`` with its stage and reason.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
_SCHEMA = Path(__file__).with_name("schema.sql")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class IssuerRow:
    cik: str
    ticker: str
    name: str
    fiscal_year_end: str
    sector: str = ""


@dataclass(frozen=True)
class FilingRow:
    accession: str
    cik: str
    form: str
    items: str
    filed: str
    exhibit: str | None
    url: str | None
    sha256: str | None
    bytes: int | None


@dataclass(frozen=True)
class PeriodRow:
    col: int
    period_id: str | None
    months: int | None
    end_date: str | None
    header: str


@dataclass(frozen=True)
class ObservationRow:
    row_order: int
    label: str
    line_key: str
    role: str
    sign: int
    period_id: str
    value_raw: str
    value: str | None
    value_usd: str | None
    xpath: str | None
    url: str | None


@dataclass(frozen=True)
class CheckRow:
    kind: str
    period_id: str
    status: str
    detail: dict[str, Any]


@dataclass
class BridgeRow:
    accession: str
    engine_version: str
    status: str
    reason: str | None = None
    table_index: int | None = None
    table_title: str | None = None
    table_xpath: str | None = None
    metric_label: str | None = None
    scale: str | None = None
    scale_quote: str | None = None
    direction: int | None = None
    exceptions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    periods: list[PeriodRow] = field(default_factory=list)
    observations: list[ObservationRow] = field(default_factory=list)
    checks: list[CheckRow] = field(default_factory=list)


class Store:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
        row = self.conn.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
            )
            self.conn.commit()
        elif row["version"] != SCHEMA_VERSION:
            raise RuntimeError(
                f"{self.path}: schema version {row['version']} != {SCHEMA_VERSION}"
            )

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self.conn:
            yield self.conn

    # ------------------------------------------------------------ runs

    def start_run(self, command: str) -> int:
        with self.tx() as c:
            cur = c.execute(
                "INSERT INTO runs (started_at, command) VALUES (?, ?)",
                (_now(), command),
            )
        run_id = cur.lastrowid
        if run_id is None:
            raise RuntimeError("run insert returned no id")
        return run_id

    def finish_run(self, run_id: int, stats: dict[str, Any]) -> None:
        with self.tx() as c:
            c.execute(
                "UPDATE runs SET finished_at = ?, stats_json = ? WHERE run_id = ?",
                (_now(), json.dumps(stats, sort_keys=True), run_id),
            )

    def add_failure(
        self,
        run_id: int,
        stage: str,
        reason: str,
        cik: str | None = None,
        accession: str | None = None,
    ) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO failures (run_id, cik, accession, stage, reason, at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, cik, accession, stage, reason, _now()),
            )

    # ------------------------------------------------------------ writes

    def upsert_issuer(self, issuer: IssuerRow) -> None:
        """Issuer metadata is reference data, refreshed from EDGAR each run."""
        with self.tx() as c:
            c.execute(
                "INSERT INTO issuers (cik, ticker, name, fiscal_year_end, sector) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(cik) DO UPDATE SET "
                "ticker = excluded.ticker, name = excluded.name, "
                "fiscal_year_end = excluded.fiscal_year_end, sector = excluded.sector",
                (
                    issuer.cik,
                    issuer.ticker,
                    issuer.name,
                    issuer.fiscal_year_end,
                    issuer.sector,
                ),
            )

    def has_filing(self, accession: str) -> bool:
        return (
            self.conn.execute(
                "SELECT 1 FROM filings WHERE accession = ?", (accession,)
            ).fetchone()
            is not None
        )

    def add_filing(self, filing: FilingRow, run_id: int) -> bool:
        """Insert once; returns False when the filing was already stored."""
        with self.tx() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO filings (accession, cik, form, items, filed, "
                "exhibit, url, sha256, bytes, first_run) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    filing.accession,
                    filing.cik,
                    filing.form,
                    filing.items,
                    filing.filed,
                    filing.exhibit,
                    filing.url,
                    filing.sha256,
                    filing.bytes,
                    run_id,
                ),
            )
        return cur.rowcount == 1

    def has_bridge(self, accession: str, engine_version: str) -> bool:
        return (
            self.conn.execute(
                "SELECT 1 FROM bridges WHERE accession = ? AND engine_version = ?",
                (accession, engine_version),
            ).fetchone()
            is not None
        )

    def add_bridge(self, bridge: BridgeRow, cik: str, filed: str, run_id: int) -> bool:
        """Write a bridge with its periods, observations and checks atomically."""
        if self.has_bridge(bridge.accession, bridge.engine_version):
            return False
        with self.tx() as c:
            cur = c.execute(
                "INSERT INTO bridges (accession, engine_version, status, reason, "
                "table_index, table_title, table_xpath, metric_label, scale, "
                "scale_quote, direction, exceptions, notes, candidates, run_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    bridge.accession,
                    bridge.engine_version,
                    bridge.status,
                    bridge.reason,
                    bridge.table_index,
                    bridge.table_title,
                    bridge.table_xpath,
                    bridge.metric_label,
                    bridge.scale,
                    bridge.scale_quote,
                    bridge.direction,
                    json.dumps(bridge.exceptions),
                    json.dumps(bridge.notes),
                    json.dumps(bridge.candidates),
                    run_id,
                ),
            )
            bridge_id = cur.lastrowid
            c.executemany(
                "INSERT INTO bridge_periods VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (bridge_id, p.col, p.period_id, p.months, p.end_date, p.header)
                    for p in bridge.periods
                ],
            )
            c.executemany(
                "INSERT INTO observations VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        bridge_id,
                        cik,
                        bridge.accession,
                        filed,
                        o.row_order,
                        o.label,
                        o.line_key,
                        o.role,
                        o.sign,
                        o.period_id,
                        o.value_raw,
                        o.value,
                        bridge.scale,
                        o.value_usd,
                        o.xpath,
                        o.url,
                    )
                    for o in bridge.observations
                ],
            )
            c.executemany(
                "INSERT INTO checks VALUES (?, ?, ?, ?, ?)",
                [
                    (bridge_id, k.kind, k.period_id, k.status, json.dumps(k.detail))
                    for k in bridge.checks
                ],
            )
        return True

    def set_label(
        self,
        cik: str,
        line_key: str,
        code: str,
        source: str,
        decided_by: str,
        components: Sequence[str] = (),
        flags: Sequence[str] = (),
        overwrite_rule: bool = True,
    ) -> None:
        """
        Record a category decision. A human decision is never replaced by a rule;
        a rule suggestion is replaced by a later human decision.
        """
        existing = self.conn.execute(
            "SELECT source FROM label_memory WHERE cik = ? AND line_key = ?",
            (cik, line_key),
        ).fetchone()
        if existing is not None and (
            existing["source"] == "human" and source != "human" or not overwrite_rule
        ):
            return
        with self.tx() as c:
            c.execute(
                "INSERT INTO label_memory VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(cik, line_key) DO UPDATE SET code = excluded.code, "
                "components = excluded.components, flags = excluded.flags, "
                "source = excluded.source, decided_by = excluded.decided_by, "
                "decided_on = excluded.decided_on",
                (
                    cik,
                    line_key,
                    code,
                    json.dumps(list(components)),
                    json.dumps(list(flags)),
                    source,
                    decided_by,
                    _now()[:10],
                ),
            )

    # ------------------------------------------------------------ reads

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return list(self.conn.execute(sql, params).fetchall())
