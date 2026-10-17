"""
P0-08: score the production HTML extractor against the gold set.

For every release in the P0-03 manifest this tool reads the saved exhibit
(``eval/gold/raw/<accession>/<exhibit>.gz``, sha256-checked), runs
``HtmlExtractor`` exactly as a caller would (default ``target_metric``), and
compares its output with the gold labels (``eval/gold/labels/<accession>.json``).

The unit of scoring is one gold *value* (one line x one period), so every metric
can be split by the value's ``verified_by``. Dash placeholders (gold value null)
are not scored and are counted separately. Metrics:

- **table_found**: the extractor's top-ranked reconciliation table is the gold
  table. Also reported per release.
- **line_exact_match**: the extractor emits, from the gold table, a value whose
  row label matches the gold label (case, whitespace, dash and trailing-footnote
  insensitive; the k-th gold line with a label aligns to the k-th extractor row
  with it), whose period string identifies exactly the gold period, and whose
  number equals the gold value.
- **line_label_value_match** (diagnostic): as above but ignoring the period, so
  period-binding failures can be told apart from label and value failures.
- **scale_accuracy**: the scale ``scale_and_sign.detect_scale_from_caption``
  finds in the extractor's table title equals the gold scale. The extractor
  passes no other caption today, so this is what the current code can know.
  Also reported per release.
- **sign_accuracy**: the direction ``scale_and_sign.detect_sign`` gives the
  located cell equals the gold contribution direction, sign(sign x value). A
  value counts as located when its aligned row has a cell of the same magnitude;
  an unlocated value counts as wrong. Zero values have no direction and are not
  scored.

The extractor's records are attributed to tables by replaying its public
pipeline (``extract_html_tables`` + ``detect_reconciliation_tables``) and
checking the replay record by record against the real output; any divergence
raises. XPaths cannot be used for this: they are not unique in these filings.

The scorer is deterministic and offline: it never imports ``app.ingestion``.

Usage (from ``backend/``)::

    python -m tools.eval.score                       # summary to stdout
    python -m tools.eval.score --json ../eval/results/score.json
"""

from __future__ import annotations

import argparse
import calendar
import gzip
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from app.extraction.html.detector import detect_reconciliation_tables
from app.extraction.html.extractor import HtmlExtractor
from app.extraction.html.models import HtmlCell, HtmlTable
from app.extraction.html.table_parser import extract_html_tables
from app.extraction.locator import HtmlLocator
from app.extraction.scale_and_sign import (
    UnitScale,
    detect_scale_from_caption,
    detect_sign,
)
from bs4 import BeautifulSoup

from tools.gold.compare import norm_label
from tools.gold.labels import (
    GOLD_DIR,
    SCHEMA_FILE,
    GoldRelease,
    Period,
    Scale,
    VerifiedBy,
    load_release,
)

SCORER_VERSION = 1
GROUPS: tuple[str, ...] = tuple(v.value for v in VerifiedBy)
HEADLINE_METRICS: tuple[str, ...] = (
    "table_found",
    "line_exact_match",
    "scale_accuracy",
    "sign_accuracy",
)
DIAGNOSTIC_METRICS: tuple[str, ...] = ("line_label_value_match",)

_SCALES = {
    UnitScale.UNITS: Scale.units,
    UnitScale.THOUSANDS: Scale.thousands,
    UnitScale.MILLIONS: Scale.millions,
    UnitScale.BILLIONS: Scale.billions,
}


class ScoreError(Exception):
    """The inputs are inconsistent; scoring them would give a wrong number."""


# ---------------------------------------------------------------- extractor


@dataclass(frozen=True)
class ExtractedValue:
    """One numeric value the extractor emitted from its top-ranked table."""

    row_idx: int
    row_label: str
    period: str | None
    value_raw: str
    value: Decimal
    direction: int  # scale_and_sign.detect_sign: +1 or -1


@dataclass(frozen=True)
class ExtractorOutput:
    status: str
    not_found_reason: str | None
    candidate_tables: tuple[int, ...]  # ranked, best first
    table_index: int | None
    table_title: str | None
    scale: Scale | None
    scale_reason: str | None
    values: tuple[ExtractedValue, ...]


