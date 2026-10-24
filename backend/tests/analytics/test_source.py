"""
Source viewer table (``app.analytics.source``) and ``GET /api/source/{accession}``.
The issuer, CIK, accession and every number are fixtures, not a real filing.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pytest
from app.analytics.snapshot import build_snapshot
from app.analytics.source import resolve_xpath, source_table
from app.extraction.bridge.engine import extract_headline_bridge
from app.pipeline.ingest import bridge_row
from app.store.db import FilingRow, IssuerRow, Store
from bs4 import BeautifulSoup, Tag

CIK = "0000000001"
ACC = "0000000001-26-000001"
RELEASE = (
    b"<html><head><style>td{color:red}</style></head><body>"
    b"<p>Fixture release</p>"
    b'<table style="width:100%">'
    b"<tr><td>(in millions)</td><td>Three Months Ended March 31, 2026</td>"
    b"<td>Three Months Ended March 31, 2025</td></tr>"
    b"<tr><td></td><td></td><td></td></tr>"
    b'<tr><td><font style="x">Net income</font></td><td>50</td><td>45</td></tr>'
    b"<tr><td>Interest expense</td><td>40</td><td>40</td></tr>"
    b'<tr><td>Restructuring<script>alert(1)</script></td><td onclick="x()">15</td><td>2</td></tr>'
    b"<tr><td>Adjusted EBITDA</td><td>105</td><td>87</td></tr>"
    b"</table></body></html>"
)


def _store(tmp_path: Path, sha: str | None) -> Store:
    s = Store(tmp_path / "footnote.db")
    s.upsert_issuer(IssuerRow(CIK, "TEST", "Fixture Holdings", "1231", "Fixtures"))
    run = s.start_run("test")
    s.add_filing(
        FilingRow(ACC, CIK, "8-K", "2.02", "2026-04-30", "ex991.htm", None, sha, None),
        run,
    )
    hb = extract_headline_bridge(
        RELEASE, accession=ACC, fiscal_year_end="1231", filed=date(2026, 4, 30)
    )
    assert hb.draft is not None
    assert s.add_bridge(bridge_row(hb, ACC, CIK, "ex991.htm"), CIK, "2026-04-30", run)
    return s


@pytest.fixture
def cache(tmp_path: Path) -> Path:
    d = tmp_path / "cache"
    (d / ACC).mkdir(parents=True)
    (d / ACC / "ex991.htm").write_bytes(RELEASE)
    return d


SHA = hashlib.sha256(RELEASE).hexdigest()


def test_resolve_xpath_counts_same_named_siblings() -> None:
    soup = BeautifulSoup(
        "<html><body><p>a</p><div>x</div><p>b</p></body></html>", "lxml"
    )
    html = soup.find("html")
    assert isinstance(html, Tag)
    found = resolve_xpath(html, ["body", "p[2]"])
    assert found is not None and found.get_text() == "b"
    assert resolve_xpath(html, ["body", "p[3]"]) is None
    assert resolve_xpath(html, ["body", "bad step!"]) is None


def test_source_table_marks_every_observed_cell(tmp_path: Path, cache: Path) -> None:
    store = _store(tmp_path, SHA)
    doc = source_table(store, ACC, cache)
    assert doc is not None
    assert doc["status"] == "ok", doc["reason"]
    assert doc["sha256"] == SHA
    observed = {
        r["xpath"]
        for r in store.query(
            "SELECT DISTINCT xpath FROM observations WHERE accession = ?", (ACC,)
        )
    }
    assert doc["cells"] == len(observed) > 0 and doc["cells_missing"] == 0
    html = doc["table_html"]
    for xp in observed:
        assert f'data-fn-xp="{xp}"' in html
    # Structure only: no filing scripts, styles, handlers or spacer rows.
    assert "<script" not in html and "style=" not in html and "onclick" not in html
    assert "<font" not in html and "<tr><td></td>" not in html
    assert "Net income" in html and "Adjusted EBITDA" in html


def test_source_table_reports_missing_and_tampered_exhibits(
    tmp_path: Path, cache: Path
) -> None:
    store = _store(tmp_path, "0" * 64)
    doc = source_table(store, ACC, cache)
    assert doc is not None and doc["status"] == "sha256_mismatch"
    assert doc["table_html"] is None
    doc = source_table(store, ACC, tmp_path / "empty-cache")
    assert doc is not None and doc["status"] == "not_cached" and doc["reason"]
    assert source_table(store, "0000000001-26-999999", cache) is None


def test_source_endpoint(
    tmp_path: Path, cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api import main as api
    from fastapi.testclient import TestClient

    _store(tmp_path, SHA).close()
    monkeypatch.setenv("FOOTNOTE_DB", str(tmp_path / "footnote.db"))
    monkeypatch.setenv("EDGAR_CACHE_DIR", str(cache))
    api._state.clear()
    client = TestClient(api.app)
    res = client.get(f"/api/source/{ACC}")
    assert res.status_code == 200
    body = res.json()
    assert (
        body["status"] == "ok"
        and body["accession"] == ACC
        and body["filed"] == "2026-04-30"
    )
    assert "data-fn-xp" in body["table_html"]
    assert client.get("/api/source/0000000001-26-999999").status_code == 404


def test_held_out_counts_exclude_the_gold_set(tmp_path: Path) -> None:
    store = _store(tmp_path, SHA)
    held = build_snapshot(store, gold=set())["coverage"]["held_out"]
    assert held == {
        "gold_releases": 0,
        "releases": 1,
        "bridges_found": 1,
        "bridges_all_periods_tie": 1,
    }
    held = build_snapshot(store, gold={ACC})["coverage"]["held_out"]
    assert held["releases"] == 0 and held["gold_releases"] == 1
