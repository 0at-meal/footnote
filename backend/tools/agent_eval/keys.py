"""
A-02: deterministic answer keys for FootnoteBench-Credit categories C1–C7.

Every key is computed with ``Decimal`` arithmetic from values that are already
verified, never from a model:

- **Gold** (C1): the 30 gold-set releases, ``eval/gold/labels``. Provenance is
  the value's ``verified_by`` (``gold_model_agreement`` / ``gold_human``).
- **Tie-out** (C1–C7): store observations of the newest extraction of a filing
  (``current_bridges``) whose period passes *both* the sum tie-out and the XBRL
  anchor, with a known scale. Provenance ``tieout``.

The keys read the store with their own SQL, not through ``app.analytics``, so a
bug in the analytics the agent will call is not copied into the answer keys.

"Latest reported" means the newest release that reports the period. If that
release is not verified for the period, there is no key: the generator never
falls back to an older release. A quarter is also skipped when a later release
of the issuer, within a year, has no extracted bridge, since that release may
have recast it unseen. Each skip is counted by reason and printed.

Categories that need a judgement Footnote has not had confirmed by a person are
phrased so that the key is pure arithmetic. C6 names the reconciling items to
remove rather than applying a policy to rule-suggested categories (DECISIONS
2026-10-24, A-02).

Usage (from ``backend/``)::

    python -m tools.agent_eval.keys --write   # C1–C7 rows into eval/agent/questions
    python -m tools.agent_eval.keys           # dry run: counts and skip reasons
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from itertools import combinations, pairwise
from pathlib import Path
from typing import Any

from app.analytics.classify import suggest
from app.extraction.bridge.keys import line_key
from app.store.db import Store

from tools.agent_eval.questions import (
    QUESTIONS_DIR,
    Category,
    KeyProvenance,
    Question,
    Split,
    load_file,
    load_universe,
)
from tools.gold.labels import LABELS_DIR, load_release
from tools.gold.labels import SCHEMA_FILE as GOLD_SCHEMA

AUTHOR = "tools.agent_eval.keys"
DEFAULT_DB = Path(__file__).resolve().parents[3] / "var" / "footnote.db"

# Questions per category (PLAN.md shares of ~400 questions; C8/C9 come from A-03).
TARGETS: dict[str, int] = {
    "c1_gold": 20,
    "c1_tieout": 20,
    "c2_ltm": 30,
    "c2_yoy": 30,
    "c3_recast": 27,
    "c3_unchanged": 13,
    "c4_share": 20,
    "c4_ltm_line": 20,
    "c5": 40,
    "c6": 40,
    "c7": 40,
}

PCT_TOLERANCE = Decimal("0.05")  # percentage points; one decimal place
RANK_GAP = Decimal("1.02")  # adjacent ranked values differ by at least 2%
RECAST_WINDOW = timedelta(days=400)
# Labels named in C6 questions avoid EBITDA's own components (D&A, interest,
# tax, NCI, non-operating) so the question reads as an add-back question. The
# key's arithmetic does not depend on this choice.
_COMPONENT_CODES = frozenset({"DA", "INT", "TAX", "NCI", "NONOP"})
_MONTHS = {3: "three", 6: "six", 9: "nine", 12: "twelve"}
_INVISIBLE = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")


@dataclass(frozen=True)
class Line:
    row_order: int
    label: str
    line_key: str
    role: str
    sign: int
    value_raw: str
    value: Decimal | None
    value_usd: Decimal | None
    url: str | None

    @property
    def contribution(self) -> Decimal | None:
        return None if self.value is None else self.sign * self.value


@dataclass
class Release:
    accession: str
    cik: str
    ticker: str
    filed: date
    bridge_id: int
    scale: str | None
    metric_label: str | None
    exhibit_url: str | None
    end_dates: dict[str, date] = field(default_factory=dict)
    lines: dict[str, list[Line]] = field(default_factory=dict)  # period -> lines
    sum_ok: dict[str, bool] = field(default_factory=dict)
    anchor_ok: dict[str, bool] = field(default_factory=dict)

    def verified(self, period: str) -> bool:
        return (
            self.scale is not None
            and self.sum_ok.get(period, False)
            and self.anchor_ok.get(period, False)
        )

    def all_sums_pass(self) -> bool:
        return bool(self.sum_ok) and all(self.sum_ok.values())

    def total(self, period: str) -> Line | None:
        totals = [ln for ln in self.lines.get(period, []) if ln.role == "total"]
        return totals[0] if len(totals) == 1 else None

    def start(self, period: str) -> Line | None:
        starts = [ln for ln in self.lines.get(period, []) if ln.role == "gaap_start"]
        return starts[0] if len(starts) == 1 else None

    def unique_adjustments(self, period: str) -> list[Line]:
        """Adjustment lines whose key occurs once in this column, with a value."""
        lines = self.lines.get(period, [])
        counts = Counter(ln.line_key for ln in lines)
        return [
            ln
            for ln in lines
            if ln.role == "adjustment"
            and counts[ln.line_key] == 1
            and ln.value is not None
            and ln.value != 0
        ]

    def url(self, line: Line) -> str:
        url = line.url or self.exhibit_url
        if url is None:
            raise ValueError(f"{self.accession}: no source URL for {line.label!r}")
        return url


@dataclass(frozen=True)
class Quarter:
    period: str
    end: date
    release: Release


@dataclass
class Candidate:
    family: str  # a TARGETS key
    key: str  # stable identity: the question ID and split derive from it
    tickers: tuple[str, ...]
    fields: dict[str, Any]

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.key.encode("utf-8")).hexdigest()


class KeyData:
    """Releases, checks and filings of the store, held in memory."""

    def __init__(self, store: Store) -> None:
        self.skips: Counter[str] = Counter()
        self.ticker = {
            r["cik"]: r["ticker"] for r in store.query("SELECT * FROM issuers")
        }
        self.sector = {
            r["cik"]: r["sector"]
            for r in store.query("SELECT cik, sector FROM issuers")
        }
        self.filings: dict[str, list[tuple[date, str]]] = defaultdict(list)
        for r in store.query(
            "SELECT cik, accession, filed FROM filings ORDER BY filed"
        ):
            self.filings[r["cik"]].append(
                (date.fromisoformat(r["filed"]), r["accession"])
            )
        self.releases: dict[str, Release] = {}
        for r in store.query(
            """
            SELECT b.bridge_id, b.accession, b.scale, b.metric_label, f.cik, f.filed,
                   f.url
            FROM current_bridges b JOIN filings f ON f.accession = b.accession
            WHERE b.status != 'not_found'
            """
        ):
            self.releases[r["accession"]] = Release(
                accession=r["accession"],
                cik=r["cik"],
                ticker=self.ticker[r["cik"]],
                filed=date.fromisoformat(r["filed"]),
                bridge_id=r["bridge_id"],
                scale=r["scale"],
                metric_label=r["metric_label"],
                exhibit_url=r["url"],
            )
        by_bridge = {rel.bridge_id: rel for rel in self.releases.values()}
        for r in store.query("SELECT * FROM bridge_periods"):
            rel = by_bridge.get(r["bridge_id"])
            if rel is not None and r["period_id"] and r["end_date"]:
                rel.end_dates[r["period_id"]] = date.fromisoformat(r["end_date"])
        for r in store.query("SELECT * FROM checks"):
            rel = by_bridge.get(r["bridge_id"])
            if rel is None:
                continue
            target = rel.sum_ok if r["kind"] == "sum" else rel.anchor_ok
            target[r["period_id"]] = r["status"] == "pass"
        for r in store.query(
            "SELECT * FROM observations ORDER BY bridge_id, row_order"
        ):
            rel = by_bridge.get(r["bridge_id"])
            if rel is None:
                continue
            rel.lines.setdefault(r["period_id"], []).append(
                Line(
                    row_order=r["row_order"],
                    label=r["label"],
                    line_key=r["line_key"],
                    role=r["role"],
                    sign=r["sign"],
                    value_raw=r["value_raw"],
                    value=None if r["value"] is None else Decimal(r["value"]),
                    value_usd=None
                    if r["value_usd"] is None
                    else Decimal(r["value_usd"]),
                    url=r["url"],
                )
            )
        self._quarters: dict[str, list[Quarter]] = {}
        self.by_cik: dict[str, list[Release]] = defaultdict(list)
        for rel in sorted(self.releases.values(), key=lambda x: (x.filed, x.bridge_id)):
            self.by_cik[rel.cik].append(rel)

    def filed_on(self, accession: str) -> date | None:
        for filings in self.filings.values():
            for filed, acc in filings:
                if acc == accession:
                    return filed
        return None

    def _unseen_recast_risk(self, cik: str, after: date) -> bool:
        """A later filing within the window has no extracted bridge."""
        for filed, acc in self.filings[cik]:
            if after < filed <= after + RECAST_WINDOW and acc not in self.releases:
                return True
        return False

    def quarter(self, cik: str, period: str) -> Quarter | None:
        """The period as latest reported, or None (with a counted reason)."""
        reporting = [rel for rel in self.by_cik[cik] if period in rel.lines]
        if not reporting:
            return None
        latest = reporting[-1]
        if period not in latest.end_dates:
            self.skips["period has no end date"] += 1
            return None
        if not latest.verified(period):
            self.skips["latest release not verified for the period"] += 1
            return None
        if self._unseen_recast_risk(cik, latest.filed):
            self.skips["later release without a bridge (possible unseen recast)"] += 1
            return None
        return Quarter(period, latest.end_dates[period], latest)

    def quarters(self, cik: str) -> list[Quarter]:
        """Every 3-month period of the issuer that has a key (memoized)."""
        if cik not in self._quarters:
            periods = {
                p for rel in self.by_cik[cik] for p in rel.lines if p.startswith("3M-")
            }
            out = [q for p in periods if (q := self.quarter(cik, p)) is not None]
            self._quarters[cik] = sorted(out, key=lambda q: q.end)
        return self._quarters[cik]


# ---- helpers -----------------------------------------------------------------


def _date(d: date) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def _ended(period: str, end: date) -> str:
    months = int(period.split("M-", 1)[0])
    return f"the {_MONTHS[months]} months ended {_date(end)}"


def _metric(rel: Release) -> str:
    return rel.metric_label or "Adjusted EBITDA"


def _metric_key(rel: Release) -> str:
    """The headline metric, normalized: "Adjusted EBITDA (a)" == "Adjusted EBITDA".
    "EBITDA" and "Adjusted EBITDA" differ, so they are never compared or summed."""
    return line_key(rel.metric_label or "")


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    return (numerator / denominator * 100).quantize(Decimal("0.01"))


def _consecutive(quarters: list[Quarter]) -> bool:
    return all(
        timedelta(days=80) <= b.end - a.end <= timedelta(days=100)
        for a, b in pairwise(quarters)
    )


def _usd(
    name: str,
    ticker: str,
    period: str,
    value: Decimal,
    scale: str,
    urls: Iterable[str],
    tolerance: Decimal = Decimal(0),
) -> dict[str, Any]:
    return {
        "name": name,
        "ticker": ticker,
        "period_id": period,
        "value": str(value),
        "unit": "usd",
        "scale": scale,
        "tolerance": str(tolerance),
        "source_urls": sorted(set(urls)),
    }


def _pct_value(
    name: str, ticker: str, period: str, value: Decimal, urls: Iterable[str]
) -> dict[str, Any]:
    return {
        "name": name,
        "ticker": ticker,
        "period_id": period,
        "value": str(value),
        "unit": "percent",
        "tolerance": str(PCT_TOLERANCE),
        "source_urls": sorted(set(urls)),
    }


def _windows(quarters: list[Quarter]) -> Iterator[list[Quarter]]:
    """Every run of four consecutive quarters with one scale and one metric."""
    for i in range(len(quarters) - 3):
        window = quarters[i : i + 4]
        if not _consecutive(window):
            continue
        if len({q.release.scale for q in window}) != 1:
            continue
        if len({_metric_key(q.release) for q in window}) != 1:
            continue
        yield window


# ---- C1: point lookup ----------------------------------------------------------


def c1_gold(data: KeyData, labels_dir: Path = LABELS_DIR) -> Iterator[Candidate]:
    for path in sorted(labels_dir.glob("*.json")):
        if path.name == GOLD_SCHEMA.name:
            continue
        rel = load_release(path)
        filed = data.filed_on(rel.accession)
        if filed is None:
            data.skips["gold release not in the store's filings"] += 1
            continue
        for period in rel.periods:
            for line in rel.lines:
                if line.role.value not in ("total", "gaap_start", "adjustment"):
                    continue
                gv = next(v for v in line.values if v.period_id == period.period_id)
                if gv.value is None:
                    continue
                provenance = {
                    "human": KeyProvenance.gold_human,
                    "model_agreement": KeyProvenance.gold_model_agreement,
                    "tieout": KeyProvenance.tieout,
                }[gv.verified_by.value]
                yield Candidate(
                    "c1_gold",
                    f"c1|{rel.accession}|{period.period_id}|{line.row_order}",
                    (rel.ticker,),
                    {
                        "category": Category.point_lookup,
                        "as_of": filed,
                        "question": (
                            f"In its earnings release filed on {_date(filed)}, what "
                            f'amount did {rel.ticker} report for "{line.label_raw}" '
                            f"for {_ended(period.period_id, period.end_date)}? Give "
                            "the figure as reported."
                        ),
                        "values": [
                            _usd(
                                line.label_raw,
                                rel.ticker,
                                period.period_id,
                                gv.value,
                                rel.scale.value,
                                [rel.source_url],
                            )
                        ],
                        "provenance": provenance,
                    },
                )


def c1_tieout(data: KeyData, gold: set[str]) -> Iterator[Candidate]:
    for rel in data.releases.values():
        if rel.accession in gold:
            continue
        for period in rel.lines:
            if not rel.verified(period):
                continue
            picks = [
                rel.total(period),
                rel.start(period),
                *rel.unique_adjustments(period),
            ]
            for line in picks:
                if line is None or line.value is None or rel.scale is None:
                    continue
                yield Candidate(
                    "c1_tieout",
                    f"c1|{rel.accession}|{period}|{line.row_order}",
                    (rel.ticker,),
                    {
                        "category": Category.point_lookup,
                        "as_of": rel.filed,
                        "question": (
                            f"In its earnings release filed on {_date(rel.filed)}, "
                            f"what amount did {rel.ticker} report for "
                            f'"{line.label}" for '
                            f"{_ended(period, rel.end_dates[period])}? Give the "
                            "figure as reported."
                        ),
                        "values": [
                            _usd(
                                line.label,
                                rel.ticker,
                                period,
                                line.value,
                                rel.scale,
                                [rel.url(line)],
                            )
                        ],
                    },
                )


# ---- C2: multi-period ----------------------------------------------------------


def c2(data: KeyData) -> Iterator[Candidate]:
    for cik in sorted(data.by_cik):
        quarters = data.quarters(cik)
        ticker = data.ticker[cik]
        for window in _windows(quarters):
            totals = [q.release.total(q.period) for q in window]
            if any(t is None or t.value is None for t in totals):
                data.skips["LTM window has a quarter without a single total"] += 1
                continue
            last = window[-1]
            as_of = max(q.release.filed for q in window)
            ltm = sum(
                (t.value for t in totals if t and t.value is not None), Decimal(0)
            )
            urls = [q.release.url(t) for q, t in zip(window, totals, strict=True) if t]
            metric = _metric(last.release)
            assert last.release.scale is not None
            yield Candidate(
                "c2_ltm",
                f"c2-ltm|{cik}|{last.period}",
                (ticker,),
                {
                    "category": Category.multi_period,
                    "as_of": as_of,
                    "question": (
                        f"As of {_date(as_of)}, what is {ticker}'s last-twelve-months "
                        f"{metric} for the four quarters ended {_date(last.end)}, "
                        "using each quarter's most recently reported figure?"
                    ),
                    "values": [
                        _usd(
                            f"LTM {metric}",
                            ticker,
                            f"12M-{last.end.isoformat()}",
                            ltm,
                            last.release.scale,
                            urls,
                        )
                    ],
                },
            )
        by_end = {q.end: q for q in quarters}
        for q in quarters:
            prior = next(
                (
                    p
                    for d, p in by_end.items()
                    if timedelta(days=357) <= q.end - d <= timedelta(days=371)
                ),
                None,
            )
            if prior is None:
                continue
            if _metric_key(q.release) != _metric_key(prior.release):
                data.skips["YoY: the two quarters report different metrics"] += 1
                continue
            cur_t, pri_t = q.release.total(q.period), prior.release.total(prior.period)
            if not (cur_t and pri_t and cur_t.value_usd and pri_t.value_usd):
                continue
            if pri_t.value_usd <= 0 or q.release.scale is None or cur_t.value is None:
                data.skips["YoY base not positive"] += 1
                continue
            change = _pct(cur_t.value_usd - pri_t.value_usd, pri_t.value_usd)
            as_of = max(q.release.filed, prior.release.filed)
            metric = _metric(q.release)
            urls = [q.release.url(cur_t), prior.release.url(pri_t)]
            yield Candidate(
                "c2_yoy",
                f"c2-yoy|{cik}|{q.period}",
                (ticker,),
                {
                    "category": Category.multi_period,
                    "as_of": as_of,
                    "question": (
                        f"As of {_date(as_of)}, what was {ticker}'s {metric} for "
                        f"{_ended(q.period, q.end)}, and by what percentage did it "
                        "change from the same quarter a year earlier? Use the most "
                        "recently reported figure for each quarter."
                    ),
                    "values": [
                        _usd(
                            metric,
                            ticker,
                            q.period,
                            cur_t.value,
                            q.release.scale,
                            [q.release.url(cur_t)],
                        ),
                        _pct_value(
                            f"YoY % change in {metric}", ticker, q.period, change, urls
                        ),
                    ],
                },
            )


# ---- C3: point in time -------------------------------------------------------------


def c3(data: KeyData) -> Iterator[Candidate]:
    for cik in sorted(data.by_cik):
        releases = data.by_cik[cik]
        ticker = data.ticker[cik]
        periods = sorted(
            {p for rel in releases for p in rel.lines if p.startswith("3M-")}
        )
        for period in periods:
            reporting = [rel for rel in releases if period in rel.lines]
            if len(reporting) < 2:
                continue
            first, latest = reporting[0], reporting[-1]
            if not (first.verified(period) and latest.verified(period)):
                data.skips["recast pair: first or latest release not verified"] += 1
                continue
            if data._unseen_recast_risk(cik, latest.filed):
                data.skips[
                    "later release without a bridge (possible unseen recast)"
                ] += 1
                continue
            for role in ("total", "gaap_start"):
                a = first.total(period) if role == "total" else first.start(period)
                b = latest.total(period) if role == "total" else latest.start(period)
                if not (a and b and a.value is not None and b.value is not None):
                    continue
                if a.value_usd is None or b.value_usd is None:
                    continue
                if first.scale is None or latest.scale is None:
                    continue
                same = (
                    _metric_key(first) == _metric_key(latest)
                    if role == "total"
                    else a.line_key == b.line_key
                )
                if not same:
                    # e.g. MAT reported "EBITDA" in one release and "Adjusted
                    # EBITDA" in a later one: a different measure, not a recast.
                    data.skips["C3: a different metric or line, not a recast"] += 1
                    continue
                family = "c3_recast" if a.value_usd != b.value_usd else "c3_unchanged"
                label = b.label
                yield Candidate(
                    family,
                    f"c3|{cik}|{period}|{role}",
                    (ticker,),
                    {
                        "category": Category.point_in_time,
                        "as_of": latest.filed,
                        "question": (
                            f'{ticker} has reported "{label}" for '
                            f"{_ended(period, latest.end_dates[period])} in more than "
                            "one earnings release. What was the figure as first "
                            f"reported, and what is it as most recently reported as of "
                            f"{_date(latest.filed)}?"
                        ),
                        "values": [
                            _usd(
                                f"{label} as first reported",
                                ticker,
                                period,
                                a.value,
                                first.scale,
                                [first.url(a)],
                            ),
                            _usd(
                                f"{label} as most recently reported",
                                ticker,
                                period,
                                b.value,
                                latest.scale,
                                [latest.url(b)],
                            ),
                        ],
                    },
                )


# ---- C4: add-back composition --------------------------------------------------------


def c4(data: KeyData) -> Iterator[Candidate]:
    for cik in sorted(data.by_cik):
        quarters = data.quarters(cik)
        ticker = data.ticker[cik]
        for q in quarters:
            total = q.release.total(q.period)
            if total is None or total.value is None or total.value <= 0:
                continue
            metric = _metric(q.release)
            for line in q.release.unique_adjustments(q.period):
                assert line.contribution is not None
                yield Candidate(
                    "c4_share",
                    f"c4-share|{cik}|{q.period}|{line.line_key}",
                    (ticker,),
                    {
                        "category": Category.addback_composition,
                        "as_of": q.release.filed,
                        "question": (
                            f"For {_ended(q.period, q.end)}, as most recently "
                            f"reported by {ticker} as of {_date(q.release.filed)}, "
                            f'what percentage of {metric} came from "{line.label}"? '
                            "Use the amount as it contributes to the reconciliation "
                            f"(negative if it reduces {metric})."
                        ),
                        "values": [
                            _pct_value(
                                f"share of {metric} from {line.label}",
                                ticker,
                                q.period,
                                _pct(line.contribution, total.value),
                                [q.release.url(line), q.release.url(total)],
                            )
                        ],
                    },
                )
        for window in _windows(quarters):
            last = window[-1]
            assert last.release.scale is not None
            for line in last.release.unique_adjustments(last.period):
                matches = []
                for q in window:
                    same = [
                        ln
                        for ln in q.release.unique_adjustments(q.period)
                        if ln.line_key == line.line_key
                    ]
                    if len(same) != 1:
                        break
                    matches.append((q, same[0]))
                if len(matches) != 4:
                    continue
                ltm_total = sum(
                    (
                        ln.contribution
                        for _, ln in matches
                        if ln.contribution is not None
                    ),
                    Decimal(0),
                )
                as_of = max(q.release.filed for q in window)
                metric = _metric(last.release)
                yield Candidate(
                    "c4_ltm_line",
                    f"c4-ltm|{cik}|{last.period}|{line.line_key}",
                    (ticker,),
                    {
                        "category": Category.addback_composition,
                        "as_of": as_of,
                        "question": (
                            f"Over the four quarters ended {_date(last.end)}, as most "
                            f"recently reported as of {_date(as_of)}, what is the "
                            f'total of "{line.label}" in {ticker}\'s {metric} '
                            "reconciliation, as it contributes to "
                            f"{metric}?"
                        ),
                        "values": [
                            _usd(
                                f"LTM {line.label}",
                                ticker,
                                f"12M-{last.end.isoformat()}",
                                ltm_total,
                                last.release.scale,
                                [q.release.url(ln) for q, ln in matches],
                            )
                        ],
                    },
                )


# ---- C5: definition change -------------------------------------------------------------


def _present(rel: Release) -> dict[str, Line]:
    """Adjustment lines with a non-zero value in any column, by line key."""
    out: dict[str, Line] = {}
    for period in sorted(rel.lines):
        for ln in rel.lines[period]:
            if ln.role == "adjustment" and ln.value not in (None, Decimal(0)):
                out.setdefault(ln.line_key, ln)
    return out


def c5(data: KeyData) -> Iterator[Candidate]:
    for cik in sorted(data.filings):
        filings = data.filings[cik]
        ticker = data.ticker[cik]
        for (_, prev_acc), (_, cur_acc) in pairwise(filings):
            prev, cur = data.releases.get(prev_acc), data.releases.get(cur_acc)
            if prev is None or cur is None:
                data.skips["C5: release or its predecessor has no bridge"] += 1
                continue
            if not (prev.all_sums_pass() and cur.all_sums_pass()):
                data.skips["C5: a sum tie-out fails in one of the two releases"] += 1
                continue
            before, after = _present(prev), _present(cur)
            if not before or not after:
                continue
            if len(set(before) & set(after)) < 0.5 * max(len(before), len(after)):
                data.skips["C5: layout changed (most lines differ)"] += 1
                continue
            added = sorted(set(after) - set(before))
            dropped = sorted(set(before) - set(after))
            if len(added) + len(dropped) > 6:
                continue
            if added and dropped:
                # Could be renames ("Income tax expense" -> "Income tax expense
                # (benefit)"); whether it is one is a judgement, so no key.
                data.skips["C5: lines both added and dropped (possible rename)"] += 1
                continue
            lead = max(
                (p for p in cur.lines if p.startswith("3M-")),
                key=lambda p: cur.end_dates.get(p, date.min),
                default=None,
            )
            if lead is None:
                continue
            labels = [
                {
                    "ticker": ticker,
                    "label_raw": after[k].label,
                    "change": "added",
                    "source_urls": [cur.url(after[k])],
                }
                for k in added
            ] + [
                {
                    "ticker": ticker,
                    "label_raw": before[k].label,
                    "change": "dropped",
                    "source_urls": [prev.url(before[k])],
                }
                for k in dropped
            ]
            counts = [
                {
                    "name": f"number of reconciling lines {kind}",
                    "ticker": ticker,
                    "period_id": lead,
                    "value": str(n),
                    "unit": "items",
                    "tolerance": "0",
                    "source_urls": [
                        u for u in (cur.exhibit_url, prev.exhibit_url) if u
                    ],
                }
                for kind, n in (("added", len(added)), ("dropped", len(dropped)))
            ]
            yield Candidate(
                "c5",
                f"c5|{cik}|{cur_acc}",
                (ticker,),
                {
                    "category": Category.definition_change,
                    "as_of": cur.filed,
                    "question": (
                        f"Compare the {_metric(cur)} reconciliation in {ticker}'s "
                        f"earnings release filed on {_date(cur.filed)} with the one in "
                        f"its previous earnings release (filed {_date(prev.filed)}). "
                        "Which reconciling items appear with a non-zero amount in the "
                        "new release but not the previous one, and which were dropped? "
                        "Say how many of each, including none."
                    ),
                    "values": counts,
                    "labels": labels,
                },
            )


# ---- C6: normalization with named items -------------------------------------------------


def c6(data: KeyData) -> Iterator[Candidate]:
    for cik in sorted(data.by_cik):
        ticker = data.ticker[cik]
        for q in data.quarters(cik):
            total = q.release.total(q.period)
            if total is None or total.value is None or q.release.scale is None:
                continue
            items = [
                ln
                for ln in q.release.unique_adjustments(q.period)
                if not set(_codes(ln.line_key)) & _COMPONENT_CODES
            ]
            items.sort(key=lambda ln: hashlib.sha256(ln.line_key.encode()).hexdigest())
            for size in (1, 2, 3):
                for chosen in combinations(items[:4], size):
                    removed = sum(
                        (
                            ln.contribution
                            for ln in chosen
                            if ln.contribution is not None
                        ),
                        Decimal(0),
                    )
                    names = "; ".join(f'"{ln.label}"' for ln in chosen)
                    metric = _metric(q.release)
                    keys = "+".join(sorted(ln.line_key for ln in chosen))
                    yield Candidate(
                        "c6",
                        f"c6|{cik}|{q.period}|{keys}",
                        (ticker,),
                        {
                            "category": Category.normalization,
                            "as_of": q.release.filed,
                            "question": (
                                f"Take {ticker}'s {metric} for "
                                f"{_ended(q.period, q.end)}, as most recently reported "
                                f"as of {_date(q.release.filed)}. What would it be if "
                                f"these reconciling items were removed from the "
                                f"reconciliation: {names}?"
                            ),
                            "values": [
                                _usd(
                                    f"{metric} without {names}",
                                    ticker,
                                    q.period,
                                    total.value - removed,
                                    q.release.scale,
                                    [
                                        q.release.url(total),
                                        *(q.release.url(ln) for ln in chosen),
                                    ],
                                )
                            ],
                        },
                    )


def _codes(line_key: str) -> tuple[str, ...]:
    s = suggest(line_key)
    return s.components if s.code == "MIXED" else (s.code,)


# ---- C7: cross-issuer ranking ---------------------------------------------------------


@dataclass(frozen=True)
class _Ltm:
    ticker: str
    end: date
    value_usd: Decimal
    as_of: date
    urls: tuple[str, ...]


def _latest_ltm(data: KeyData, cik: str) -> _Ltm | None:
    """LTM over the issuer's four most recent quarters, if all are verified."""
    releases = data.by_cik[cik]
    periods = {p for rel in releases for p in rel.lines if p.startswith("3M-")}
    if not periods:
        return None
    ends = sorted(
        {
            rel.end_dates[p]
            for rel in releases
            for p in rel.lines
            if p in periods and p in rel.end_dates
        }
    )
    quarters = data.quarters(cik)
    if not quarters or quarters[-1].end != ends[-1]:
        data.skips["C7: most recent quarter not verified"] += 1
        return None
    window = quarters[-4:]
    if (
        len(window) != 4
        or not _consecutive(window)
        or len({_metric_key(q.release) for q in window}) != 1
    ):
        return None
    totals = [q.release.total(q.period) for q in window]
    if any(t is None or t.value_usd is None for t in totals):
        return None
    value = sum((t.value_usd for t in totals if t and t.value_usd), Decimal(0))
    return _Ltm(
        data.ticker[cik],
        window[-1].end,
        value,
        max(q.release.filed for q in window),
        tuple(q.release.url(t) for q, t in zip(window, totals, strict=True) if t),
    )