def _emitted(table: HtmlTable) -> Iterable[tuple[HtmlCell, str]]:
    """The cells HtmlExtractor turns into records, in its order."""
    for cell in table.cells:
        if cell.numeric_value is None:
            continue
        label = table.row_headers.get(cell.row_idx, "").strip()
        if label:
            yield cell, label


def table_scale(title: str) -> tuple[Scale | None, str | None]:
    res = detect_scale_from_caption(title)
    if res.is_ambiguous or res.scale is UnitScale.UNKNOWN:
        return None, res.flag_reason or "scale not detected"
    return _SCALES[res.scale], None


def run_extractor(
    html: bytes, accession: str, exhibit: str, url: str, cik: str
) -> ExtractorOutput:
    """Run HtmlExtractor and attribute its records to its top-ranked table."""
    result = HtmlExtractor().extract(html, accession, exhibit, url=url, cik=cik)
    if result.status != "success":
        return ExtractorOutput(
            status=result.status,
            not_found_reason=result.not_found_reason,
            candidate_tables=(),
            table_index=None,
            table_title=None,
            scale=None,
            scale_reason="no table",
            values=(),
        )

    candidates = detect_reconciliation_tables(
        extract_html_tables(BeautifulSoup(html, "lxml"))
    )
    replay = [(t, c, lbl) for t in candidates for c, lbl in _emitted(t)]
    if len(replay) != len(result.records):
        raise ScoreError(
            f"{accession}: replay gives {len(replay)} records, "
            f"extractor gave {len(result.records)}"
        )
    for i, ((_, cell, label), rec) in enumerate(zip(replay, result.records)):
        loc = rec.locator
        if (
            not isinstance(loc, HtmlLocator)
            or loc.element_path != cell.xpath
            or rec.value != cell.text.strip()
            or not rec.label.endswith(label)
        ):
            raise ScoreError(f"{accession}: replay diverges at record {i}")

    top = candidates[0]
    scale, scale_reason = table_scale(top.title)
    values = tuple(
        ExtractedValue(
            row_idx=cell.row_idx,
            row_label=label,
            period=cell.period,
            value_raw=cell.text.strip(),
            value=Decimal(str(cell.numeric_value)),
            direction=detect_sign(cell.text.strip(), label)[0],
        )
        for t, cell, label in replay
        if t is top
    )
    return ExtractorOutput(
        status=result.status,
        not_found_reason=None,
        candidate_tables=tuple(t.index for t in candidates),
        table_index=top.index,
        table_title=top.title,
        scale=scale,
        scale_reason=scale_reason,
        values=values,
    )


# ---------------------------------------------------------------- periods

# The extractor's period strings come only from its PERIOD_PATTERNS: "<n> months
# ended <date>", "year ended <date>", "<Month d, yyyy>", "Q<n> [FY]yy" or "yyyy".
_DURATIONS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"\bthree\s+months\b", re.IGNORECASE), 3),
    (re.compile(r"\bsix\s+months\b", re.IGNORECASE), 6),
    (re.compile(r"\bnine\s+months\b", re.IGNORECASE), 9),
    (re.compile(r"\btwelve\s+months\b", re.IGNORECASE), 12),
    (re.compile(r"\byear\s+ended\b", re.IGNORECASE), 12),
    (re.compile(r"\bQ[1-4]\b", re.IGNORECASE), 3),
)
_FULL_DATE = re.compile(r"\b([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})\b")
_QUARTER_YEAR = re.compile(r"\bQ[1-4]\s+(?:FY)?(\d{2,4})\b", re.IGNORECASE)
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}


@dataclass(frozen=True)
class PeriodHint:
    end_date: date | None
    year: int | None
    months: int | None


