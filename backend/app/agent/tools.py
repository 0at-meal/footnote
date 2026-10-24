"""
A-09: the agent's read-only tools over the observation store (ADR-011).

Every tool takes an optional ``as_of`` date and sees only filings filed on or
before it, so a question asked "as of" a date is answered with what was public
then. Every value comes back under a stable vid and is added to the session
ledger; every result carries a ``status`` (``ok``, ``not_found``, ``unavailable``,
``invalid``) and, unless ``ok``, a ``reason``. Values that fail a tie-out are
still returned, marked ``verified: false``, never dropped or repaired.

The tools only read (``Store.query``); the boundary test forbids store writes in
``app/agent``. The same tools serve the agent loop and the MCP server (A-18).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent.values import Ledger, Value
from app.analytics.history import quarter_series
from app.analytics.normalize import (
    Category,
    load_policy,
    normalize_quarters,
    recorded_category,
)
from app.extraction.bridge.keys import line_key
from app.store.db import Store

Status = Literal["ok", "not_found", "unavailable", "invalid"]
_FAR_FUTURE = "9999-12-31"


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool: str
    status: Status
    reason: str | None = None
    values: list[Value] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)

    def for_model(self) -> dict[str, Any]:
        """The JSON the model sees: values by vid, never bare numbers alone."""
        out: dict[str, Any] = {"tool": self.tool, "status": self.status}
        if self.reason:
            out["reason"] = self.reason
        if self.values:
            out["values"] = [v.brief() for v in self.values]
        if self.data:
            out["data"] = self.data
        return out


# ---- argument models ----------------------------------------------------------------


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResolveIssuerArgs(_Args):
    query: str = Field(..., min_length=1, description="ticker or part of the name")


class _Issuer(_Args):
    ticker: str = Field(..., min_length=1)
    as_of: date | None = Field(None, description="only filings filed on or before")


class ListReleasesArgs(_Issuer):
    pass


class GetBridgeArgs(_Issuer):
    accession: str | None = None
    filed: date | None = Field(None, description="the release's filing date")
    period_id: str | None = Field(None, description="e.g. 3M-2026-06-30")


class GetLineHistoryArgs(_Issuer):
    period_id: str
    line: str = Field("total", description="'total', 'gaap_start' or a line label")


class GetQuartersArgs(_Issuer):
    line: str = Field("total", description="'total', 'gaap_start' or a line label")
    limit: int = Field(8, ge=1, le=16)


class GetChangesArgs(_Issuer):
    accession: str | None = Field(None, description="default: the latest release")


class GetNormalizedArgs(_Issuer):
    period_id: str | None = Field(None, description="default: the latest quarter")


# ---- the tools ---------------------------------------------------------------------------


class AgentTools:
    def __init__(self, store: Store, ledger: Ledger | None = None) -> None:
        self.store = store
        self.ledger = ledger if ledger is not None else Ledger()
        self._dispatch: dict[str, tuple[type[_Args], Callable[[Any], ToolResult]]] = {
            "resolve_issuer": (ResolveIssuerArgs, self.resolve_issuer),
            "list_releases": (ListReleasesArgs, self.list_releases),
            "get_bridge": (GetBridgeArgs, self.get_bridge),
            "get_line_history": (GetLineHistoryArgs, self.get_line_history),
            "get_quarters": (GetQuartersArgs, self.get_quarters),
            "get_changes": (GetChangesArgs, self.get_changes),
            "get_normalized": (GetNormalizedArgs, self.get_normalized),
        }

    @property
    def names(self) -> list[str]:
        return list(self._dispatch)

    def call(self, name: str, args: dict[str, Any]) -> ToolResult:
        """Validate and run one tool call; a bad call is an ``invalid`` result."""
        entry = self._dispatch.get(name)
        if entry is None:
            return ToolResult(
                tool=name, status="invalid", reason=f"unknown tool {name!r}"
            )
        model, fn = entry
        try:
            parsed = model.model_validate(args)
        except ValidationError as exc:
            return ToolResult(tool=name, status="invalid", reason=str(exc))
        try:
            result = fn(parsed)
        except sqlite3.Error as exc:
            return ToolResult(
                tool=name, status="unavailable", reason=f"store error: {exc}"
            )
        self.ledger.add(result.values)
        return result

    # -- helpers

    def _issuer(self, ticker: str) -> sqlite3.Row | None:
        rows = self.store.query(
            "SELECT * FROM issuers WHERE upper(ticker) = upper(?)", (ticker,)
        )
        return rows[0] if rows else None

    @staticmethod
    def _not_covered(tool: str, ticker: str) -> ToolResult:
        return ToolResult(
            tool=tool,
            status="not_found",
            reason=f"not_covered: {ticker} is not in Footnote's universe",
        )

    def _observations(
        self,
        cik: str,
        as_of: date | None,
        extra: str = "",
        params: tuple[Any, ...] = (),
    ) -> list[sqlite3.Row]:
        cutoff = as_of.isoformat() if as_of else _FAR_FUTURE
        return self.store.query(
            f"""
            SELECT o.bridge_id, o.row_order, o.label, o.line_key, o.role, o.sign,
                   o.period_id, o.value_raw, o.value, o.xpath, o.url, o.accession,
                   o.filed, b.scale, b.metric_label,
                   (SELECT s.status FROM checks s WHERE s.bridge_id = o.bridge_id
                     AND s.kind = 'sum' AND s.period_id = o.period_id) AS sum_status,
                   (SELECT a.status FROM checks a WHERE a.bridge_id = o.bridge_id
                     AND a.kind = 'anchor' AND a.period_id = o.period_id) AS anchor_status,
                   (SELECT p.end_date FROM bridge_periods p WHERE p.bridge_id = o.bridge_id
                     AND p.period_id = o.period_id LIMIT 1) AS end_date
            FROM observations o
            JOIN current_bridges b ON b.bridge_id = o.bridge_id
            WHERE o.cik = ? AND o.filed <= ? {extra}
            ORDER BY o.filed, o.bridge_id, o.row_order
            """,
            (cik, cutoff, *params),
        )

    @staticmethod
    def _value(r: sqlite3.Row, ticker: str) -> Value:
        checks = {
            "sum": r["sum_status"] or "none",
            "anchor": r["anchor_status"] or "none",
        }
        return Value(
            vid=f"obs:{r['bridge_id']}:{r['row_order']}:{r['period_id']}",
            kind="obs",
            ticker=ticker,
            label=r["label"],
            period_id=r["period_id"],
            value=None if r["value"] is None else Decimal(r["value"]),
            value_raw=r["value_raw"],
            unit="usd",
            scale=r["scale"],
            role=r["role"],
            line_key=r["line_key"],
            accession=r["accession"],
            filed=r["filed"],
            url=r["url"],
            xpath=r["xpath"],
            checks=checks,
            verified=r["scale"] is not None
            and checks["sum"] == "pass"
            and checks["anchor"] == "pass",
        )

    @staticmethod
    def _line_filter(line: str) -> tuple[str, tuple[Any, ...]]:
        if line in ("total", "gaap_start"):
            return "AND o.role = ?", (line,)
        return "AND o.line_key = ?", (line_key(line),)

    # -- tools

    def resolve_issuer(self, a: ResolveIssuerArgs) -> ToolResult:
        q = a.query.strip()
        rows = self.store.query(
            "SELECT i.*, (SELECT COUNT(*) FROM filings f WHERE f.cik = i.cik) AS releases,"
            " (SELECT MIN(filed) FROM filings f WHERE f.cik = i.cik) AS first_filed,"
            " (SELECT MAX(filed) FROM filings f WHERE f.cik = i.cik) AS last_filed"
            " FROM issuers i WHERE upper(i.ticker) = upper(?) OR i.name LIKE ?"
            " ORDER BY upper(i.ticker) = upper(?) DESC, i.ticker LIMIT 5",
            (q, f"%{q}%", q),
        )
        if not rows:
            return ToolResult(
                tool="resolve_issuer",
                status="not_found",
                reason=f"not_covered: no issuer in Footnote's universe matches {q!r}",
            )
        return ToolResult(
            tool="resolve_issuer",
            status="ok",
            data={
                "issuers": [
                    {
                        "ticker": r["ticker"],
                        "name": r["name"],
                        "sector": r["sector"],
                        "fiscal_year_end": r["fiscal_year_end"],
                        "releases": r["releases"],
                        "first_filed": r["first_filed"],
                        "last_filed": r["last_filed"],
                    }
                    for r in rows
                ]
            },
        )

    def list_releases(self, a: ListReleasesArgs) -> ToolResult:
        issuer = self._issuer(a.ticker)
        if issuer is None:
            return self._not_covered("list_releases", a.ticker)
        cutoff = a.as_of.isoformat() if a.as_of else _FAR_FUTURE
        rows = self.store.query(
            """
            SELECT f.accession, f.filed, f.url, b.status, b.reason, b.metric_label,
                   b.scale,
                   (SELECT group_concat(DISTINCT o.period_id) FROM observations o
                     WHERE o.bridge_id = b.bridge_id) AS periods
            FROM filings f LEFT JOIN current_bridges b ON b.accession = f.accession
            WHERE f.cik = ? AND f.filed <= ? ORDER BY f.filed
            """,
            (issuer["cik"], cutoff),
        )
        return ToolResult(
            tool="list_releases",
            status="ok" if rows else "not_found",
            reason=None if rows else "no Item 2.02 release filed by as_of",
            data={
                "releases": [
                    {
                        "accession": r["accession"],
                        "filed": r["filed"],
                        "url": r["url"],
                        "bridge": r["status"] or "not_extracted",
                        "reason": r["reason"],
                        "metric": r["metric_label"],
                        "scale": r["scale"],
                        "periods": sorted((r["periods"] or "").split(","))
                        if r["periods"]
                        else [],
                    }
                    for r in rows
                ]
            },
        )

    def get_bridge(self, a: GetBridgeArgs) -> ToolResult:
        issuer = self._issuer(a.ticker)
        if issuer is None:
            return self._not_covered("get_bridge", a.ticker)
        cutoff = a.as_of.isoformat() if a.as_of else _FAR_FUTURE
        where, params = "f.cik = ? AND f.filed <= ?", [issuer["cik"], cutoff]
        if a.accession:
            where += " AND f.accession = ?"
            params.append(a.accession)
        if a.filed:
            where += " AND f.filed = ?"
            params.append(a.filed.isoformat())
        rows = self.store.query(
            f"""
            SELECT f.accession, f.filed, b.status, b.reason, b.metric_label, b.scale
            FROM filings f LEFT JOIN current_bridges b ON b.accession = f.accession
            WHERE {where} ORDER BY f.filed DESC LIMIT 1
            """,
            tuple(params),
        )
        if not rows:
            return ToolResult(
                tool="get_bridge", status="not_found", reason="no such release by as_of"
            )
        rel = rows[0]
        if rel["status"] in (None, "not_found"):
            return ToolResult(
                tool="get_bridge",
                status="unavailable",
                reason=f"no_bridge: {rel['reason'] or 'no bridge was extracted'}",
                data={"accession": rel["accession"], "filed": rel["filed"]},
            )
        extra = "AND o.accession = ?"
        extra_params: tuple[Any, ...] = (rel["accession"],)
        if a.period_id:
            extra += " AND o.period_id = ?"
            extra_params = (*extra_params, a.period_id)
        obs = self._observations(issuer["cik"], a.as_of, extra, extra_params)
        values = [self._value(r, issuer["ticker"]) for r in obs]
        notes = []
        if rel["scale"] is None:
            notes.append("scale_unknown: the bridge's unit could not be read")
        return ToolResult(
            tool="get_bridge",
            status="ok" if values else "not_found",
            reason=None if values else "no values for that period in this release",
            values=values,
            data={
                "accession": rel["accession"],
                "filed": rel["filed"],
                "metric": rel["metric_label"],
                "scale": rel["scale"],
                "notes": notes,
            },
        )

    def get_line_history(self, a: GetLineHistoryArgs) -> ToolResult:
        """One line for one period in every release that reported it, oldest first."""
        issuer = self._issuer(a.ticker)
        if issuer is None:
            return self._not_covered("get_line_history", a.ticker)
        extra, params = self._line_filter(a.line)
        obs = self._observations(
            issuer["cik"],
            a.as_of,
            f"AND o.period_id = ? {extra}",
            (a.period_id, *params),
        )
        per_release: dict[str, list[sqlite3.Row]] = {}
        for r in obs:
            per_release.setdefault(r["accession"], []).append(r)
        values = [
            self._value(rs[0], issuer["ticker"])
            for rs in per_release.values()
            if len(rs) == 1
        ]
        ambiguous = [acc for acc, rs in per_release.items() if len(rs) > 1]
        metrics = sorted({r["metric_label"] or "" for r in obs})
        return ToolResult(
            tool="get_line_history",
            status="ok" if values else "not_found",
            reason=None
            if values
            else f"no release by as_of reports {a.line!r} for {a.period_id}",
            values=values,
            data={
                "releases": len(values),
                "ambiguous_releases": ambiguous,
                "metrics": metrics,
                "note": "values are oldest first; the first is as first reported",
            },
        )

    def get_quarters(self, a: GetQuartersArgs) -> ToolResult:
        """Each 3-month period's line as most recently reported by as_of."""
        issuer = self._issuer(a.ticker)
        if issuer is None:
            return self._not_covered("get_quarters", a.ticker)
        extra, params = self._line_filter(a.line)
        obs = self._observations(
            issuer["cik"], a.as_of, f"AND o.period_id LIKE '3M-%' {extra}", params
        )
        latest: dict[str, list[sqlite3.Row]] = {}
        for r in obs:  # ordered by filed: later releases replace earlier ones
            rows = latest.get(r["period_id"])
            if rows and rows[0]["accession"] != r["accession"]:
                rows = None
            latest[r["period_id"]] = [*(rows or []), r]
        chosen = sorted(
            (rs[0] for rs in latest.values() if len(rs) == 1),
            key=lambda r: r["end_date"] or r["period_id"][3:],
        )[-a.limit :]
        values = [self._value(r, issuer["ticker"]) for r in chosen]
        metrics = sorted({r["metric_label"] or "" for r in chosen})
        notes = []
        if len(metrics) > 1:
            notes.append(f"the quarters report different metrics: {metrics}")
        return ToolResult(
            tool="get_quarters",
            status="ok" if values else "not_found",
            reason=None if values else f"no quarters with line {a.line!r} by as_of",
            values=values,
            data={"metrics": metrics, "notes": notes},
        )

    def get_changes(self, a: GetChangesArgs) -> ToolResult:
        """Reconciling lines added or dropped versus the issuer's previous release."""
        issuer = self._issuer(a.ticker)
        if issuer is None:
            return self._not_covered("get_changes", a.ticker)
        cutoff = a.as_of.isoformat() if a.as_of else _FAR_FUTURE
        filings = self.store.query(
            "SELECT f.accession, f.filed, b.status FROM filings f LEFT JOIN"
            " current_bridges b ON b.accession = f.accession WHERE f.cik = ?"
            " AND f.filed <= ? ORDER BY f.filed",
            (issuer["cik"], cutoff),
        )
        idx = (
            next(
                (i for i, f in enumerate(filings) if f["accession"] == a.accession),
                None,
            )
            if a.accession
            else len(filings) - 1
        )
        if idx is None or idx < 0:
            return ToolResult(
                tool="get_changes", status="not_found", reason="no such release"
            )
        if idx == 0:
            return ToolResult(
                tool="get_changes",
                status="unavailable",
                reason="no previous release in the store",
            )
        cur, prev = filings[idx], filings[idx - 1]
        for f in (cur, prev):
            if f["status"] in (None, "not_found"):
                return ToolResult(
                    tool="get_changes",
                    status="unavailable",
                    reason=f"no_bridge: release {f['accession']} has no extracted bridge",
                )
        lines = {}
        for f in (cur, prev):
            obs = self._observations(
                issuer["cik"],
                a.as_of,
                "AND o.accession = ? AND o.role = 'adjustment'",
                (f["accession"],),
            )
            present: dict[str, Value] = {}
            for r in obs:
                if r["value"] not in (None, "0"):
                    present.setdefault(r["line_key"], self._value(r, issuer["ticker"]))
            lines[f["accession"]] = present
        now, before = lines[cur["accession"]], lines[prev["accession"]]
        added = [now[k] for k in sorted(set(now) - set(before))]
        dropped = [before[k] for k in sorted(set(before) - set(now))]
        return ToolResult(
            tool="get_changes",
            status="ok",
            values=[*added, *dropped],
            data={
                "release": {"accession": cur["accession"], "filed": cur["filed"]},
                "previous": {"accession": prev["accession"], "filed": prev["filed"]},
                "added": [v.label for v in added],
                "dropped": [v.label for v in dropped],
                "note": "a line counts as present with a non-zero amount in any column; "
                "an added and a dropped line may be one renamed line",
            },
        )

    def get_normalized(self, a: GetNormalizedArgs) -> ToolResult:
        """Normalized EBITDA under the current draft policy, current record only."""
        issuer = self._issuer(a.ticker)
        if issuer is None:
            return self._not_covered("get_normalized", a.ticker)
        cik = issuer["cik"]
        if a.as_of is not None:
            later = self.store.query(
                "SELECT 1 FROM filings WHERE cik = ? AND filed > ? LIMIT 1",
                (cik, a.as_of.isoformat()),
            )
            if later:
                return ToolResult(
                    tool="get_normalized",
                    status="unavailable",
                    reason="normalized figures exist for the current record only, "
                    "not as of an earlier date",
                )
        quarters = quarter_series(self.store, cik)
        if not quarters:
            return ToolResult(
                tool="get_normalized", status="not_found", reason="no verified quarters"
            )
        cats: dict[str, Category] = {}
        for q in quarters:
            for ln in q.adjustments:
                if ln.line_key in cats:
                    continue
                cat = recorded_category(self.store, cik, ln.line_key)
                if cat is None:
                    return ToolResult(
                        tool="get_normalized",
                        status="unavailable",
                        reason=f"unclassified_line: no category recorded for {ln.label!r}",
                    )
                cats[ln.line_key] = cat
        policy = load_policy()
        results = normalize_quarters(quarters, cats, policy)
        pick = (
            next((r for r in results if r.period_id == a.period_id), None)
            if a.period_id
            else results[-1]
        )
        if pick is None:
            return ToolResult(
                tool="get_normalized",
                status="not_found",
                reason=f"no verified quarter {a.period_id}",
            )
        data = {
            "period_id": pick.period_id,
            "accession": pick.accession,
            "policy_version": pick.policy_version,
            "preview": pick.preview,
            "lines": [
                {
                    "label": ln.label,
                    "category": ln.code,
                    "category_source": ln.source,
                    "treatment": ln.treatment,
                    "value_raw": ln.value_raw,
                }
                for ln in pick.lines
            ],
        }
        if pick.status != "computed" or pick.normalized is None:
            return ToolResult(
                tool="get_normalized",
                status="unavailable",
                reason=pick.reason or "not computed",
                data=data,
            )
        notes = ["policy is a draft: the figure is a preview"] if pick.preview else []
        if any(ln.source == "rule" for ln in pick.lines):
            notes.append(
                "some categories are rule suggestions not yet confirmed by a person"
            )
        value = Value(
            vid=f"norm:{cik}:{pick.period_id}:{pick.policy_version}",
            kind="norm",
            ticker=issuer["ticker"],
            label=f"Normalized EBITDA (policy {pick.policy_version})",
            period_id=pick.period_id,
            value=pick.normalized,
            unit="usd",
            scale=pick.scale,
            accession=pick.accession,
            verified=True,
            notes=tuple(notes),
        )
        return ToolResult(tool="get_normalized", status="ok", values=[value], data=data)


