"""
Point-in-time views over the observation store.

- ``quarter_series``: one verified bridge per fiscal quarter (3-month column),
  using the *latest* release that reports that quarter and ties out for it
  (spec v0.1 §6.5). Earlier observations stay in the store; nothing is merged.
- ``recasts``: the same (issuer, line, period) reported with different values
  in different releases (P3-03).
- ``definition_changes``: lines added, removed or renamed between consecutive
  releases, and headline metric renames (P3-04).
"""

from __future__ import annotations

import itertools
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.extraction.bridge.keys import line_key
from app.store.db import Store

TOTAL_KEY = "__total__"
_COMPONENT_ROLES = ("gaap_start", "adjustment", "subtotal", "total")


@dataclass(frozen=True)
class LineObs:
    row_order: int
    label: str
    line_key: str
    role: str
    sign: int
    value_raw: str
    value: Decimal | None
    url: str | None
    xpath: str | None

    @property
    def contribution(self) -> Decimal | None:
        return None if self.value is None else self.sign * self.value


@dataclass
class QuarterBridge:
    cik: str
    period_id: str
    end_date: date
    accession: str
    filed: str
    scale: str | None
    metric_label: str | None
    exhibit_url: str | None
    sum_check: dict[str, Any]
    anchor_status: str | None
    lines: list[LineObs] = field(default_factory=list)

    @property
    def total(self) -> LineObs | None:
        return next((ln for ln in self.lines if ln.role == "total"), None)

    @property
    def start(self) -> LineObs | None:
        return next((ln for ln in self.lines if ln.role == "gaap_start"), None)

    @property
    def adjustments(self) -> list[LineObs]:
        return [ln for ln in self.lines if ln.role == "adjustment"]


def _dec(raw: str | None) -> Decimal | None:
    return None if raw is None else Decimal(raw)


def quarter_series(store: Store, cik: str) -> list[QuarterBridge]:
    rows = store.query(
        """
        SELECT o.*, b.bridge_id AS bid, b.scale AS bscale, b.metric_label,
               f.url AS exhibit_url, p.end_date,
               c.status AS sum_status, c.detail AS sum_detail,
               a.status AS anchor_status
        FROM observations o
        JOIN current_bridges b ON b.bridge_id = o.bridge_id
        JOIN filings f ON f.accession = o.accession
        JOIN bridge_periods p ON p.bridge_id = o.bridge_id AND p.period_id = o.period_id
        JOIN checks c ON c.bridge_id = o.bridge_id AND c.kind = 'sum'
                     AND c.period_id = o.period_id
        LEFT JOIN checks a ON a.bridge_id = o.bridge_id AND a.kind = 'anchor'
                          AND a.period_id = o.period_id
        WHERE o.cik = ? AND o.period_id LIKE '3M-%' AND c.status = 'pass'
        ORDER BY o.period_id, o.filed DESC, o.bridge_id DESC, o.row_order
        """,
        (cik,),
    )
    chosen: dict[str, int] = {}
    out: dict[str, QuarterBridge] = {}
    for r in rows:
        pid = r["period_id"]
        if pid not in chosen:
            chosen[pid] = r["bid"]
            out[pid] = QuarterBridge(
                cik=cik,
                period_id=pid,
                end_date=date.fromisoformat(r["end_date"]),
                accession=r["accession"],
                filed=r["filed"],
                scale=r["bscale"],
                metric_label=r["metric_label"],
                exhibit_url=r["exhibit_url"],
                sum_check=json.loads(r["sum_detail"]),
                anchor_status=r["anchor_status"],
            )
        if chosen[pid] != r["bid"]:
            continue
        out[pid].lines.append(
            LineObs(
                row_order=r["row_order"],
                label=r["label"],
                line_key=r["line_key"],
                role=r["role"],
                sign=r["sign"],
                value_raw=r["value_raw"],
                value=_dec(r["value"]),
                url=r["url"],
                xpath=r["xpath"],
            )
        )
    return sorted(out.values(), key=lambda q: q.end_date)


@dataclass(frozen=True)
class Recast:
    cik: str
    period_id: str
    line_key: str
    label: str
    role: str
    first_accession: str
    first_filed: str
    first_value_usd: Decimal
    latest_accession: str
    latest_filed: str
    latest_value_usd: Decimal
    first_url: str | None
    latest_url: str | None

    @property
    def delta_usd(self) -> Decimal:
        return self.latest_value_usd - self.first_value_usd


