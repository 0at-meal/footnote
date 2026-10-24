"""
A-19: the earnings-night credit brief, deterministic sections only.

For one issuer's release (default: its latest), the brief gathers what the
snapshot read model already holds, with no new arithmetic:

- **headline**: the release's quarter, reported vs normalized EBITDA under the
  current policy (a preview while the policy is a draft) and add-back intensity;
- **changes**: reconciling lines added, dropped or renamed, metric renames and
  layout changes versus the previous release;
- **recasts**: earlier periods this release restated;
- **recurring add-backs**: "non-recurring" items the recurrence rule flags;
- **peers**: the issuer's add-back intensity against its sector's;
- **tie-out exceptions** recorded for the release.

Every item keeps its sec.gov link. The ``narrative`` and
``questions_for_management`` slots stay empty: the agent writes them later, by
reference (ADR-011). This module never calls a model.

Usage (from ``backend/``)::

    python -m app.analytics.brief TDG [--accession ...] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from app.analytics.snapshot import build_snapshot
from app.store.db import Store

NARRATIVE_PENDING = "not_generated: written by the agent by reference (not in A-19)"
_CHANGE_TYPES = ("added", "removed", "renamed", "metric_renamed", "layout_changed")


def build_brief(
    snapshot: dict[str, Any], ticker: str, accession: str | None = None
) -> dict[str, Any]:
    issuer = next(
        (i for i in snapshot["issuers"] if i["ticker"].upper() == ticker.upper()), None
    )
    if issuer is None:
        return {"ticker": ticker, "status": "not_found", "reason": "not_covered"}
    releases = sorted(issuer["releases"], key=lambda r: (r["filed"], r["accession"]))
    release = (
        next((r for r in releases if r["accession"] == accession), None)
        if accession
        else (releases[-1] if releases else None)
    )
    if release is None:
        return {
            "ticker": issuer["ticker"],
            "status": "not_found",
            "reason": "no such release",
        }
    acc = release["accession"]
    brief: dict[str, Any] = {
        "ticker": issuer["ticker"],
        "name": issuer["name"],
        "sector": issuer["sector"],
        "status": "ok",
        "release": {
            k: release.get(k)
            for k in (
                "accession",
                "filed",
                "url",
                "status",
                "reason",
                "metric_label",
                "scale",
            )
        },
        "headline": _headline(issuer, acc, release["filed"]),
        "changes": [
            i
            for i in snapshot["feed"]
            if i["ticker"] == issuer["ticker"]
            and i["type"] in _CHANGE_TYPES
            and i.get("accession") == acc
        ],
        "recasts": [r for r in issuer["recasts"] if r.get("latest_accession") == acc],
        "recurring_addbacks": [
            i
            for i in snapshot["feed"]
            if i["ticker"] == issuer["ticker"]
            and i["type"] == "recurring_addback"
            and i.get("accession") == acc
        ],
        "peers": _peers(snapshot, issuer),
        "tieout_exceptions": list(release.get("exceptions") or []),
        "narrative": None,
        "questions_for_management": None,
        "narrative_status": NARRATIVE_PENDING,
    }
    return brief


def _headline(issuer: dict[str, Any], accession: str, filed: str) -> dict[str, Any]:
    """The quarter this release reports, as currently served. The snapshot keeps
    each quarter's latest release; a quarter that ended more than 120 days
    before the filing is a comparative column, not the release's own quarter."""
    quarters = [q for q in issuer["quarters"] if q["accession"] == accession]
    own = [
        q
        for q in quarters
        if 0
        <= (date.fromisoformat(filed) - date.fromisoformat(q["end_date"])).days
        <= 120
    ]
    if not own:
        return {
            "status": "unavailable",
            "reason": "no current verified quarter from this release (no bridge, a "
            "failed tie-out, or a later release restated it)",
        }
    q = max(own, key=lambda x: x["end_date"])
    norm = q.get("normalization") or {}
    return {
        "status": "ok",
        "period_id": q["period_id"],
        "metric_label": q["metric_label"],
        "scale": q["scale"],
        "reported": norm.get("reported_total"),
        "normalized": norm.get("normalized"),
        "excluded": norm.get("excluded"),
        "normalization_status": norm.get("status"),
        "normalization_reason": norm.get("reason"),
        "policy_version": norm.get("policy_version"),
        "preview": norm.get("preview"),
        "pending_review": norm.get("pending_review"),
        "addback_intensity": q.get("addback_intensity"),
        "url": q["exhibit_url"],
    }