def parse_period_hint(text: str | None) -> PeriodHint:
    if not text:
        return PeriodHint(None, None, None)
    months = next((m for pat, m in _DURATIONS if pat.search(text)), None)
    end: date | None = None
    year: int | None = None
    full = _FULL_DATE.search(text)
    if full:
        year = int(full.group(3))
        month = _MONTHS.get(full.group(1)[:3].lower())
        try:
            end = date(year, month, int(full.group(2))) if month else None
        except ValueError:  # e.g. "February 30": the year still counts
            end = None
    elif quarter := _QUARTER_YEAR.search(text):
        yy = quarter.group(1)
        year = int(yy) + 2000 if len(yy) == 2 else int(yy)
    elif plain := _YEAR.search(text):
        year = int(plain.group(1))
    return PeriodHint(end, year, months)


def resolve_period(
    text: str | None, periods: Sequence[Period]
) -> tuple[str | None, str]:
    """The gold period a period string identifies, or None and why not."""
    hint = parse_period_hint(text)
    if hint == PeriodHint(None, None, None):
        return None, "period_missing"
    matches = [
        p.period_id
        for p in periods
        if (hint.end_date is None or hint.end_date == p.end_date)
        and (hint.year is None or hint.year == p.end_date.year)
        and (hint.months is None or hint.months == p.months)
    ]
    if len(matches) == 1:
        return matches[0], "ok"
    return None, "period_ambiguous" if matches else "period_wrong"


# ---------------------------------------------------------------- scoring


@dataclass(frozen=True)
class ValueOutcome:
    ticker: str
    accession: str
    row_order: int
    label: str
    period_id: str
    value_raw: str
    verified_by: str
    table_found: bool
    scale_ok: bool
    scale_failure: str | None
    line_exact: bool
    line_label_value: bool
    line_failure: str | None
    sign_ok: bool | None  # None: zero value, no direction to score
    sign_failure: str | None
    line_detail: str
    scale_detail: str
    sign_detail: str


@dataclass(frozen=True)
class ReleaseScore:
    ticker: str
    accession: str
    gold_table: int
    extractor_table: int | None
    gold_table_rank: int | None  # 1-based rank among candidates
    candidate_tables: tuple[int, ...]
    extractor_title: str | None
    gold_scale: str
    extractor_scale: str | None
    scale_reason: str | None
    not_found_reason: str | None
    null_values: int
    outcomes: tuple[ValueOutcome, ...]


def _direction(x: Decimal) -> int:
    return 1 if x > 0 else -1


def _rows(values: Sequence[ExtractedValue]) -> dict[str, list[list[ExtractedValue]]]:
    """Extractor rows (in table order) grouped by normalized label."""
    by_idx: dict[int, list[ExtractedValue]] = defaultdict(list)
    for v in values:
        by_idx[v.row_idx].append(v)
    rows: dict[str, list[list[ExtractedValue]]] = defaultdict(list)
    for idx in sorted(by_idx):
        rows[norm_label(by_idx[idx][0].row_label)].append(by_idx[idx])
    return rows