def tool_specs() -> list[dict[str, Any]]:
    """Name, description and JSON input schema of every tool, for a model or MCP."""
    docs = {
        "resolve_issuer": "Find a covered issuer by ticker or name.",
        "list_releases": "List an issuer's Item 2.02 earnings releases filed by as_of, "
        "with whether a bridge was extracted.",
        "get_bridge": "All lines of one release's EBITDA bridge (default: the latest "
        "by as_of), each with its vid, checks and verified flag.",
        "get_line_history": "One line for one period in every release that reported "
        "it, oldest first: as first reported vs as most recently reported.",
        "get_quarters": "Each 3-month period's line as most recently reported by "
        "as_of (use for LTM sums and year-over-year changes).",
        "get_changes": "Reconciling lines added or dropped versus the previous release.",
        "get_normalized": "Normalized EBITDA under Footnote's draft policy (current "
        "record only; preview).",
    }
    models: dict[str, type[_Args]] = {
        "resolve_issuer": ResolveIssuerArgs,
        "list_releases": ListReleasesArgs,
        "get_bridge": GetBridgeArgs,
        "get_line_history": GetLineHistoryArgs,
        "get_quarters": GetQuartersArgs,
        "get_changes": GetChangesArgs,
        "get_normalized": GetNormalizedArgs,
    }
    return [
        {
            "name": n,
            "description": docs[n],
            "input_schema": models[n].model_json_schema(),
        }
        for n in models
    ]
