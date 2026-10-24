"""
Watchlist change digest (P4-06): a self-contained HTML email body.

Built from the snapshot's change feed for the tickers on a watchlist and the
releases filed in a window. Every item links to the line on sec.gov. Sending
is a separate step (an email provider account is an owner action).
"""

from __future__ import annotations

from datetime import date
from html import escape
from typing import Any

_LABELS = {
    "recast": "Recast",
    "recurring_addback": "Recurring “one-off”",
    "added": "Add-back added",
    "removed": "Add-back dropped",
    "renamed": "Line renamed",
    "metric_renamed": "Metric renamed",
    "layout_changed": "New bridge layout",
}
_ORDER = list(_LABELS)


def _m(v: float | None) -> str:
    if v is None:
        return "—"
    x = v / 1e6
    s = f"{abs(x):,.1f}"
    return f"({s})" if x < 0 else s


def _describe(item: dict[str, Any]) -> str:
    link = escape(item.get("url") or item.get("latest_url") or "")
    label = escape(str(item.get("label", "")))
    if item["type"] == "recast":
        return (
            f"{label} for {escape(item['period_id'])}: {_m(item['first_usd'])} → "
            f'<a href="{link}">{_m(item["latest_usd"])}</a> ($m)'
        )
    if item["type"] in ("renamed", "metric_renamed"):
        return f'{escape(str(item.get("prior_label")))} → <a href="{link}">{label}</a>'
    return f'<a href="{link}">{label}</a> {escape(str(item.get("value_raw") or ""))}'


def build_digest(
    snapshot: dict[str, Any], tickers: list[str], since: date, until: date
) -> tuple[str, int]:
    """(HTML, item count) for changes filed in [since, until] on the watchlist."""
    wanted = {t.upper() for t in tickers}
    items = [
        i
        for i in snapshot["feed"]
        if i["ticker"] in wanted
        and i.get("filed")
        and since.isoformat() <= i["filed"] <= until.isoformat()
    ]
    items.sort(
        key=lambda i: (
            _ORDER.index(i["type"]) if i["type"] in _ORDER else 99,
            i["ticker"],
        )
    )
    rows = "".join(
        f"<tr><td style='padding:6px 10px;font-weight:600'>{escape(i['ticker'])}</td>"
        f"<td style='padding:6px 10px'>{escape(_LABELS.get(i['type'], i['type']))}</td>"
        f"<td style='padding:6px 10px'>{_describe(i)}</td>"
        f"<td style='padding:6px 10px;color:#5b6577'>{escape(i['filed'])}</td></tr>"
        for i in items
    )
    body = (
        "<div style='font-family:Arial,sans-serif;color:#111a2b;max-width:720px'>"
        f"<h2 style='margin:0 0 4px'>Footnote: what changed, {since:%d %b} to {until:%d %b %Y}</h2>"
        f"<p style='color:#5b6577;margin:0 0 16px'>Watchlist: {escape(', '.join(sorted(wanted)))}. "
        f"{len(items)} change(s). Every value links to the line in the SEC filing.</p>"
        + (
            "<table style='border-collapse:collapse;font-size:14px'>"
            "<tr><th align='left' style='padding:6px 10px'>Issuer</th>"
            "<th align='left' style='padding:6px 10px'>Change</th>"
            "<th align='left' style='padding:6px 10px'>Detail</th>"
            "<th align='left' style='padding:6px 10px'>Filed</th></tr>"
            f"{rows}</table>"
            if items
            else "<p>No changes in the bridges on your watchlist this period.</p>"
        )
        + "<p style='color:#5b6577;font-size:12px;margin-top:16px'>Normalized figures use "
        "draft policy v0.1. Categories pending review are marked in the app.</p></div>"
    )
    return body, len(items)