def score_release(gold: GoldRelease, out: ExtractorOutput) -> ReleaseScore:
    table_found = out.table_index == gold.table.table_index
    scale_ok = out.scale is gold.scale
    scale_detail = f"table {out.table_index} title {out.table_title!r}: " + (
        out.scale_reason
        or f"read {out.scale.value if out.scale else None}, gold {gold.scale.value}"
    )
    if scale_ok:
        scale_failure = None
    elif out.table_index is None:
        scale_failure = "no_table"
    elif out.scale is None:
        scale_failure = "scale_not_detected"
    else:
        scale_failure = "scale_wrong"

    rows = _rows(out.values) if table_found else {}
    seen: Counter[str] = Counter()
    outcomes: list[ValueOutcome] = []
    null_values = 0
    for line in sorted(gold.lines, key=lambda ln: ln.row_order):
        key = norm_label(line.label_raw)
        occurrence = seen[key]
        seen[key] += 1
        row = rows[key][occurrence] if occurrence < len(rows.get(key, [])) else None
        unused = list(row or [])
        for gv in line.values:
            if gv.value is None:
                null_values += 1
                continue
            exact = False
            label_value = False
            located: ExtractedValue | None = None
            if out.table_index is None:
                failure: str | None = "no_table"
                detail = out.not_found_reason or "extractor found no table"
            elif not table_found:
                failure = "wrong_table"
                detail = f"extractor table {out.table_index}"
            elif row is None:
                failure = "label_not_found"
                detail = f"no extractor row labelled {line.label_raw!r}"
            else:
                bound = [
                    v
                    for v in row
                    if resolve_period(v.period, gold.periods)[0] == gv.period_id
                ]
                equal = [v for v in row if v.value == gv.value]
                exact = bool(bound) and all(v.value == gv.value for v in bound)
                spare = [v for v in unused if v.value == gv.value]
                if spare:  # period-agnostic: each extractor value matches once
                    unused.remove(spare[0])
                    label_value = True
                same_size = [v for v in row if abs(v.value) == abs(gv.value)]
                if exact:
                    located = bound[0]
                elif equal or same_size:
                    located = (equal or same_size)[0]
                if exact:
                    failure, detail = None, ""
                elif equal:
                    failure = resolve_period(equal[0].period, gold.periods)[1]
                    if failure == "ok":  # bound to the period, but conflicting
                        failure = "period_conflict"
                    detail = f"period string {equal[0].period!r}"
                elif not row:
                    failure, detail = "row_without_values", ""
                else:
                    failure = "value_mismatch"
                    detail = "row values " + ", ".join(v.value_raw for v in row)

            gold_dir = _direction(line.sign * gv.value) if gv.value else 0
            sign_detail = ""
            if gv.value == 0:
                sign_ok: bool | None = None
                sign_failure = None
            elif located is None:
                sign_ok, sign_failure = False, "not_located"
                sign_detail = f"line match failed: {failure}"
            else:
                sign_ok = located.direction == gold_dir
                sign_failure = None if sign_ok else "direction_wrong"
                sign_detail = (
                    f"cell {located.value_raw!r} read as {located.direction:+d}, "
                    f"gold contribution {gold_dir:+d} (line sign {line.sign:+d})"
                )

            outcomes.append(
                ValueOutcome(
                    ticker=gold.ticker,
                    accession=gold.accession,
                    row_order=line.row_order,
                    label=line.label_raw,
                    period_id=gv.period_id,
                    value_raw=gv.value_raw,
                    verified_by=gv.verified_by.value,
                    table_found=table_found,
                    scale_ok=scale_ok,
                    scale_failure=scale_failure,
                    line_exact=exact,
                    line_label_value=label_value,
                    line_failure=failure,
                    sign_ok=sign_ok,
                    sign_failure=sign_failure,
                    line_detail=detail,
                    scale_detail=scale_detail,
                    sign_detail=sign_detail,
                )
            )

    rank = (
        out.candidate_tables.index(gold.table.table_index) + 1
        if gold.table.table_index in out.candidate_tables
        else None
    )
    return ReleaseScore(
        ticker=gold.ticker,
        accession=gold.accession,
        gold_table=gold.table.table_index,
        extractor_table=out.table_index,
        gold_table_rank=rank,
        candidate_tables=out.candidate_tables,
        extractor_title=out.table_title,
        gold_scale=gold.scale.value,
        extractor_scale=out.scale.value if out.scale else None,
        scale_reason=out.scale_reason,
        not_found_reason=out.not_found_reason,
        null_values=null_values,
        outcomes=tuple(outcomes),
    )


# ---------------------------------------------------------------- aggregation


def _rate(correct: int, n: int) -> dict[str, Any]:
    return {"n": n, "correct": correct, "rate": round(correct / n, 4) if n else None}


def _metric(outcomes: Sequence[ValueOutcome], ok: str) -> dict[str, Any]:
    def count(items: Iterable[ValueOutcome]) -> dict[str, Any]:
        scored = [getattr(o, ok) for o in items if getattr(o, ok) is not None]
        return _rate(sum(1 for s in scored if s), len(scored))

    return {
        "overall": count(outcomes),
        "by_verified_by": {
            g: count(o for o in outcomes if o.verified_by == g) for g in GROUPS
        },
    }