def c7(data: KeyData) -> Iterator[Candidate]:
    ltms = {cik: x for cik in sorted(data.by_cik) if (x := _latest_ltm(data, cik))}
    by_sector: dict[str, list[str]] = defaultdict(list)
    for cik in ltms:
        by_sector[data.sector.get(cik, "")].append(cik)
    groups: list[tuple[str, ...]] = []
    for ciks in by_sector.values():
        ordered = sorted(ciks, key=lambda c: ltms[c].ticker)
        for size in (3, 4, 5):
            groups.extend(combinations(ordered, size))
    # Across sectors: consecutive groups of five in a fixed hash order.
    mixed = sorted(ltms, key=lambda c: hashlib.sha256(c.encode()).hexdigest())
    groups.extend(tuple(mixed[i : i + 5]) for i in range(len(mixed) - 4))
    for group in groups:
        members = sorted((ltms[c] for c in group), key=lambda x: -x.value_usd)
        if any(
            b.value_usd <= 0 or a.value_usd < b.value_usd * RANK_GAP
            for a, b in pairwise(members)
        ):
            continue
        as_of = max(m.as_of for m in members)
        tickers = tuple(sorted(m.ticker for m in members))
        yield Candidate(
            "c7",
            f"c7|{'|'.join(tickers)}",
            tickers,
            {
                "category": Category.cross_issuer,
                "as_of": as_of,
                "question": (
                    f"As of {_date(as_of)}, rank {', '.join(tickers)} by "
                    "last-twelve-months adjusted EBITDA (each issuer's headline "
                    "measure) in US dollars, largest first, using each issuer's four "
                    "most recently reported quarters."
                ),
                "ranking": [m.ticker for m in members],
            },
        )


