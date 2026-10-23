"""
P0-05: auto-draft each gold release's headline bridge and verify it.

For every release in the P0-03 manifest this tool:

1. reads the saved exhibit and the approved table (``eval/gold/issuers.yaml``);
2. extracts the headline Adjusted EBITDA bridge: every period column, the GAAP
   starting line, adjustments, subtotals and the headline total;
3. runs two independent checks per period:
   (a) **sum tie-out**: start + adjustments (contribution = sign x value) equals
       the stated total within max(1, ceil(n/2)) units of the reported scale;
   (b) **GAAP anchor**: the starting line equals the XBRL ``companyfacts`` value
       for the same CIK, period end, duration and unit;
4. writes ``eval/gold/drafts/<accession>.json``: draft labels in the P0-04 shape,
   check results, and an exception list for the owner (P0-06).

A value gets ``verified_by="tieout"`` only when *both* checks pass for its
period; otherwise ``verified_by`` is null and the period appears as an exception.
Drafts are inputs to P0-05b / P0-06; they are not gold labels until promoted.

The bridge engine itself lives in ``app.extraction.bridge.core`` (P2-01).

Usage (from ``backend/``, with ``SEC_USER_AGENT`` set for the XBRL fetch)::

    python -m tools.gold.draft
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import yaml
from app.extraction.bridge.core import (
    Draft,
    DraftLine,
    PeriodColumn,
    Row,
    SumCheck,
    anchor_check,
    build_rows,
    derived_ltm,
    detect_scale,
    extract_bridge,
    merge_split_parentheses,
    parse_period,
    period_columns,
    run_anchor,
    solve,
    tolerance,
)
from app.extraction.bridge.models import LineRole
from app.extraction.html.table_parser import extract_html_tables
from app.extraction.scale_and_sign import UnitScale
from app.ingestion.edgar.client import EdgarClient
from bs4 import BeautifulSoup
from pydantic import ValidationError

from tools.gold.labels import GoldRelease, Scale

__all__ = [
    "Draft",
    "DraftLine",
    "PeriodColumn",
    "Row",
    "SumCheck",
    "anchor_check",
    "build_rows",
    "derived_ltm",
    "draft_release",
    "extract_bridge",
    "merge_split_parentheses",
    "parse_period",
    "period_columns",
    "solve",
    "tolerance",
]

GOLD_DIR = Path(__file__).resolve().parents[3] / "eval" / "gold"
DRAFTS_DIR = GOLD_DIR / "drafts"
LABELER = "extractor (tools.gold.draft)"

_SCALE_TO_LABEL = {
    UnitScale.UNITS: Scale.units,
    UnitScale.THOUSANDS: Scale.thousands,
    UnitScale.MILLIONS: Scale.millions,
    UnitScale.BILLIONS: Scale.billions,
}


# ---------------------------------------------------------------- output


def verified_periods(draft: Draft) -> set[str]:
    sums = {c.period_id for c in draft.sum_checks if c.passed}
    anchors = {a["period_id"] for a in draft.anchor_checks if a["status"] == "pass"}
    return sums & anchors


def release_payload(
    draft: Draft, entry: dict[str, Any], table_index: int, today: date
) -> dict[str, Any]:
    ok = verified_periods(draft)
    periods = [
        {
            "period_id": c.period_id,
            "label_raw": c.header,
            "end_date": c.end_date.isoformat() if c.end_date else None,
            "months": c.months,
        }
        for c in draft.periods
    ]
    lines = []
    for order, line in enumerate(draft.lines):
        values = []
        for col, raw, value in zip(draft.periods, line.raw, line.values, strict=True):
            values.append(
                {
                    "period_id": col.period_id,
                    "value_raw": raw,
                    "value": None if value is None else str(value),
                    "verified_by": "tieout" if col.period_id in ok else None,
                    "labeler": LABELER,
                    "labeled_on": today.isoformat(),
                }
            )
        lines.append(
            {
                "row_order": order,
                "label_raw": line.label,
                "role": line.role.value,
                "sign": line.sign,
                "values": values,
            }
        )
    total = next((ln for ln in draft.lines if ln.role is LineRole.total), None)
    return {
        "schema_version": 1,
        "ticker": entry["ticker"],
        "cik": entry["cik"],
        "accession": entry["accession"],
        "exhibit": entry["exhibit"],
        "source_url": entry["url"],
        "sha256": entry["sha256"],
        "metric_label_raw": total.label if total else None,
        "scale": _SCALE_TO_LABEL[draft.scale].value
        if draft.scale in _SCALE_TO_LABEL
        else None,
        "scale_quote": draft.scale_quote,
        "table": {"table_index": table_index, "caption_raw": None},
        "periods": periods,
        "lines": lines,
    }


def schema_problems(payload: dict[str, Any]) -> list[str]:
    """Validate the draft against P0-04, treating null verified_by as pending."""
    probe = json.loads(json.dumps(payload))
    for line in probe.get("lines", []):
        for v in line["values"]:
            v["verified_by"] = v["verified_by"] or "tieout"
    try:
        GoldRelease.model_validate(probe)
    except ValidationError as exc:
        return [
            f"schema: {e['msg']} at {'.'.join(str(p) for p in e['loc'])}"
            for e in exc.errors()
        ]
    return []


def draft_release(
    entry: dict[str, Any],
    issuer_release: dict[str, Any],
    html: bytes,
    facts: dict[str, Any] | None,
    fiscal_year_end: str | None = None,
) -> tuple[dict[str, Any], Draft]:
    soup = BeautifulSoup(html, "lxml")
    table_index = int(issuer_release["table_index"])
    tables = {t.index: t for t in extract_html_tables(soup)}
    draft = Draft(accession=entry["accession"])
    table = tables.get(table_index)
    if table is None:
        draft.exceptions.append(f"table {table_index} not found")
        return {"exceptions": draft.exceptions}, draft

    extract_bridge(table, issuer_release["metric_label"], draft, fiscal_year_end or "")
    if draft.lines:
        tag = soup.find_all("table")[table_index]
        preceding = " ".join(
            s.strip()
            for s in list(tag.find_all_previous(string=True, limit=40))
            if s.strip()
        )
        detect_scale(table, draft.lines[0].row_idx, preceding, draft)
    if facts is not None:
        run_anchor(draft, facts)
    else:
        draft.exceptions.append("XBRL company facts unavailable")

    payload = release_payload(draft, entry, table_index, datetime.now(UTC).date())
    problems = schema_problems(payload)
    if problems:
        draft.exceptions.append(
            f"schema: {len(problems)} problem(s), first: {problems[0]}"
        )
    out = {
        "ticket": "P0-05",
        "generated_by": "tools.gold.draft",
        "generated_on": datetime.now(UTC).date().isoformat(),
        "status": "ok" if not draft.exceptions else "exceptions",
        "release": payload,
        "checks": {
            "direction": draft.direction,
            "sum": [
                {
                    "period_id": c.period_id,
                    "expected": str(c.expected),
                    "computed": str(c.computed),
                    "tolerance": str(c.tolerance),
                    "lines_summed": c.lines_summed,
                    "passed": c.passed,
                }
                for c in draft.sum_checks
            ],
            "anchor": draft.anchor_checks,
        },
        "exceptions": draft.exceptions,
        "notes": draft.notes,
    }
    return out, draft


def _issuer_releases(issuers: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for issuer in issuers["selected"]:
        for rel in issuer["releases"]:
            out[rel["accession"]] = {
                **rel,
                "fiscal_year_end": issuer.get("fiscal_year_end"),
            }
    return out


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-xbrl", action="store_true", help="skip the GAAP anchor fetch"
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    manifest = yaml.safe_load(
        (GOLD_DIR / "raw" / "manifest.yaml").read_text(encoding="utf-8")
    )
    issuers = _issuer_releases(
        yaml.safe_load((GOLD_DIR / "issuers.yaml").read_text(encoding="utf-8"))
    )
    client = None if args.no_xbrl else EdgarClient()
    facts_by_cik: dict[str, dict[str, Any]] = {}
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    clean = 0
    for entry in manifest["releases"]:
        html = gzip.decompress((GOLD_DIR / "raw" / entry["path"]).read_bytes())
        facts = None
        if client is not None:
            if entry["cik"] not in facts_by_cik:
                facts_by_cik[entry["cik"]] = client.get_company_facts(entry["cik"])
            facts = facts_by_cik[entry["cik"]]
        issuer_release = issuers[entry["accession"]]
        out, draft = draft_release(
            entry, issuer_release, html, facts, issuer_release["fiscal_year_end"]
        )
        (DRAFTS_DIR / f"{entry['accession']}.json").write_text(
            json.dumps(out, indent=2) + "\n", encoding="utf-8"
        )
        sums = sum(c.passed for c in draft.sum_checks)
        anchors = sum(a["status"] == "pass" for a in draft.anchor_checks)
        clean += not draft.exceptions
        print(
            f"{entry['ticker']:5} {entry['accession']} periods={len(draft.periods)} "
            f"lines={len(draft.lines)} sum={sums}/{len(draft.sum_checks)} "
            f"anchor={anchors}/{len(draft.anchor_checks)} exceptions={len(draft.exceptions)}"
        )
    print(f"{clean}/{len(manifest['releases'])} releases with no exceptions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