def _example(o: ValueOutcome, detail: str) -> str:
    text = (
        f"{o.ticker} {o.accession} line {o.row_order} {o.label!r} "
        f"{o.period_id} = {o.value_raw}"
    )
    return f"{text}: {detail}" if detail else text


def _failures(
    outcomes: Sequence[ValueOutcome], metric: str, examples: int
) -> dict[str, Any]:
    field_name, detail_name = f"{metric}_failure", f"{metric}_detail"
    by_cat: dict[str, list[ValueOutcome]] = defaultdict(list)
    for o in outcomes:
        cat = getattr(o, field_name)
        if cat is not None:
            by_cat[cat].append(o)
    return {
        cat: {
            "count": len(items),
            "releases": len({o.accession for o in items}),
            "examples": [
                _example(o, getattr(o, detail_name)) for o in items[:examples]
            ],
        }
        for cat, items in sorted(by_cat.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    }


def aggregate(
    scores: Sequence[ReleaseScore], gold_info: dict[str, Any], examples: int = 5
) -> dict[str, Any]:
    outcomes = [o for s in scores for o in s.outcomes]
    metrics = {
        "table_found": _metric(outcomes, "table_found"),
        "line_exact_match": _metric(outcomes, "line_exact"),
        "line_label_value_match": _metric(outcomes, "line_label_value"),
        "scale_accuracy": _metric(outcomes, "scale_ok"),
        "sign_accuracy": _metric(outcomes, "sign_ok"),
    }
    metrics["table_found"]["releases"] = _rate(
        sum(1 for s in scores if s.extractor_table == s.gold_table), len(scores)
    )
    metrics["scale_accuracy"]["releases"] = _rate(
        sum(1 for s in scores if s.extractor_scale == s.gold_scale), len(scores)
    )
    return {
        "scorer": "tools.eval.score",
        "scorer_version": SCORER_VERSION,
        "extractor": "app.extraction.html.HtmlExtractor (default target_metric)",
        "unit": "gold value (one line x one period); dash placeholders not scored",
        "gold": gold_info,
        "headline_metrics": list(HEADLINE_METRICS),
        "metrics": metrics,
        "failures": {
            "line_exact_match": _failures(outcomes, "line", examples),
            "scale_accuracy": _failures(outcomes, "scale", examples),
            "sign_accuracy": _failures(outcomes, "sign", examples),
        },
        "releases": [
            {
                **{k: v for k, v in asdict(s).items() if k != "outcomes"},
                "values": len(s.outcomes),
                "line_exact": sum(1 for o in s.outcomes if o.line_exact),
            }
            for s in scores
        ],
    }


# ---------------------------------------------------------------- inputs


def label_files(labels_dir: Path) -> list[Path]:
    return sorted(p for p in labels_dir.glob("*.json") if p.name != SCHEMA_FILE.name)


def gold_info(labels_dir: Path, releases: Sequence[GoldRelease]) -> dict[str, Any]:
    digest = hashlib.sha256()
    for path in label_files(labels_dir):
        digest.update(path.name.encode() + b"\0" + path.read_bytes())
    values = [v for r in releases for v in r.all_values()]
    by = Counter(v.verified_by.value for v in values)
    return {
        "releases": len(releases),
        "values": len(values),
        "null_values": sum(1 for v in values if v.value is None),
        "verified_by": {g: by.get(g, 0) for g in GROUPS},
        "labels_sha256": digest.hexdigest(),
    }


def score_gold_set(gold_dir: Path = GOLD_DIR, examples: int = 5) -> dict[str, Any]:
    labels_dir = gold_dir / "labels"
    raw_dir = gold_dir / "raw"
    manifest = yaml.safe_load((raw_dir / "manifest.yaml").read_text(encoding="utf-8"))
    entries = sorted(manifest["releases"], key=lambda e: e["accession"])
    files = {p.stem for p in label_files(labels_dir)}
    if files != {e["accession"] for e in entries}:
        raise ScoreError("label files and manifest releases differ")

    releases: list[GoldRelease] = []
    scores: list[ReleaseScore] = []
    for entry in entries:
        gold = load_release(labels_dir / f"{entry['accession']}.json")
        html = gzip.decompress((raw_dir / entry["path"]).read_bytes())
        if not hashlib.sha256(html).hexdigest() == gold.sha256 == entry["sha256"]:
            raise ScoreError(f"{entry['accession']}: saved exhibit sha256 mismatch")
        out = run_extractor(
            html, gold.accession, gold.exhibit, gold.source_url, gold.cik
        )
        releases.append(gold)
        scores.append(score_release(gold, out))
    return aggregate(scores, gold_info(labels_dir, releases), examples)


# ---------------------------------------------------------------- report


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
        f"labels sha256 {gold['labels_sha256']}",
        "",
        f"{'metric':<24}{'overall':<24}" + "".join(f"{g:<24}" for g in GROUPS),
    ]
    for name in (*HEADLINE_METRICS, *DIAGNOSTIC_METRICS):
        m = report["metrics"][name]
        lines.append(
            f"{name:<24}{_pct(m['overall']):<24}"
            + "".join(f"{_pct(m['by_verified_by'][g]):<24}" for g in GROUPS)
        )
    for name in ("table_found", "scale_accuracy"):
        lines.append(f"{name} by release: {_pct(report['metrics'][name]['releases'])}")
    for metric, cats in report["failures"].items():
        lines += ["", f"{metric} failures:"]
        for cat, info in cats.items():
            lines.append(
                f"  {cat}: {info['count']} values in {info['releases']} releases"
            )
            lines += [f"    e.g. {ex}" for ex in info["examples"][:2]]
    return "\n".join(lines)


