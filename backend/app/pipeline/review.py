"""
Category review (P3-02): turn rule suggestions into human decisions quickly.

``export`` writes one CSV row per distinct label (line key) still decided only
by rules, grouped across issuers, most consequential first:

1. labels whose code changes the normalized number (exclude / review /
   accept-unless-recurring), then flagged ones, then plain accepts;
2. within a group, by total absolute contribution in the latest quarters.

The reviewer fills the ``decision`` column in Excel: ``ok`` confirms the
suggestion, a code (e.g. ``MA``) or ``MIXED:IMPAIR+RESTR`` replaces it, blank
skips the row. ``apply`` records filled rows in label memory as
``source='human'`` with the reviewer's name, for every issuer that uses that
label. Nothing is ever confirmed without a reviewer's entry.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from app.analytics.normalize import load_policy
from app.store.db import Store

FIELDS = [
    "line_key",
    "suggested",
    "components",
    "decision",
    "treatment",
    "issuers",
    "abs_contribution_usd_m",
    "example_label",
    "example_value",
    "source_url",
]
_IMPACT = {"exclude": 0, "review": 0, "accept-unless-recurring": 1, "flag": 2}


@dataclass(frozen=True)
class ApplyResult:
    applied: int
    skipped: int
    errors: list[str]


def export_queue(store: Store, out: Path) -> int:
    policy = load_policy()
    rows = store.query(
        """
        SELECT lm.cik, lm.line_key, lm.code, lm.components, o.label, o.value_raw,
               o.value_usd, o.sign, o.url
        FROM label_memory lm
        JOIN observations o ON o.cik = lm.cik AND o.line_key = lm.line_key
        JOIN current_bridges b ON b.bridge_id = o.bridge_id
        WHERE lm.source = 'rule' AND o.role = 'adjustment'
        """
    )
    groups: dict[str, dict[str, object]] = {}
    issuers: dict[str, set[str]] = defaultdict(set)
    weight: dict[str, Decimal] = defaultdict(Decimal)
    for r in rows:
        key = r["line_key"]
        issuers[key].add(r["cik"])
        if r["value_usd"] is not None:
            weight[key] += abs(Decimal(r["value_usd"]))
        if key not in groups:
            code = r["code"]
            comps = json.loads(r["components"])
            treat = (
                "strictest of " + "+".join(comps)
                if code == "MIXED"
                else policy.codes.get(code, {}).get("treatment", "?")
            )
            groups[key] = {
                "line_key": key,
                "suggested": code,
                "components": "+".join(comps),
                "decision": "",
                "treatment": treat,
                "example_label": r["label"],
                "example_value": r["value_raw"],
                "source_url": r["url"] or "",
            }
    ordered = sorted(
        groups.values(),
        key=lambda g: (
            _IMPACT.get(str(g["treatment"]), 0 if g["suggested"] == "MIXED" else 3),
            -weight[str(g["line_key"])],
        ),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for g in ordered:
            key = str(g["line_key"])
            g["issuers"] = len(issuers[key])
            g["abs_contribution_usd_m"] = f"{weight[key] / Decimal(1_000_000):.1f}"
            w.writerow(g)
    return len(ordered)


def _parse(decision: str, suggested: str, components: str) -> tuple[str, list[str]]:
    d = decision.strip().upper()
    if d == "OK":
        return suggested, [c for c in components.split("+") if c]
    if d.startswith("MIXED:"):
        return "MIXED", [c for c in d.split(":", 1)[1].split("+") if c]
    return d, []


def apply_queue(store: Store, path: Path, reviewer: str) -> ApplyResult:
    if not reviewer.strip():
        raise ValueError("a reviewer name is required: decisions record who made them")
    codes = set(load_policy().codes)
    applied = skipped = 0
    errors: list[str] = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for i, row in enumerate(csv.DictReader(fh), start=2):
            if not (row.get("decision") or "").strip():
                skipped += 1
                continue
            code, comps = _parse(row["decision"], row["suggested"], row["components"])
            bad = [c for c in [code, *comps] if c not in codes]
            if bad or (code == "MIXED" and len(comps) < 2):
                errors.append(
                    f"row {i} ({row['line_key']}): invalid decision {row['decision']!r}"
                )
                continue
            ciks = [
                r["cik"]
                for r in store.query(
                    "SELECT cik FROM label_memory WHERE line_key = ? AND source = 'rule'",
                    (row["line_key"],),
                )
            ]
            for cik in ciks:
                store.set_label(cik, row["line_key"], code, "human", reviewer, comps)
            applied += 1
    return ApplyResult(applied, skipped, errors)
