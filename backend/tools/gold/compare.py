"""
P0-05b: compare the independent model reading with the P0-05 draft.

For each release, the draft (``eval/gold/drafts``) and Claude's reading
(``eval/gold/model_reading``) are compared on scale, periods, lines (aligned by
normalized label), roles, signs and every value. Output:

- ``eval/gold/compare/<accession>.json``: per-value proposed ``verified_by``
  (``model_agreement`` when the reading agrees *and* the draft value passed both
  P0-05 checks; otherwise ``null``) plus the list of disagreements;
- ``eval/gold/review_queue.md``: everything the owner must look at in P0-06
  (draft exceptions, draft notes, reader/draft disagreements), per release.

Usage (from ``backend/``)::

    python -m tools.gold.compare
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.extraction.scale_and_sign import parse_raw_numeric

GOLD_DIR = Path(__file__).resolve().parents[3] / "eval" / "gold"
DASHES = {"—", "–", "-", "--"}
_FOOTNOTE = re.compile(
    r"\s*\((?:[a-z]|\d{1,2})\)(?:,\s*\((?:[a-z]|\d{1,2})\))*\s*$", re.IGNORECASE
)


def norm_label(label: str) -> str:
    """Case, whitespace, dash and trailing-footnote insensitive label key."""
    text = label.replace("—", "-").replace("–", "-").replace("’", "'")
    text = re.sub(r"^\s*plus:\s*", "", text, flags=re.IGNORECASE)
    previous = None
    while previous != text:
        previous = text
        text = _FOOTNOTE.sub("", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def value_of(raw: str | None) -> Decimal | None:
    if raw is None or raw.strip() in DASHES:
        return None
    parsed = parse_raw_numeric(raw.strip())
    return None if parsed is None else Decimal(str(parsed))


@dataclass
class Comparison:
    accession: str
    ticker: str
    disagreements: list[str] = field(default_factory=list)
    values: list[dict[str, Any]] = field(default_factory=list)


def compare(draft: dict[str, Any], reading: dict[str, Any]) -> Comparison:
    rel = draft["release"]
    out = Comparison(accession=rel["accession"], ticker=rel["ticker"])
    if rel.get("scale") != reading["scale"]:
        out.disagreements.append(
            f"scale: draft {rel.get('scale')!r} vs reading {reading['scale']!r}"
        )
    if norm_label(rel.get("metric_label_raw") or "") != norm_label(
        reading["metric_label_raw"]
    ):
        out.disagreements.append(
            f"headline metric: draft {rel.get('metric_label_raw')!r} vs reading "
            f"{reading['metric_label_raw']!r}"
        )
    d_periods = [p["period_id"] for p in rel["periods"]]
    r_periods = [p["period_id"] for p in reading["periods"]]
    if d_periods != r_periods:
        out.disagreements.append(f"periods: draft {d_periods} vs reading {r_periods}")

    r_lines = {norm_label(ln["label_raw"]): ln for ln in reading["lines"]}
    d_keys = [norm_label(ln["label_raw"]) for ln in rel["lines"]]
    for key in d_keys:
        if key not in r_lines:
            out.disagreements.append(f"line only in draft: {key!r}")
    for key, ln in r_lines.items():
        if key not in d_keys:
            out.disagreements.append(f"line only in reading: {ln['label_raw']!r}")

    shared_periods = [p for p in d_periods if p in r_periods]
    for d_line in rel["lines"]:
        key = norm_label(d_line["label_raw"])
        r_line = r_lines.get(key)
        role_ok = r_line is not None and r_line["role"] == d_line["role"]
        sign_ok = r_line is not None and (
            d_line["role"] != "adjustment" or r_line["sign"] == d_line["sign"]
        )
        if r_line is not None and not role_ok:
            out.disagreements.append(
                f"role of {d_line['label_raw']!r}: draft {d_line['role']} vs reading {r_line['role']}"
            )
        if r_line is not None and role_ok and not sign_ok:
            out.disagreements.append(
                f"sign of {d_line['label_raw']!r}: draft {d_line['sign']} vs reading {r_line['sign']}"
            )
        for v in d_line["values"]:
            pid = v["period_id"]
            agrees = False
            if r_line is not None and pid in shared_periods:
                r_raw = r_line["values"][r_periods.index(pid)]
                d_val, r_val = value_of(v["value_raw"]), value_of(r_raw)
                agrees = d_val == r_val
                if not agrees:
                    out.disagreements.append(
                        f"value {d_line['label_raw']!r} {pid}: draft {v['value_raw']!r} vs "
                        f"reading {r_raw!r}"
                    )
            proposed = (
                "model_agreement"
                if agrees and role_ok and sign_ok and v.get("verified_by") == "tieout"
                else None
            )
            out.values.append(
                {
                    "label_raw": d_line["label_raw"],
                    "period_id": pid,
                    "value_raw": v["value_raw"],
                    "reader_agrees": agrees and role_ok and sign_ok,
                    "draft_verified_by": v.get("verified_by"),
                    "proposed_verified_by": proposed,
                }
            )
    return out


def table_pointer(rel: dict[str, Any]) -> list[str]:
    """Queue lines that let the owner find the selected table on sec.gov."""
    lines = rel["lines"]
    first, last = lines[0], lines[-1]
    # The same row label often recurs (highlights, guidance), so also give the
    # column and the last row's number: together they identify one table.
    periods = rel.get("periods") or []
    column = periods[0]["label_raw"] if periods else None

    def number(line: dict[str, Any]) -> str | None:
        return next((v["value_raw"] for v in line["values"] if v["value_raw"]), None)

    first_value, last_value = number(first), number(last)
    return [
        f"- open: {rel['source_url']}",
        f"- look for the table starting with **{first['label_raw']}**"
        + (f" (first number: {first_value})" if first_value else "")
        + f" and ending with **{last['label_raw']}**"
        + (f" (first number: {last_value})" if last_value else "")
        + (f"; first column: {column}" if column else ""),
        (
            f"- [ ] that table is the headline {rel.get('metric_label_raw')} bridge"
            f" (table {rel['table']['table_index']}, counted from 0)"
        ),
    ]


def main() -> int:
    compare_dir = GOLD_DIR / "compare"
    compare_dir.mkdir(parents=True, exist_ok=True)
    queue: list[str] = [
        "# Gold-set review queue (P0-06)",
        "",
        "Generated by `python -m tools.gold.compare`. For every release: open the link,",
        "find the table described, tick the box if it is the main Adjusted EBITDA",
        "reconciliation (otherwise write which table it should be). Then resolve any",
        "other item listed. Values not listed here were verified by both P0-05 checks",
        "*and* agreed with the independent reading (P0-05b).",
        "",
    ]
    header_len = len(queue)
    totals = {"values": 0, "model_agreement": 0, "releases_clear": 0}
    for draft_path in sorted((GOLD_DIR / "drafts").glob("*.json")):
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        reading_path = GOLD_DIR / "model_reading" / draft_path.name
        if not reading_path.exists():
            print(f"{draft_path.stem}: no model reading")
            return 1
        reading = json.loads(reading_path.read_text(encoding="utf-8"))
        result = compare(draft, reading)
        agree = sum(
            v["proposed_verified_by"] == "model_agreement" for v in result.values
        )
        totals["values"] += len(result.values)
        totals["model_agreement"] += agree
        items = (
            [f"- [ ] draft exception: {e}" for e in draft["exceptions"]]
            + [f"- [ ] draft note: {n}" for n in draft.get("notes", [])]
            + [f"- [ ] disagreement: {d}" for d in result.disagreements]
        )
        totals["releases_clear"] += not items
        queue.append(f"## {result.ticker} `{result.accession}`")
        queue.append("")
        queue.extend(table_pointer(draft["release"]))
        queue.extend(items or ["- nothing else to resolve"])
        queue.append(f"- values with model agreement: {agree} / {len(result.values)}")
        queue.append("")
        (compare_dir / draft_path.name).write_text(
            json.dumps(
                {
                    "ticket": "P0-05b",
                    "accession": result.accession,
                    "ticker": result.ticker,
                    "disagreements": result.disagreements,
                    "values": result.values,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(
            f"{result.ticker:5} {result.accession} agree={agree}/{len(result.values)} "
            f"disagreements={len(result.disagreements)}"
        )
    queue.insert(
        header_len,
        f"**Summary:** {totals['model_agreement']} / {totals['values']} values have "
        f"`model_agreement`; {totals['releases_clear']} / 30 releases need only the table "
        "confirmation.\n",
    )
    (GOLD_DIR / "review_queue.md").write_text("\n".join(queue) + "\n", encoding="utf-8")
    print(f"model_agreement {totals['model_agreement']}/{totals['values']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