# ---------------------------------------------------------------- P0-10 gate


def check_thresholds(report: dict[str, Any], thresholds: dict[str, Any]) -> list[str]:
    """
    Regressions against the recorded baseline; an empty list means the gate passes.

    The thresholds hold an overall rate per headline metric, plus the scorer
    version and gold-label fingerprint they were recorded against. A different
    scorer or gold set is a failure too: comparing rates across them would be
    meaningless, so the baseline must be re-recorded deliberately.
    """
    problems: list[str] = []
    if thresholds.get("scorer_version") != report["scorer_version"]:
        problems.append(
            f"scorer_version {report['scorer_version']} != thresholds "
            f"{thresholds.get('scorer_version')}: re-record the baseline"
        )
    if thresholds.get("labels_sha256") != report["gold"]["labels_sha256"]:
        problems.append("gold labels changed since the baseline: re-record it")
    floors: dict[str, Any] = thresholds.get("metrics") or {}
    for name in sorted(set(floors) - set(HEADLINE_METRICS)):
        problems.append(f"unknown metric in thresholds: {name}")
    for name in HEADLINE_METRICS:
        if name not in floors:
            problems.append(f"no threshold recorded for {name}")
            continue
        rate = report["metrics"][name]["overall"]["rate"]
        if rate is None or rate < float(floors[name]):
            problems.append(f"{name} regressed: {rate} < baseline {floors[name]}")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="write the full report here")
    parser.add_argument("--examples", type=int, default=5, help="per failure class")
    parser.add_argument(
        "--check", type=Path, help="thresholds file; exit 1 on any regression (P0-10)"
    )
    args = parser.parse_args(argv)

    report = score_gold_set(examples=args.examples)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    print(summary(report))
    if args.check:
        thresholds = yaml.safe_load(args.check.read_text(encoding="utf-8"))
        problems = check_thresholds(report, thresholds)
        print()
        for p in problems:
            print(f"GATE FAIL: {p}")
        for name in HEADLINE_METRICS:
            floor = (thresholds.get("metrics") or {}).get(name)
            rate = report["metrics"][name]["overall"]["rate"]
            if floor is not None and rate is not None and rate > float(floor):
                print(f"note: {name} {rate} is above baseline {floor}")
        print(f"gate: {'FAIL' if problems else 'pass'} ({args.check.name})")
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
