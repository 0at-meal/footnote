"""
Footnote read API (P4-01) and web app host.

    uvicorn app.api.main:app --port 8000      (from backend/)

The snapshot is built from the observation store at start-up and on
``POST /api/refresh``. The API never computes or alters a number itself: it
serves the snapshot built by deterministic analytics.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response

from app.analytics.snapshot import build_snapshot
from app.analytics.source import source_table
from app.config import default_cache_dir, default_db
from app.export.excel import issuer_workbook
from app.store.db import Store

WEB_DIR = Path(__file__).resolve().parents[3] / "web"

app = FastAPI(title="Footnote API", version="0.1.0")
_state: dict[str, Any] = {}


def snapshot() -> dict[str, Any]:
    if "snap" not in _state:
        refresh()
    snap: dict[str, Any] = _state["snap"]
    return snap


@app.post("/api/refresh")
def refresh() -> dict[str, str]:
    store = Store(default_db())
    try:
        _state["snap"] = build_snapshot(store)
    finally:
        store.close()
    return {"generated_at": _state["snap"]["generated_at"]}


def _issuer(ticker: str) -> dict[str, Any]:
    for doc in snapshot()["issuers"]:
        if doc["ticker"] == ticker.upper():
            found: dict[str, Any] = doc
            return found
    raise HTTPException(status_code=404, detail=f"issuer {ticker!r} not covered")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "generated_at": snapshot()["generated_at"]}


@app.get("/api/coverage")
def coverage() -> dict[str, Any]:
    result: dict[str, Any] = snapshot()["coverage"]
    return result


@app.get("/api/issuers")
def issuers(sector: str | None = Query(default=None)) -> list[dict[str, Any]]:
    out = []
    for doc in snapshot()["issuers"]:
        if sector and doc["sector"] != sector:
            continue
        q = doc["quarters"][-1] if doc["quarters"] else None
        out.append(
            {
                "ticker": doc["ticker"],
                "name": doc["name"],
                "sector": doc["sector"],
                "quarters": len(doc["quarters"]),
                "latest_period": q["period_id"] if q else None,
                "reported_usd": q["reported_usd"] if q else None,
                "normalized_usd": q["normalized_usd"] if q else None,
                "addback_intensity": q["addback_intensity"] if q else None,
                "recasts": len(doc["recasts"]),
                "changes": len(doc["changes"]),
            }
        )
    return out


@app.get("/api/issuers/{ticker}")
def issuer(ticker: str) -> dict[str, Any]:
    return _issuer(ticker)


@app.get("/api/issuers/{ticker}/export.xlsx")
def issuer_export(ticker: str) -> Response:
    doc = _issuer(ticker)
    data = issuer_workbook(doc, snapshot()["policy"]["version"])
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{doc["ticker"]}-footnote.xlsx"'
        },
    )


@app.get("/api/feed")
def feed(limit: int = 200) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = snapshot()["feed"][:limit]
    return items


@app.get("/api/peers")
def peers() -> dict[str, Any]:
    result: dict[str, Any] = snapshot()["peers"]
    return result


@app.get("/api/source/{accession}")
def source(accession: str) -> dict[str, Any]:
    """
    The stored bridge table of one release, rendered from the cached exhibit,
    with every source cell marked by ``data-fn-xp``. A table that cannot be
    served comes back with an explicit ``status`` and ``reason``.
    """
    store = Store(default_db())
    try:
        doc = source_table(store, accession, default_cache_dir())
    finally:
        store.close()
    if doc is None:
        raise HTTPException(
            status_code=404, detail=f"release {accession!r} not on record"
        )
    return doc


@app.get("/api/snapshot")
def full_snapshot() -> dict[str, Any]:
    return snapshot()


@app.get("/snapshot.json")
def snapshot_file() -> dict[str, Any]:
    """The web app's data file (the static export writes the same document)."""
    return snapshot()


_SKELETON = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
    "<style>:root{padding-top:env(safe-area-inset-top,0px);"
    "padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}"
    "[hidden]{display:none!important}</style></head><body>{page}</body></html>"
)


@app.get("/")
def index() -> HTMLResponse:
    page = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(_SKELETON.replace("{page}", page))