# ---- selection and output ---------------------------------------------------------------


def select(candidates: Iterable[Candidate], targets: dict[str, int]) -> list[Candidate]:
    """
    Per family: round-robin across tickers, each ticker's candidates in hash
    order, until the family's target. Deterministic for a given store.
    """
    families: dict[str, dict[tuple[str, ...], list[Candidate]]] = defaultdict(
        lambda: defaultdict(list)
    )
    seen: set[str] = set()
    for c in candidates:
        if c.key in seen:
            continue
        seen.add(c.key)
        families[c.family][c.tickers].append(c)
    chosen: list[Candidate] = []
    for family, target in targets.items():
        groups = [
            sorted(cs, key=lambda c: c.digest)
            for _, cs in sorted(families[family].items())
        ]
        groups.sort(key=lambda g: g[0].digest)
        picked = 0
        depth = 0
        while picked < target and any(depth < len(g) for g in groups):
            for g in groups:
                if depth < len(g) and picked < target:
                    chosen.append(g[depth])
                    picked += 1
            depth += 1
    return chosen


def _show(text: str) -> str:
    """Question text without invisible characters (labels keep them as reported)."""
    return " ".join(_INVISIBLE.sub("", text).split())


def to_question(c: Candidate, written_on: date) -> Question:
    f = c.fields
    category: Category = f["category"]
    expected: dict[str, Any] = {"status": "answered"}
    for name in ("values", "labels", "ranking"):
        if f.get(name):
            expected[name] = f[name]
    if "values" in expected:
        expected["values"] = [
            {**v, "name": _show(v["name"])} for v in expected["values"]
        ]
    return Question.model_validate(
        {
            "id": f"fbc-{c.family.split('_')[0]}-{c.digest[:10]}",
            "split": Split.dev if int(c.digest[:8], 16) % 4 == 0 else Split.test,
            "category": category,
            "question": _show(f["question"]),
            "as_of": f["as_of"],
            "tickers": list(c.tickers),
            "expected": expected,
            "key_provenance": f.get("provenance", KeyProvenance.tieout),
            "author": AUTHOR,
            "written_on": written_on,
            "notes": f"generated from {c.key}",
        }
    )


