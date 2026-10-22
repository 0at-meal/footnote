"""
Policy-driven normalized EBITDA (spec v0.1 §5-§7; P3-05, P3-06).

    normalized(q) = reported_total(q) - sum(contribution of adjustment lines
                                            whose resolved treatment is exclude)

Deterministic and itemized: every reversal carries its source line, value as
reported and sec.gov link. Not computed, with an explicit reason, when the
quarter has no verified bridge, a line is unclassified (``OTHER``) or the scale
is unknown. The policy is a versioned file; results record its version.

While the spec is a draft (``status: draft`` in the policy file) every result
is marked ``preview``. Categories from deterministic rules are marked
``pending_review`` until a human confirms them in label memory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from app.analytics.classify import suggest
from app.analytics.history import LineObs, QuarterBridge
from app.store.db import Store

POLICY_DIR = Path(__file__).with_name("policies")
DEFAULT_POLICY = "footnote-default-v0.1"
RULES_VERSION = "rules v0.1 (app.analytics.classify)"


@dataclass(frozen=True)
class Policy:
    version: str
    status: str
    window: int
    threshold: int
    strictness: tuple[str, ...]
    codes: dict[str, dict[str, str]]

    def treatment(self, code: str) -> str:
        return self.codes[code]["treatment"]

    def group(self, code: str) -> str:
        return self.codes[code]["group"]


@cache
def load_policy(name: str = DEFAULT_POLICY) -> Policy:
    data = yaml.safe_load((POLICY_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
    return Policy(
        version=data["policy_version"],
        status=data["status"],
        window=int(data["recurrence"]["window_quarters"]),
        threshold=int(data["recurrence"]["threshold"]),
        strictness=tuple(data["strictness"]),
        codes=data["codes"],
    )


@dataclass(frozen=True)
class Category:
    code: str
    components: tuple[str, ...]
    flags: tuple[str, ...]
    source: str  # rule | human

    @property
    def codes(self) -> tuple[str, ...]:
        return self.components if self.code == "MIXED" else (self.code,)


def category_for(store: Store, cik: str, key: str) -> Category:
    """
    A human decision in label memory wins. Otherwise the current rules decide,
    and label memory is refreshed so it always shows what the rules say now.
    """
    rows = store.query(
        "SELECT code, components, flags, source FROM label_memory "
        "WHERE cik = ? AND line_key = ?",
        (cik, key),
    )
    if not rows or rows[0]["source"] == "rule":
        s = suggest(key)
        if rows and (
            rows[0]["code"],
            tuple(json.loads(rows[0]["components"])),
            tuple(json.loads(rows[0]["flags"])),
        ) == (s.code, s.components, s.flags):
            return Category(s.code, s.components, s.flags, "rule")
        store.set_label(cik, key, s.code, "rule", RULES_VERSION, s.components, s.flags)
        return Category(s.code, s.components, s.flags, "rule")
    r = rows[0]
    return Category(
        r["code"],
        tuple(json.loads(r["components"])),
        tuple(json.loads(r["flags"])),
        r["source"],
    )


def _adds_back(q: QuarterBridge, code: str, cats: dict[str, Category]) -> bool:
    total = sum(
        (
            ln.contribution
            for ln in q.adjustments
            if ln.contribution is not None and code in cats[ln.line_key].codes
        ),
        Decimal(0),
    )
    return total > 0


def recurrence(
    code: str,
    index: int,
    quarters: list[QuarterBridge],
    cats: dict[str, Category],
    policy: Policy,
) -> str:
    """recurring | not_recurring | unknown, over the window ending at quarters[index]."""
    q = quarters[index]
    known = 0
    unknown = 0
    for k in range(policy.window):
        target = q.end_date - timedelta(days=91 * k)
        hit = next((x for x in quarters if abs((x.end_date - target).days) <= 10), None)
        if hit is None:
            unknown += 1
        elif _adds_back(hit, code, cats):
            known += 1
    if known >= policy.threshold:
        return "recurring"
    if known + unknown < policy.threshold:
        return "not_recurring"
    return "unknown"


@dataclass
class LineResult:
    label: str
    line_key: str
    code: str
    components: tuple[str, ...]
    source: str
    value_raw: str
    contribution: Decimal | None
    treatment: str
    recurrence: dict[str, str]
    flags: list[str]
    url: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "code": self.code,
            "components": list(self.components),
            "category_source": self.source,
            "value_raw": self.value_raw,
            "contribution": None
            if self.contribution is None
            else str(self.contribution),
            "treatment": self.treatment,
            "recurrence": self.recurrence,
            "flags": self.flags,
            "url": self.url,
        }


@dataclass
class NormalizedResult:
    cik: str
    period_id: str
    accession: str
    policy_version: str
    preview: bool
    status: str  # computed | not_computed
    reason: str | None
    scale: str | None
    reported_total: Decimal | None
    normalized: Decimal | None
    excluded: Decimal = Decimal(0)
    lines: list[LineResult] = field(default_factory=list)
    pending_review: int = 0

    @property
    def addback_intensity(self) -> Decimal | None:
        """Non-component add-backs as a share of reported Adjusted EBITDA."""
        if not self.reported_total:
            return None
        addbacks = sum(
            (
                ln.contribution
                for ln in self.lines
                if ln.contribution is not None
                and ln.code not in ("DA", "INT", "TAX", "NCI", "NONOP")
            ),
            Decimal(0),
        )
        return addbacks / self.reported_total

    def as_dict(self) -> dict[str, Any]:
        intensity = self.addback_intensity
        return {
            "cik": self.cik,
            "period_id": self.period_id,
            "accession": self.accession,
            "policy_version": self.policy_version,
            "preview": self.preview,
            "status": self.status,
            "reason": self.reason,
            "scale": self.scale,
            "reported_total": None
            if self.reported_total is None
            else str(self.reported_total),
            "normalized": None if self.normalized is None else str(self.normalized),
            "excluded": str(self.excluded),
            "addback_intensity": None
            if intensity is None
            else round(float(intensity), 4),
            "pending_review": self.pending_review,
            "lines": [ln.as_dict() for ln in self.lines],
        }


def _resolve(
    cat: Category, rec: dict[str, str], policy: Policy
) -> tuple[str, list[str]]:
    flags = list(cat.flags)
    treatments: list[str] = []
    for code in cat.codes:
        t = policy.treatment(code)
        if t == "accept-unless-recurring":
            status = rec[code]
            if status == "recurring":
                t = "exclude"
                flags.append(f"{code} recurring")
            elif status == "unknown":
                t = "accept"
                flags.append("recurrence_unknown")
            else:
                t = "accept"
        treatments.append(t)
    order = {t: i for i, t in enumerate(policy.strictness)}
    if "review" in treatments:
        return "review", flags
    return min(treatments, key=lambda t: order.get(t, len(order))), flags


def normalize_issuer(
    store: Store, cik: str, quarters: list[QuarterBridge], policy: Policy | None = None
) -> list[NormalizedResult]:
    policy = policy or load_policy()
    cats: dict[str, Category] = {}
    for q in quarters:
        for ln in q.adjustments:
            if ln.line_key not in cats:
                cats[ln.line_key] = category_for(store, cik, ln.line_key)
    out: list[NormalizedResult] = []
    for i, q in enumerate(quarters):
        out.append(_normalize_quarter(q, i, quarters, cats, policy))
    return out


def _normalize_quarter(
    q: QuarterBridge,
    index: int,
    quarters: list[QuarterBridge],
    cats: dict[str, Category],
    policy: Policy,
) -> NormalizedResult:
    total = q.total
    result = NormalizedResult(
        cik=q.cik,
        period_id=q.period_id,
        accession=q.accession,
        policy_version=policy.version,
        preview=policy.status != "frozen",
        status="computed",
        reason=None,
        scale=q.scale,
        reported_total=total.value if total else None,
        normalized=None,
    )
    for ln in q.adjustments:
        cat = cats[ln.line_key]
        rec = {
            code: recurrence(code, index, quarters, cats, policy)
            for code in cat.codes
            if code in policy.codes
            and policy.treatment(code) == "accept-unless-recurring"
        }
        treatment, flags = _resolve(cat, rec, policy)
        if cat.source == "rule":
            result.pending_review += 1
        result.lines.append(
            LineResult(
                label=ln.label,
                line_key=ln.line_key,
                code=cat.code,
                components=cat.components,
                source=cat.source,
                value_raw=ln.value_raw,
                contribution=ln.contribution,
                treatment=treatment,
                recurrence=rec,
                flags=flags,
                url=ln.url,
            )
        )
    if total is None or total.value is None:
        result.status, result.reason = "not_computed", "no_total"
    elif q.scale is None:
        result.status, result.reason = "not_computed", "scale_unknown"
    elif any(ln.treatment == "review" for ln in result.lines):
        result.status, result.reason = "not_computed", "unclassified_line"
    if result.status == "computed" and total is not None and total.value is not None:
        excluded = sum(
            (
                ln.contribution
                for ln in result.lines
                if ln.treatment == "exclude" and ln.contribution is not None
            ),
            Decimal(0),
        )
        result.excluded = excluded
        result.normalized = total.value - excluded
    return result


def line_obs_category(store: Store, cik: str, ln: LineObs) -> Category:
    return category_for(store, cik, ln.line_key)
