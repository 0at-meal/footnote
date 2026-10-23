"""
Source viewer read model: the stored filing table behind a bridge.

``source_table`` reads the cached EX-99.1 exhibit of a release, checks its bytes
against the sha256 recorded at ingest, finds the bridge table by its stored
``table_xpath`` and marks every cell an observation was read from with a
``data-fn-xp`` attribute holding that cell's xpath. The HTML is reduced to table
structure (colspan/rowspan and text): no scripts, styles or images from the
filing are served.

Nothing here touches the network; an exhibit missing from the cache is reported
as ``not_cached``, never fetched.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from app.store.db import Store
from bs4 import BeautifulSoup, Tag

_STEP = re.compile(r"^([a-z0-9]+)(?:\[(\d+)\])?$")
_KEEP_ATTRS = ("colspan", "rowspan")
_DROP_TAGS = ("script", "style", "img", "link", "meta", "object", "iframe")
_UNWRAP_TAGS = ("font", "span", "p", "div", "a", "ix:nonfraction", "ix:nonnumeric")


def resolve_xpath(root: Tag, steps: list[str]) -> Tag | None:
    """
    Walk ``steps`` (``"div[102]"``, ``"table"``) down from ``root``.

    Mirrors ``get_element_xpath``: an index counts same-named element siblings,
    and a step without an index means the element was its parent's only one.
    """
    node: Tag = root
    for step in steps:
        m = _STEP.match(step)
        if m is None:
            return None
        name, idx = m.group(1), int(m.group(2) or 1)
        same = [c for c in node.children if isinstance(c, Tag) and c.name == name]
        if idx > len(same):
            return None
        node = same[idx - 1]
    return node


def _steps(xpath: str) -> list[str] | None:
    parts = [p for p in xpath.split("/") if p]
    if not parts or parts[0] != "html":
        return None
    return parts[1:]


def source_table(
    store: Store, accession: str, cache_dir: Path
) -> dict[str, Any] | None:
    """The bridge table of one release, or ``None`` if the accession is unknown."""
    rows = store.query(
        """
        SELECT f.accession, f.cik, f.filed, f.exhibit, f.url, f.sha256,
               b.bridge_id, b.status AS bridge_status, b.table_xpath
        FROM filings f LEFT JOIN current_bridges b USING (accession)
        WHERE f.accession = ?
        """,
        (accession,),
    )
    if not rows:
        return None
    r = rows[0]
    doc: dict[str, Any] = {
        "accession": r["accession"],
        "filed": r["filed"],
        "url": r["url"],
        "sha256": r["sha256"],
        "status": "ok",
        "reason": None,
        "table_html": None,
        "cells": 0,
        "cells_missing": 0,
    }

    def fail(status: str, reason: str) -> dict[str, Any]:
        doc["status"], doc["reason"] = status, reason
        return doc

    if r["bridge_id"] is None or not r["table_xpath"]:
        return fail("no_table", "no bridge table was recorded for this release")
    if not r["exhibit"]:
        return fail("no_exhibit", "the release has no HTML exhibit on record")
    path = cache_dir / accession / r["exhibit"]
    if not path.is_file():
        return fail("not_cached", f"exhibit {r['exhibit']} is not in the local cache")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if r["sha256"] and digest != r["sha256"]:
        return fail(
            "sha256_mismatch",
            f"cached exhibit hashes to {digest[:12]}…, ingest recorded {r['sha256'][:12]}…",
        )
    if not r["sha256"]:
        doc["sha256"] = digest

    soup = BeautifulSoup(data, "lxml")
    html = soup.find("html", recursive=False)
    steps = _steps(r["table_xpath"])
    table = resolve_xpath(html, steps) if isinstance(html, Tag) and steps else None
    if table is None or table.name != "table":
        return fail("table_not_found", f"no table at {r['table_xpath']}")

    prefix = r["table_xpath"].rstrip("/") + "/"
    xpaths = [
        x["xpath"]
        for x in store.query(
            "SELECT DISTINCT xpath FROM observations WHERE bridge_id = ? AND xpath IS NOT NULL",
            (r["bridge_id"],),
        )
    ]
    found = missing = 0
    for xp in xpaths:
        cell = (
            resolve_xpath(table, xp[len(prefix) :].split("/"))
            if xp.startswith(prefix)
            else None
        )
        if cell is None:
            missing += 1
            continue
        cell["data-fn-xp"] = xp
        found += 1

    for tag in table.find_all(_DROP_TAGS):
        tag.decompose()
    for tag in table.find_all(_UNWRAP_TAGS):
        tag.unwrap()
    # Spacer rows carry no text in the filing; dropping them keeps the
    # rendered table readable and changes no cell anyone can cite.
    for tr in table.find_all("tr"):
        marked = any(c.has_attr("data-fn-xp") for c in tr.find_all(["td", "th"]))
        if not tr.get_text(strip=True) and not marked:
            tr.decompose()
    for tag in [table, *table.find_all(True)]:
        tag.attrs = {
            k: v for k, v in tag.attrs.items() if k in _KEEP_ATTRS or k == "data-fn-xp"
        }
    doc["table_html"] = str(table)
    doc["cells"], doc["cells_missing"] = found, missing
    return doc
