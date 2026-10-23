"""
Read model for the API, the web app and exports.

``build_snapshot`` turns the observation store into one JSON-serializable
document: per issuer, the verified quarterly bridges, normalized EBITDA under
the default policy, recasts and definition changes; across the universe, a
change feed, sector peer statistics and coverage metrics. Every number in it
comes from stored observations or deterministic arithmetic on them, and every
line keeps its as-reported string and sec.gov link.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

from app.analytics.history import (
    TOTAL_KEY,
    QuarterBridge,
    definition_changes,
    quarter_series,
    recasts,
)
from app.analytics.normalize import load_policy, normalize_issuer
from app.config import REPO_ROOT
from app.store.db import Store

GOLD_LABELS_DIR = REPO_ROOT / "eval" / "gold" / "labels"

_MULT = {
    "units": 1,
    "thousands": 1_000,
    "millions": 1_000_000,
    "billions": 1_000_000_000,
}


def _usd(value: Decimal | None, scale: str | None) -> float | None:
    if value is None or scale not in _MULT:
        return None
    return float(value * _MULT[scale])


def _quarter_label(q: QuarterBridge) -> str:
    return q.end_date.isoformat()


def _issuer_doc(store: Store, issuer: dict[str, Any]) -> dict[str, Any]:
    cik = issuer["cik"]
    quarters = quarter_series(store, cik)
    normalized = normalize_issuer(store, cik, quarters)
    qdocs = []
    for q, n in zip(quarters, normalized, strict=True):
        start = q.start
        qdocs.append(
            {
                "period_id": q.period_id,
                "end_date": _quarter_label(q),
                "accession": q.accession,
                "filed": q.filed,
                "exhibit_url": q.exhibit_url,
                "scale": q.scale,
                "metric_label": q.metric_label,
                "start_label": start.label if start else None,
                "start_usd": _usd(start.value if start else None, q.scale),
                "reported_usd": _usd(n.reported_total, q.scale),
                "normalized_usd": _usd(n.normalized, q.scale),
                "excluded_usd": _usd(n.excluded, q.scale),
                "addback_intensity": n.as_dict()["addback_intensity"],
                "normalization": n.as_dict(),
                "sum_check": q.sum_check,
                "anchor_status": q.anchor_status,
                "lines": [
                    {
                        "row_order": ln.row_order,
                        "label": ln.label,
                        "role": ln.role,
                        "sign": ln.sign,
                        "value_raw": ln.value_raw,
                        "value_usd": _usd(ln.value, q.scale),
                        "url": ln.url,
                        "xpath": ln.xpath,
                    }
                    for ln in q.lines
                ],
            }
        )
    rc = [
        {
            "period_id": r.period_id,
            "label": "Headline total" if r.line_key == TOTAL_KEY else r.label,
            "role": r.role,
            "first_accession": r.first_accession,
            "first_filed": r.first_filed,
            "first_usd": float(r.first_value_usd),
            "latest_accession": r.latest_accession,
            "latest_filed": r.latest_filed,
            "latest_usd": float(r.latest_value_usd),
            "delta_usd": float(r.delta_usd),
            "first_url": r.first_url,
            "latest_url": r.latest_url,
        }
        for r in recasts(store, cik)
    ]
    changes = [
        {
            "kind": c.kind,
            "label": c.label,
            "prior_label": c.prior_label,
            "period_id": c.period_id,
            "accession": c.accession,
            "filed": c.filed,
            "prior_accession": c.prior_accession,
            "value_raw": c.value_raw,
            "url": c.url,
        }
        for c in definition_changes(store, cik)
    ]
    bridges = store.query(
        """
        SELECT b.accession, f.filed, f.url, b.status, b.reason, b.metric_label,
               b.scale, b.exceptions, b.table_index
        FROM current_bridges b JOIN filings f USING (accession)
        WHERE f.cik = ? ORDER BY f.filed DESC
        """,
        (cik,),
    )
    return {
        **issuer,
        "quarters": qdocs,
        "recasts": rc,
        "changes": changes,
        "releases": [
            {
                "accession": b["accession"],
                "filed": b["filed"],
                "url": b["url"],
                "status": b["status"],
                "reason": b["reason"],
                "metric_label": b["metric_label"],
                "scale": b["scale"],
                "table_index": b["table_index"],
                "exceptions": json.loads(b["exceptions"]),
            }
            for b in bridges
        ],
    }


def gold_accessions(labels_dir: Path = GOLD_LABELS_DIR) -> set[str]:
    """Accessions of the gold set (one ``<accession>.json`` label file each)."""
    if not labels_dir.is_dir():
        return set()
    return {p.stem for p in labels_dir.glob("*.json")}


def _coverage(store: Store, gold: set[str]) -> dict[str, Any]:
    def one(sql: str) -> Any:
        return store.query(sql)[0][0]

    per_bridge = store.query(
        """
        SELECT b.bridge_id, b.accession, b.status,
               SUM(c.kind = 'sum') AS n_sum, SUM(c.kind = 'sum' AND c.status = 'pass') AS p_sum,
               SUM(c.kind = 'anchor') AS n_anchor,
               SUM(c.kind = 'anchor' AND c.status = 'pass') AS p_anchor
        FROM current_bridges b LEFT JOIN checks c USING (bridge_id)
        GROUP BY b.bridge_id
        """
    )
    found = [r for r in per_bridge if r["status"] != "not_found"]
    held = [r for r in per_bridge if r["accession"] not in gold]
    held_found = [r for r in held if r["status"] != "not_found"]
    checks = Counter(
        (r["kind"], r["status"])
        for r in store.query(
            "SELECT kind, status FROM checks "
            "WHERE bridge_id IN (SELECT bridge_id FROM current_bridges)"
        )
    )
    failures = store.query(
        """
        SELECT f.stage, f.reason, f.accession, i.ticker FROM failures f
        LEFT JOIN issuers i USING (cik)
        WHERE f.run_id = (SELECT MAX(run_id) FROM runs WHERE finished_at IS NOT NULL)
        """
    )
    return {
        "issuers": one("SELECT COUNT(*) FROM issuers"),
        "releases_seen": one("SELECT COUNT(*) FROM filings"),
        "bridges": len(per_bridge),
        "bridges_found": len(found),
        "bridges_all_periods_tie": sum(
            1 for r in found if r["n_sum"] and r["p_sum"] == r["n_sum"]
        ),
        "held_out": {
            "gold_releases": len(per_bridge) - len(held),
            "releases": len(held),
            "bridges_found": len(held_found),
            "bridges_all_periods_tie": sum(
                1 for r in held_found if r["n_sum"] and r["p_sum"] == r["n_sum"]
            ),
        },
        "observations": one(
            "SELECT COUNT(*) FROM observations "
            "WHERE bridge_id IN (SELECT bridge_id FROM current_bridges)"
        ),
        "sum_checks": {
            "pass": checks[("sum", "pass")],
            "fail": checks[("sum", "fail")],
        },
        "anchor_checks": {
            s: checks[("anchor", s)] for s in ("pass", "mismatch", "unavailable")
        },
        "label_memory": {
            r["source"]: r["n"]
            for r in store.query(
                "SELECT source, COUNT(*) AS n FROM label_memory GROUP BY source"
            )
        },
        "failures": [dict(r) for r in failures],
        "last_run": dict(
            store.query("SELECT * FROM runs ORDER BY run_id DESC LIMIT 1")[0]
        )
        if one("SELECT COUNT(*) FROM runs")
        else None,
    }


def _peers(issuers: list[dict[str, Any]]) -> dict[str, Any]:
    """Latest-quarter add-back mix by sector, from each issuer's normalized lines."""
    by_sector: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for doc in issuers:
        if not doc["quarters"]:
            continue
        q = doc["quarters"][-1]
        n = q["normalization"]
        reported = q["reported_usd"]
        mix: dict[str, float] = defaultdict(float)
        for ln in n["lines"]:
            if ln["contribution"] is None or ln["code"] in ("DA", "INT", "TAX", "NCI"):
                continue
            v = _usd(Decimal(ln["contribution"]), q["scale"]) or 0.0
            mix[ln["code"]] += v
        by_sector[doc["sector"] or "Other"].append(
            {
                "ticker": doc["ticker"],
                "period_id": q["period_id"],
                "reported_usd": reported,
                "normalized_usd": q["normalized_usd"],
                "addback_intensity": q["addback_intensity"],
                "mix_usd": dict(mix),
            }
        )
    out = {}
    for sector, rows in sorted(by_sector.items()):
        vals = [
            r["addback_intensity"] for r in rows if r["addback_intensity"] is not None
        ]
        out[sector] = {
            "issuers": rows,
            "median_addback_intensity": median(vals) if vals else None,
        }
    return out


