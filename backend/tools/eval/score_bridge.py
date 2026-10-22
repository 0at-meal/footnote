"""
P2-04 / P2-14: score the bridge engine against the gold set.

Runs ``app.extraction.bridge.engine.extract_headline_bridge`` on every saved
gold release exactly as the ingest pipeline does (whole document, automatic
table selection, issuer fiscal year end and filing date from
``eval/gold/issuers.yaml``; no gold table index or metric label is passed in)
and compares its output with ``eval/gold/labels/``.

The unit is one gold value (line x period); dash placeholders are not scored.
Every metric is reported overall and split by ``verified_by``:

- **table_found**: the engine selected the gold table.
- **line_exact_match**: the engine has a line with the gold label (k-th
  occurrence aligns to k-th occurrence, ``norm_label``), a value for the gold
  ``period_id`` (months + end date), and that value equals the gold value.
- **role_accuracy**: that aligned line has the gold role (start, adjustment,
  subtotal, total).
- **sign_accuracy**: the aligned line's contribution direction,
  sign(sign x value), equals the gold one. Zero values are not scored.
- **scale_accuracy**: the engine's scale equals the gold scale.

**Read this with care.** The gold values were drafted by the same row and
period parsing that the engine now uses (P0-05, on the owner-selected table)
and then confirmed by an independent model reading (P0-05b) or a human
(P0-06). Line-level agreement here is therefore not an independent accuracy
estimate of the parsing; it shows the engine reproduces verified labels with
automatic table selection. Independent evidence comes from tie-out rates on
releases outside the gold set (``eval/RESULTS.md``).

Usage (from ``backend/``)::

    python -m tools.eval.score_bridge
    python -m tools.eval.score_bridge --json ../eval/results/bridge.json
    python -m tools.eval.score_bridge --check ../eval/thresholds-bridge.yaml
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from app.extraction.bridge.core import DraftLine
from app.extraction.bridge.engine import extract_headline_bridge
from app.extraction.scale_and_sign import UnitScale

from tools.eval.score import GROUPS, ScoreError, _rate, gold_info, label_files
from tools.gold.compare import norm_label
from tools.gold.labels import GOLD_DIR, GoldRelease, Scale, load_release

SCORER_VERSION = 1
HEADLINE_METRICS: tuple[str, ...] = (
    "table_found",
    "line_exact_match",
    "role_accuracy",
    "sign_accuracy",
    "scale_accuracy",
)
_SCALES = {
    UnitScale.UNITS: Scale.units,
    UnitScale.THOUSANDS: Scale.thousands,
    UnitScale.MILLIONS: Scale.millions,
    UnitScale.BILLIONS: Scale.billions,
}


@dataclass(frozen=True)
class Outcome:
    ticker: str
    accession: str
    row_order: int
    label: str
    period_id: str
    value_raw: str
    verified_by: str
    table_found: bool
    line_exact: bool
    role_ok: bool | None  # None: no aligned engine line
    sign_ok: bool | None  # None: zero value
    scale_ok: bool
    failure: str | None


def _direction(x: Decimal) -> int:
    return 1 if x > 0 else -1


def score_release(
    gold: GoldRelease, html: bytes, fiscal_year_end: str, filed: date
) -> tuple[list[Outcome], dict[str, Any]]:
    bridge = extract_headline_bridge(
        html, accession=gold.accession, fiscal_year_end=fiscal_year_end, filed=filed
    )
    draft = bridge.draft
    table_found = bridge.table_index == gold.table.table_index
    scale = _SCALES.get(draft.scale) if draft else None
    scale_ok = scale is gold.scale

    by_label: dict[str, list[DraftLine]] = defaultdict(list)
    periods: list[str | None] = []
    if draft is not None:
        periods = [p.period_id for p in draft.periods]
        for dl in draft.lines:
            by_label[norm_label(dl.label)].append(dl)
    seen: dict[str, int] = defaultdict(int)
    outcomes: list[Outcome] = []
    for gl in sorted(gold.lines, key=lambda ln: ln.row_order):
        key = norm_label(gl.label_raw)
        k = seen[key]
        seen[key] += 1
        line = by_label[key][k] if k < len(by_label[key]) else None
        for gv in gl.values:
            if gv.value is None:
                continue
            failure: str | None = None
            exact = False
            sign_ok: bool | None = None
            if bridge.status == "not_found":
                failure = "bridge_not_found"
            elif not table_found:
                failure = "wrong_table"
            elif line is None:
                failure = "label_not_found"
            elif gv.period_id not in periods:
                failure = "period_not_found"
            else:
                got = line.values[periods.index(gv.period_id)]
                if got != gv.value:
                    failure = "value_mismatch"
                else:
                    exact = True
            if gv.value != 0:
                want = _direction(gl.sign * gv.value)
                if line is not None and failure is None:
                    sign_ok = _direction(line.sign * gv.value) == want
                else:
                    sign_ok = False
            outcomes.append(
                Outcome(
                    ticker=gold.ticker,
                    accession=gold.accession,
                    row_order=gl.row_order,
                    label=gl.label_raw,
                    period_id=gv.period_id,
                    value_raw=gv.value_raw,
                    verified_by=gv.verified_by.value,
                    table_found=table_found,
                    line_exact=exact,
                    role_ok=None if line is None else line.role is gl.role,
                    sign_ok=sign_ok,
                    scale_ok=scale_ok,
                    failure=failure,
                )
            )
    sums = draft.sum_checks if draft else []
    release = {
        "ticker": gold.ticker,
        "accession": gold.accession,
        "status": bridge.status,
        "gold_table": gold.table.table_index,
        "engine_table": bridge.table_index,
        "gold_scale": gold.scale.value,
        "engine_scale": scale.value if scale else None,
        "sum_tieouts": f"{sum(c.passed for c in sums)}/{len(sums)}",
        "values": len(outcomes),
        "line_exact": sum(o.line_exact for o in outcomes),
        "exceptions": bridge.exceptions,
    }
    return outcomes, release


def _metric(outcomes: Sequence[Outcome], attr: str) -> dict[str, Any]:
    def count(items: Sequence[Outcome]) -> dict[str, Any]:
        scored = [getattr(o, attr) for o in items if getattr(o, attr) is not None]
        return _rate(sum(1 for s in scored if s), len(scored))

    return {
        "overall": count(outcomes),
        "by_verified_by": {
            g: count([o for o in outcomes if o.verified_by == g]) for g in GROUPS
        },
    }


def _fiscal_info(gold_dir: Path) -> dict[str, tuple[str, date]]:
    issuers = yaml.safe_load((gold_dir / "issuers.yaml").read_text(encoding="utf-8"))
    out: dict[str, tuple[str, date]] = {}
    for issuer in issuers["selected"]:
        fye = str(issuer.get("fiscal_year_end") or "").zfill(4)
        for rel in issuer["releases"]:
            out[rel["accession"]] = (fye, date.fromisoformat(str(rel["filed"])))
    return out


def score_gold_set(gold_dir: Path = GOLD_DIR, examples: int = 5) -> dict[str, Any]:
    labels_dir, raw_dir = gold_dir / "labels", gold_dir / "raw"
    manifest = yaml.safe_load((raw_dir / "manifest.yaml").read_text(encoding="utf-8"))
    entries = sorted(manifest["releases"], key=lambda e: e["accession"])
    if {p.stem for p in label_files(labels_dir)} != {e["accession"] for e in entries}:
        raise ScoreError("label files and manifest releases differ")
    fiscal = _fiscal_info(gold_dir)

    golds: list[GoldRelease] = []
    outcomes: list[Outcome] = []
    releases: list[dict[str, Any]] = []
    for entry in entries:
        gold = load_release(labels_dir / f"{entry['accession']}.json")
        html = gzip.decompress((raw_dir / entry["path"]).read_bytes())
        if not hashlib.sha256(html).hexdigest() == gold.sha256 == entry["sha256"]:
            raise ScoreError(f"{entry['accession']}: saved exhibit sha256 mismatch")
        fye, filed = fiscal[entry["accession"]]
        got, release = score_release(gold, html, fye, filed)
        golds.append(gold)
        outcomes += got
        releases.append(release)

    failures: dict[str, list[Outcome]] = defaultdict(list)
    for o in outcomes:
        if o.failure:
            failures[o.failure].append(o)
    metrics = {
        "table_found": _metric(outcomes, "table_found"),
        "line_exact_match": _metric(outcomes, "line_exact"),
        "role_accuracy": _metric(outcomes, "role_ok"),
        "sign_accuracy": _metric(outcomes, "sign_ok"),
        "scale_accuracy": _metric(outcomes, "scale_ok"),
    }
    metrics["table_found"]["releases"] = _rate(
        sum(r["engine_table"] == r["gold_table"] for r in releases), len(releases)
    )
    return {
        "scorer": "tools.eval.score_bridge",
        "scorer_version": SCORER_VERSION,
        "engine": "app.extraction.bridge.engine.extract_headline_bridge",
        "unit": "gold value (one line x one period); dash placeholders not scored",
        "caveat": (
            "gold values were drafted by the same row/period parsing and confirmed "
            "by a model reading or a human; this is not an independent parsing "
            "accuracy estimate"
        ),
        "gold": gold_info(labels_dir, golds),
        "headline_metrics": list(HEADLINE_METRICS),
        "metrics": metrics,
        "failures": {
            cat: {
                "count": len(items),
                "releases": len({o.accession for o in items}),
                "examples": [
                    f"{o.ticker} {o.accession} line {o.row_order} {o.label!r} "
                    f"{o.period_id} = {o.value_raw}"
                    for o in items[:examples]
                ],
            }
            for cat, items in sorted(failures.items(), key=lambda kv: -len(kv[1]))
        },
        "releases": releases,
    }


def _pct(cell: dict[str, Any]) -> str:
    if cell["rate"] is None:
        return "n/a (n=0)"
    return f"{cell['rate'] * 100:5.1f}% ({cell['correct']}/{cell['n']})"


def summary(report: dict[str, Any]) -> str:
    gold = report["gold"]
    lines = [
        f"Gold set: {gold['releases']} releases, {gold['values']} values "
        f"({gold['null_values']} dash placeholders not scored); verified_by "
        + ", ".join(f"{g}={n}" for g, n in gold["verified_by"].items()),
        f"caveat: {report['caveat']}",
        "",
        f"{'metric':<20}{'overall':<24}" + "".join(f"{g:<24}" for g in GROUPS),
    ]
    for name in HEADLINE_METRICS:
        m = report["metrics"][name]
        lines.append(
            f"{name:<20}{_pct(m['overall']):<24}"
            + "".join(f"{_pct(m['by_verified_by'][g]):<24}" for g in GROUPS)
        )
    lines.append(
        f"table_found by release: {_pct(report['metrics']['table_found']['releases'])}"
    )
    for cat, info in report["failures"].items():
        lines.append(f"  {cat}: {info['count']} values in {info['releases']} releases")
        lines += [f"    e.g. {ex}" for ex in info["examples"][:2]]
    return "\n".join(lines)


def check_thresholds(report: dict[str, Any], thresholds: dict[str, Any]) -> list[str]:
    """Regressions against the recorded floor; empty means the gate passes."""
    problems: list[str] = []
    if thresholds.get("scorer_version") != report["scorer_version"]:
        problems.append("scorer version changed: re-record the floor")
    if thresholds.get("labels_sha256") != report["gold"]["labels_sha256"]:
        problems.append("gold labels changed since the floor was recorded")
    floors: dict[str, Any] = thresholds.get("metrics") or {}
    for name in HEADLINE_METRICS:
        if name not in floors:
            problems.append(f"no threshold recorded for {name}")
            continue
        rate = report["metrics"][name]["overall"]["rate"]
        if rate is None or rate < float(floors[name]):
            problems.append(f"{name} regressed: {rate} < floor {floors[name]}")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="write the full report here")
    parser.add_argument(
        "--check", type=Path, help="thresholds file; exit 1 on regression"
    )
    args = parser.parse_args(argv)
    report = score_gold_set()
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    print(summary(report))
    if args.check:
        problems = check_thresholds(
            report, yaml.safe_load(args.check.read_text(encoding="utf-8"))
        )
        for p in problems:
            print(f"GATE FAIL: {p}")
        print(f"gate: {'FAIL' if problems else 'pass'} ({args.check.name})")
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