def recasts(store: Store, cik: str | None = None) -> list[Recast]:
    """
    Values of the same (issuer, line, period) that changed between releases.

    Lines are matched by ``line_key`` (totals by role, so a renamed headline
    still matches). A line_key that occurs twice in one bridge is ambiguous and
    is skipped. Only bridges whose sum tie-out passed for the period count.
    """
    where = "AND o.cik = ?" if cik else ""
    rows = store.query(
        f"""
        SELECT o.cik, o.period_id, o.line_key, o.label, o.role, o.accession,
               o.filed, o.value_usd, o.url, o.bridge_id
        FROM observations o
        JOIN current_bridges b ON b.bridge_id = o.bridge_id
        JOIN checks c ON c.bridge_id = o.bridge_id AND c.kind = 'sum'
                     AND c.period_id = o.period_id AND c.status = 'pass'
        WHERE o.value_usd IS NOT NULL {where}
        ORDER BY o.filed, o.bridge_id
        """,
        (cik,) if cik else (),
    )
    per_bridge: dict[tuple[int, str, str], int] = defaultdict(int)
    for r in rows:
        key = TOTAL_KEY if r["role"] == "total" else r["line_key"]
        per_bridge[(r["bridge_id"], key, r["period_id"])] += 1
    series: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
    for r in rows:
        key = TOTAL_KEY if r["role"] == "total" else r["line_key"]
        if per_bridge[(r["bridge_id"], key, r["period_id"])] > 1:
            continue
        series[(r["cik"], r["period_id"], key)].append(r)
    out: list[Recast] = []
    for (c, pid, key), obs in series.items():
        if len({o["accession"] for o in obs}) < 2:
            continue
        first, latest = obs[0], obs[-1]
        v0, v1 = Decimal(first["value_usd"]), Decimal(latest["value_usd"])
        if v0 == v1:
            continue
        out.append(
            Recast(
                cik=c,
                period_id=pid,
                line_key=key,
                label=latest["label"],
                role=latest["role"],
                first_accession=first["accession"],
                first_filed=first["filed"],
                first_value_usd=v0,
                latest_accession=latest["accession"],
                latest_filed=latest["filed"],
                latest_value_usd=v1,
                first_url=first["url"],
                latest_url=latest["url"],
            )
        )
    return sorted(out, key=lambda r: (r.cik, r.latest_filed, r.period_id))


@dataclass(frozen=True)
class DefinitionChange:
    cik: str
    accession: str
    filed: str
    period_id: str
    prior_accession: str
    kind: str  # added | removed | metric_renamed
    label: str
    prior_label: str | None = None
    value_raw: str | None = None
    url: str | None = None


def definition_changes(store: Store, cik: str) -> list[DefinitionChange]:
    """
    Adjustment lines added or dropped, and headline renames, release over release.

    Each release's bridge is compared with the issuer's previous release (by
    filing date). A line counts as present when it has a non-zero value in any
    column. Only bridges that tie out in every period are compared, so an
    extraction failure is never reported as a definition change.
    """
    rows = store.query(
        """
        SELECT b.bridge_id, b.accession, f.filed, b.metric_label, o.line_key,
               o.label, o.role, o.value, o.value_raw, o.url, o.period_id
        FROM current_bridges b
        JOIN filings f ON f.accession = b.accession
        JOIN observations o ON o.bridge_id = b.bridge_id
        WHERE f.cik = ?
          AND NOT EXISTS (SELECT 1 FROM checks c WHERE c.bridge_id = b.bridge_id
                          AND c.kind = 'sum' AND c.status != 'pass')
          AND EXISTS (SELECT 1 FROM checks c WHERE c.bridge_id = b.bridge_id
                      AND c.kind = 'sum')
        ORDER BY f.filed, b.bridge_id, o.row_order
        """,
        (cik,),
    )
    releases: dict[int, dict[str, Any]] = {}
    for r in rows:
        rel = releases.setdefault(
            r["bridge_id"],
            {
                "accession": r["accession"],
                "filed": r["filed"],
                "metric": r["metric_label"],
                "lines": {},
                "total_url": None,
                "lead": None,
            },
        )
        if r["period_id"].startswith("3M-") and (
            rel["lead"] is None or r["period_id"][3:] > rel["lead"][3:]
        ):
            rel["lead"] = r["period_id"]
        if r["role"] == "total":
            rel["total_url"] = r["url"]
        if r["role"] != "adjustment" or r["value"] in (None, "0"):
            continue
        rel["lines"].setdefault(r["line_key"], (r["label"], r["value_raw"], r["url"]))
    ordered = sorted(releases.values(), key=lambda x: x["filed"])
    out: list[DefinitionChange] = []
    for prev, cur in itertools.pairwise(ordered):
        period = cur["lead"] or ""
        for key in sorted(set(cur["lines"]) - set(prev["lines"])):
            label, raw, url = cur["lines"][key]
            out.append(
                DefinitionChange(
                    cik,
                    cur["accession"],
                    cur["filed"],
                    period,
                    prev["accession"],
                    "added",
                    label,
                    value_raw=raw,
                    url=url,
                )
            )
        for key in sorted(set(prev["lines"]) - set(cur["lines"])):
            label, raw, url = prev["lines"][key]
            out.append(
                DefinitionChange(
                    cik,
                    cur["accession"],
                    cur["filed"],
                    period,
                    prev["accession"],
                    "removed",
                    label,
                    value_raw=raw,
                    url=url,
                )
            )
        if (
            prev["metric"]
            and cur["metric"]
            and _strip(prev["metric"]) != _strip(cur["metric"])
        ):
            out.append(
                DefinitionChange(
                    cik,
                    cur["accession"],
                    cur["filed"],
                    period,
                    prev["accession"],
                    "metric_renamed",
                    cur["metric"],
                    prior_label=prev["metric"],
                    url=cur["total_url"],
                )
            )
    return out


def _strip(label: str) -> str:
    return line_key(label)
