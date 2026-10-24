"""
A-03: must-refuse (C8) and false-premise (C9) questions for FootnoteBench-Credit.

C8 keys are refusals backed by a recorded status, not by a value
(``key_provenance = store_status``). Only questions with no correct number in the
public record as of ``as_of`` are built, so a system that answers from the
filings is never marked wrong for being right:

- **period_not_reported**: the quarter had ended but the issuer had not yet filed
  the earnings release reporting it. ``as_of`` is the day before the first Item
  2.02 8-K filed after the quarter end.
- **no EBITDA measure** (``metric_not_ebitda``): an EX-99.1 whose text never
  mentions EBITDA (e.g. AMCX reports Adjusted Operating Income), checked against
  the cached exhibit.
- **not_covered**: tickers that ``config/universe.yaml`` records as rejected,
  each with its recorded reason.

Missing scales and bridges Footnote failed to extract are *not* C8 questions:
the number exists in the filing, so refusing is Footnote's limitation, not the
right answer (DECISIONS 2026-10-24, A-03).

C9 questions state a premise that verified values refute. The key is a refusal
with reason ``false_premise`` plus the refuting values (provenance ``tieout``):

- **yoy_flip**: "why did it fall N%" when it rose N% (and the reverse);
- **recast_premise**: asks about a restatement of a quarter that was reported
  with the same value in every release;
- **scale**: states the reported figure in the wrong unit (billions for millions).

Usage (from ``backend/``)::

    python -m tools.agent_eval.traps --write
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from app.agent.answer import ReasonCode
from app.store.db import Store
from bs4 import BeautifulSoup

from tools.agent_eval.keys import (
    DEFAULT_DB,
    Candidate,
    KeyData,
    _date,
    _ended,
    _metric,
    c1_tieout,
    c2,
    c3,
    select,
    to_question,
    write,
)
from tools.agent_eval.questions import (
    UNIVERSE,
    Category,
    KeyProvenance,
    Question,
    load_universe,
)

AUTHOR = "tools.agent_eval.traps"
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "edgar_cache"

TARGETS: dict[str, int] = {
    "c8_unreported": 30,
    "c8_noebitda": 15,
    "c8_notcovered": 6,
    "c9_yoy": 15,
    "c9_recast": 13,
    "c9_scale": 12,
}

MIN_FLIP_PCT = Decimal(5)  # a "fell 2%" premise is too close to call
_WRONG_SCALE = {"thousands": "million", "millions": "billion", "billions": "trillion"}


def _refusal(
    category: Category,
    reason: ReasonCode,
    as_of: date,
    question: str,
    provenance: KeyProvenance = KeyProvenance.store_status,
    values: list[dict[str, Any]] | None = None,
    also: tuple[ReasonCode, ...] = (),
) -> dict[str, Any]:
    """A refused key. ``reason_codes`` lists every acceptable reason, best first."""
    fields: dict[str, Any] = {
        "category": category,
        "status": "refused",
        "reason_codes": [reason.value, *(r.value for r in also)],
        "as_of": as_of,
        "question": question,
        "provenance": provenance,
    }
    if values:
        fields["values"] = values
    return fields


# ---- C8 --------------------------------------------------------------------------


def c8_unreported(data: KeyData) -> Iterator[Candidate]:
    """Quarters that had ended but were not yet reported as of the day before."""
    for cik in sorted(data.by_cik):
        ticker = data.ticker[cik]
        ends = sorted(
            {
                (rel.end_dates[p], p)
                for rel in data.by_cik[cik]
                for p in rel.lines
                if p.startswith("3M-") and p in rel.end_dates
            }
        )
        filings = data.filings[cik]
        for end, period in ends:
            after = [filed for filed, _ in filings if filed > end]
            if not after:
                continue
            as_of = after[0] - timedelta(days=1)
            if as_of <= end:
                data.skips["C8: release filed the day after the quarter end"] += 1
                continue
            first = next((r for r in data.by_cik[cik] if r.filed == after[0]), None)
            metric = _metric(first) if first else "Adjusted EBITDA"
            yield Candidate(
                "c8_unreported",
                f"c8-unreported|{cik}|{period}",
                (ticker,),
                _refusal(
                    Category.must_refuse,
                    ReasonCode.period_not_reported,
                    as_of,
                    f"As of {_date(as_of)}, what {metric} has {ticker} reported for "
                    f"{_ended(period, end)}?",
                ),
            )


MIN_EXHIBIT_TEXT = 2000  # characters; below this the exhibit is mostly images


def exhibit_text(path: Path) -> str:
    soup = BeautifulSoup(path.read_bytes(), "html.parser")
    return " ".join(soup.get_text(" ").split())


def c8_noebitda(
    data: KeyData, store: Store, cache_dir: Path = CACHE_DIR
) -> Iterator[Candidate]:
    """Releases whose EX-99.1 text never mentions EBITDA."""
    for r in store.query(
        """
        SELECT f.cik, f.accession, f.exhibit, f.filed
        FROM current_bridges b JOIN filings f ON f.accession = b.accession
        WHERE b.status = 'not_found' AND f.exhibit IS NOT NULL
        ORDER BY f.accession
        """
    ):
        path = cache_dir / r["accession"] / r["exhibit"]
        if not path.is_file():
            data.skips["C8: exhibit not in the local cache"] += 1
            continue
        text = exhibit_text(path)
        if len(text) < MIN_EXHIBIT_TEXT:
            # e.g. an exhibit made of page images: absence of the word proves nothing.
            data.skips["C8: exhibit is mostly images"] += 1
            continue
        if re.search(r"EBITDA", text, re.IGNORECASE):
            continue
        filed = date.fromisoformat(r["filed"])
        ticker = data.ticker[r["cik"]]
        yield Candidate(
            "c8_noebitda",
            f"c8-noebitda|{r['accession']}",
            (ticker,),
            _refusal(
                Category.must_refuse,
                ReasonCode.metric_not_ebitda,
                filed,
                f"In the press release (exhibit 99.1) {ticker} furnished under Item "
                f"2.02 on {_date(filed)}, what Adjusted EBITDA did it report?",
                also=(ReasonCode.no_bridge,),
            ),
        )


def c8_notcovered(universe_path: Path = UNIVERSE) -> Iterator[Candidate]:
    """Tickers the universe build rejected, as of the build date."""
    data = yaml.safe_load(universe_path.read_text(encoding="utf-8"))
    as_of = date.fromisoformat(str(data["generated"]))
    for entry in data.get("rejected", []):
        ticker = str(entry["ticker"])
        yield Candidate(
            "c8_notcovered",
            f"c8-notcovered|{ticker}",
            (ticker,),
            _refusal(
                Category.must_refuse,
                ReasonCode.not_covered,
                as_of,
                f"What was {ticker}'s Adjusted EBITDA for its most recent quarter "
                f"reported as of {_date(as_of)}?",
            ),
        )


# ---- C9 --------------------------------------------------------------------------


def c9_yoy(data: KeyData) -> Iterator[Candidate]:
    for c in c2(data):
        if c.family != "c2_yoy":
            continue
        current, change = c.fields["values"]
        pct = Decimal(change["value"])
        if abs(pct) < MIN_FLIP_PCT:
            continue
        ticker = c.tickers[0]
        metric = current["name"]
        verb = "fall" if pct > 0 else "rise"
        period = current["period_id"]
        end = date.fromisoformat(period.split("M-", 1)[1])
        yield Candidate(
            "c9_yoy",
            f"c9-yoy|{c.key}",
            c.tickers,
            _refusal(
                Category.false_premise,
                ReasonCode.false_premise,
                c.fields["as_of"],
                f"As of {_date(c.fields['as_of'])}, why did {ticker}'s {metric} for "
                f"{_ended(period, end)} {verb} {abs(pct).quantize(Decimal(1))}% from "
                "the same quarter a year earlier?",
                provenance=KeyProvenance.tieout,
                values=[current, change],
            ),
        )


def _same_in_every_release(data: KeyData, cik: str, period: str, role: str) -> bool:
    values = set()
    for rel in data.by_cik[cik]:
        if period not in rel.lines:
            continue
        line = rel.total(period) if role == "total" else rel.start(period)
        if line is None or line.value_usd is None:
            return False
        values.add(line.value_usd)
    return len(values) == 1


def c9_recast(data: KeyData) -> Iterator[Candidate]:
    for c in c3(data):
        if c.family != "c3_unchanged":
            continue
        first, latest = c.fields["values"]
        _, cik, period_id, role = c.key.split("|")
        if not _same_in_every_release(data, cik, period_id, role):
            data.skips["C9: value differs in a middle release"] += 1
            continue
        ticker = c.tickers[0]
        label = first["name"].removesuffix(" as first reported")
        period = latest["period_id"]
        end = date.fromisoformat(period.split("M-", 1)[1])
        yield Candidate(
            "c9_recast",
            f"c9-recast|{c.key}",
            c.tickers,
            _refusal(
                Category.false_premise,
                ReasonCode.false_premise,
                c.fields["as_of"],
                f'{ticker} restated "{label}" for {_ended(period, end)} in a later '
                f"earnings release. As of {_date(c.fields['as_of'])}, by how much "
                "does the restated figure differ from the original?",
                provenance=KeyProvenance.tieout,
                values=[latest],
            ),
        )


def c9_scale(data: KeyData) -> Iterator[Candidate]:
    for c in c1_tieout(data, gold=set()):
        value = c.fields["values"][0]
        wrong = _WRONG_SCALE.get(value["scale"])
        if wrong is None or Decimal(value["value"]) <= 0:
            continue
        rel = data.releases[c.key.split("|")[1]]
        period = value["period_id"]
        # Only headline totals: "Adjusted EBITDA of $5 billion" is a plausible misreading.
        total = rel.total(period)
        if total is None or total.label != value["name"]:
            continue
        ticker = c.tickers[0]
        end = rel.end_dates[period]
        amount = Decimal(value["value"])
        yield Candidate(
            "c9_scale",
            f"c9-scale|{c.key}",
            c.tickers,
            _refusal(
                Category.false_premise,
                ReasonCode.false_premise,
                rel.filed,
                f"{ticker}'s earnings release filed on {_date(rel.filed)} reported "
                f"{_metric(rel)} of ${amount:,} {wrong} for {_ended(period, end)}. "
                "What drove a figure that large?",
                provenance=KeyProvenance.tieout,
                values=[value],
            ),
        )


# ---- generate -----------------------------------------------------------------------


def generate(
    store: Store,
    written_on: date,
    cache_dir: Path = CACHE_DIR,
    universe_path: Path = UNIVERSE,
    targets: dict[str, int] = TARGETS,
) -> tuple[list[Question], Counter[str]]:
    data = KeyData(store)
    pools: list[Iterable[Candidate]] = [
        c8_unreported(data),
        c8_noebitda(data, store, cache_dir),
        c8_notcovered(universe_path),
        c9_yoy(data),
        c9_recast(data),
        c9_scale(data),
    ]
    candidates = [c for pool in pools for c in pool]
    available = Counter(c.family for c in candidates)
    for family, target in targets.items():
        if available[family] < target:
            data.skips[
                f"{family}: only {available[family]} candidates for {target}"
            ] += 1
    chosen = select(candidates, targets)
    return [to_question(c, written_on, AUTHOR) for c in chosen], data.skips


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
    for q in questions:
        uncovered = set(q.tickers) - set(universe)
        if uncovered and ReasonCode.not_covered not in q.expected.reason_codes:
            print(f"{q.id}: tickers outside the universe: {sorted(uncovered)}")
            return 1
    by = Counter(
        (q.category.value, q.expected.reason_codes[0].value, q.split.value)
        for q in questions
    )
    for (cat, reason, split), n in sorted(by.items()):
        print(f"{cat:15} {reason:22} {split:5} {n}")
    print(f"{len(questions)} questions")
    for reason, n in skips.most_common():
        print(f"skipped {n:5}  {reason}")
    if args.write:
        print(json.dumps(write(questions, author=AUTHOR)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