def _peers(snapshot: dict[str, Any], issuer: dict[str, Any]) -> dict[str, Any]:
    sector = snapshot["peers"].get(issuer["sector"])
    if not sector:
        return {"status": "unavailable", "reason": "no sector peers computed"}
    rows = [p for p in sector["issuers"] if p.get("addback_intensity") is not None]
    mine = next((p for p in rows if p["ticker"] == issuer["ticker"]), None)
    if mine is None:
        return {
            "status": "unavailable",
            "reason": "no add-back intensity for the issuer",
        }
    ordered = sorted(rows, key=lambda p: -p["addback_intensity"])
    return {
        "status": "ok",
        "sector": issuer["sector"],
        "period_id": mine["period_id"],
        "addback_intensity": mine["addback_intensity"],
        "sector_median": sector.get("median_addback_intensity"),
        "rank": next(
            i for i, p in enumerate(ordered, 1) if p["ticker"] == issuer["ticker"]
        ),
        "of": len(ordered),
    }


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def _m(v: float | None) -> str:
    if v is None:
        return "—"
    s = f"{abs(v) / 1e6:,.1f}"
    return f"({s})" if v < 0 else s


def to_markdown(brief: dict[str, Any]) -> str:
    if brief["status"] != "ok":
        return f"# {brief['ticker']}\n\nNo brief: {brief['reason']}.\n"
    r, h, p = brief["release"], brief["headline"], brief["peers"]
    out = [
        f"# {brief['ticker']} — earnings release filed {r['filed']}",
        f"{brief['name']} · {brief['sector']} · [EX-99.1]({r['url']})",
        "",
        "## Headline",
    ]
    if h["status"] == "ok":
        normalized = h["normalized"] or f"— ({h['normalization_reason']})"
        preview = " (preview)" if h["preview"] else ""
        headline = (
            f"- {h['metric_label']}, {h['period_id']} ({h['scale']}): reported "
            f"{h['reported']}, normalized {normalized} under {h['policy_version']}"
            f"{preview}"
        )
        out += [headline, f"- Add-back intensity: {_pct(h['addback_intensity'])}"]
    else:
        out.append(f"- Unavailable: {h['reason']}")
    out += ["", "## Changes versus the previous release"]
    out += [
        f"- {c['type'].replace('_', ' ')}: [{c['label']}]({c.get('url') or ''})"
        + (f" (was {c['prior_label']})" if c.get("prior_label") else "")
        for c in brief["changes"]
    ] or ["- None"]
    out += ["", "## Recasts in this release ($m)"]
    out += [
        f"- {x['label']} {x['period_id']}: {_m(x['first_usd'])} → "
        f"[{_m(x['latest_usd'])}]({x.get('latest_url') or ''})"
        for x in brief["recasts"]
    ] or ["- None"]
    out += ["", "## Recurring “non-recurring” add-backs"]
    out += [
        f"- [{x['label']}]({x['url']}) {x['value_raw']} ({x['code']}, {x['treatment']})"
        for x in brief["recurring_addbacks"]
    ] or ["- None"]
    out += ["", "## Peers"]
    out.append(
        f"- Add-back intensity {_pct(p['addback_intensity'])} vs sector median "
        f"{_pct(p['sector_median'])}; rank {p['rank']} of {p['of']} in {p['sector']}"
        if p["status"] == "ok"
        else f"- Unavailable: {p['reason']}"
    )
    out += ["", "## Tie-out exceptions"]
    out += [f"- {e}" for e in brief["tieout_exceptions"]] or ["- None"]
    out += ["", "## Narrative", f"_{brief['narrative_status']}_", ""]
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker")
    parser.add_argument("--accession")
    parser.add_argument("--db", type=Path, default=Path("../var/footnote.db"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not args.db.exists():
        print(f"no store at {args.db}", file=sys.stderr)
        return 1
    brief = build_brief(build_snapshot(Store(args.db)), args.ticker, args.accession)
    print(json.dumps(brief, indent=2, default=str) if args.json else to_markdown(brief))
    return 0 if brief["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