_RAW_NUMBER = re.compile(r"^\(?-?[0-9][0-9,]*(?:\.[0-9]+)?\)?$")


def raw_usd(value_raw: str | None, scale: str | None) -> float | None:
    """An as-reported cell ("(1,431)", "$ 12.5") in USD, or None if it is not a number."""
    if not value_raw:
        return None
    s = value_raw.replace("$", "").replace("−", "-").replace(" ", "").strip()
    if not _RAW_NUMBER.match(s):
        return None
    neg = s.startswith("(") and s.endswith(")")
    num = Decimal(s.strip("()").replace(",", ""))
    return _usd(-num if neg else num, scale)


def _moves(
    before: float | None, after: float | None, impact: float | None
) -> dict[str, float | None]:
    delta = None
    if before is not None or after is not None:
        delta = (after or 0.0) - (before or 0.0)
    return {
        "before_usd": before,
        "after_usd": after,
        "delta_usd": delta,
        "impact_usd": impact,
    }


def _feed(issuers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Every change across the universe. ``impact_usd`` (the size of the move, in
    USD, used to rank the inbox) is plain arithmetic on as-reported values and
    the release's stated scale; it is None where a change carries no amount.
    """
    items: list[dict[str, Any]] = []
    for doc in issuers:
        scale_of = {r["accession"]: r["scale"] for r in doc["releases"]}
        for r in doc["recasts"]:
            items.append(
                {
                    "type": "recast",
                    "ticker": doc["ticker"],
                    "filed": r["latest_filed"],
                    **r,
                    **_moves(r["first_usd"], r["latest_usd"], abs(r["delta_usd"])),
                }
            )
        for c in doc["changes"]:
            if c["kind"] == "added":
                v = raw_usd(c["value_raw"], scale_of.get(c["accession"]))
                mv = _moves(None, v, abs(v) if v is not None else None)
            elif c["kind"] == "removed":
                v = raw_usd(c["value_raw"], scale_of.get(c["prior_accession"]))
                mv = _moves(v, None, abs(v) if v is not None else None)
            else:
                mv = _moves(None, None, None)
            items.append({"type": c["kind"], "ticker": doc["ticker"], **c, **mv})
        if doc["quarters"]:
            q = doc["quarters"][-1]
            for ln in q["normalization"]["lines"]:
                if any(f.endswith("recurring") for f in ln["flags"]):
                    v = raw_usd(ln["value_raw"], q["scale"])
                    items.append(
                        {
                            "type": "recurring_addback",
                            "ticker": doc["ticker"],
                            "filed": q["filed"],
                            "period_id": q["period_id"],
                            "accession": q["accession"],
                            "label": ln["label"],
                            "code": ln["code"],
                            "value_raw": ln["value_raw"],
                            "treatment": ln["treatment"],
                            "url": ln["url"],
                            **_moves(None, v, abs(v) if v is not None else None),
                        }
                    )
    return sorted(items, key=lambda i: i.get("filed") or "", reverse=True)


def build_snapshot(store: Store, gold: set[str] | None = None) -> dict[str, Any]:
    """``gold``: gold-set accessions, excluded from the held-out counts."""
    issuers = [
        dict(r)
        for r in store.query(
            "SELECT cik, ticker, name, fiscal_year_end, sector FROM issuers ORDER BY ticker"
        )
    ]
    docs = [_issuer_doc(store, i) for i in issuers]
    policy = load_policy()
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "policy": {
            "version": policy.version,
            "status": policy.status,
            "codes": policy.codes,
        },
        "coverage": _coverage(store, gold_accessions() if gold is None else gold),
        "issuers": docs,
        "feed": _feed(docs),
        "peers": _peers(docs),
    }