def generate(
    store: Store,
    written_on: date,
    labels_dir: Path = LABELS_DIR,
    targets: dict[str, int] = TARGETS,
) -> tuple[list[Question], Counter[str]]:
    data = KeyData(store)
    gold = {
        load_release(p).accession
        for p in labels_dir.glob("*.json")
        if p.name != GOLD_SCHEMA.name
    }
    pools: list[Iterable[Candidate]] = [
        c1_gold(data, labels_dir),
        c1_tieout(data, gold),
        c2(data),
        c3(data),
        c4(data),
        c5(data),
        c6(data),
        c7(data),
    ]
    candidates = [c for pool in pools for c in pool]
    available = Counter(c.family for c in candidates)
    chosen = select(candidates, targets)
    for family, target in targets.items():
        if available[family] < target:
            data.skips[
                f"{family}: only {available[family]} candidates for {target}"
            ] += 1
    return [to_question(c, written_on) for c in chosen], data.skips


def write(
    questions: list[Question], questions_dir: Path = QUESTIONS_DIR
) -> dict[str, int]:
    """
    Replace this generator's rows in ``<split>.jsonl`` and keep everyone else's.
    A regenerated question identical to the stored one keeps its stored row, so
    re-running on an unchanged store changes no file.
    """
    questions_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for split in Split:
        path = questions_dir / f"{split.value}.jsonl"
        existing, problems = load_file(path) if path.exists() else ([], [])
        if problems:
            raise ValueError(f"{path.name} has problems; fix them first: {problems}")
        old = {q.id: q for q in existing if q.author == AUTHOR}
        kept = [q for q in existing if q.author != AUTHOR]
        new = []
        for q in (q for q in questions if q.split is split):
            prior = old.get(q.id)
            same = (
                prior is not None
                and prior.model_copy(update={"written_on": q.written_on}) == q
            )
            new.append(prior if same and prior is not None else q)
        rows = sorted(kept + new, key=lambda q: q.id)
        path.write_text(
            "".join(q.model_dump_json(exclude_none=True) + "\n" for q in rows),
            encoding="utf-8",
            newline="\n",
        )
        counts[split.value] = len(rows)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--write", action="store_true")
    parser.add_argument(
        "--written-on", type=date.fromisoformat, default=datetime.now(UTC).date()
    )
    args = parser.parse_args()
    if not args.db.exists():
        print(f"no store at {args.db}; run the ingest first")
        return 1
    store = Store(args.db)
    try:
        questions, skips = generate(store, args.written_on)
    finally:
        store.close()
    universe = load_universe()
    stray = sorted({t for q in questions for t in q.tickers} - set(universe))
    if stray:
        print(f"tickers outside config/universe.yaml: {stray}")
        return 1
    by = Counter(
        (q.category.value, q.key_provenance.value, q.split.value) for q in questions
    )
    for (cat, prov, split), n in sorted(by.items()):
        print(f"{cat:20} {prov:22} {split:5} {n}")
    print(f"{len(questions)} questions")
    for reason, n in skips.most_common():
        print(f"skipped {n:5}  {reason}")
    if args.write:
        print(json.dumps(write(questions)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
