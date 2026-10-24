"""
End-to-end on synthetic releases: engine -> store rows -> history, normalization,
snapshot, API and Excel. The issuer, CIK, accessions and every number are
fixtures, not a real filing.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from app.analytics.history import definition_changes, quarter_series, recasts
from app.analytics.normalize import load_policy, normalize_issuer
from app.analytics.snapshot import build_snapshot
from app.extraction.bridge.engine import extract_headline_bridge
from app.pipeline.ingest import ENGINE_VERSION, bridge_row
from app.store.db import FilingRow, IssuerRow, Store

CIK = "0000000001"


def _release(cols: list[str], rows: list[tuple[str, list[str]]]) -> str:
    head = (
        "<tr><td>(in millions)</td>" + "".join(f"<td>{c}</td>" for c in cols) + "</tr>"
    )
    body = "".join(
        f"<tr><td>{label}</td>" + "".join(f"<td>{v}</td>" for v in vals) + "</tr>"
        for label, vals in rows
    )
    return f"<html><body><table>{head}{body}</table></body></html>"


Q1 = _release(
    ["Three Months Ended March 31, 2026", "Three Months Ended March 31, 2025"],
    [
        ("Net income", ["50", "45"]),
        ("Interest expense", ["40", "40"]),
        ("Restructuring", ["15", "2"]),
        ("Adjusted EBITDA", ["105", "87"]),
    ],
)
Q2 = _release(
    ["Three Months Ended June 30, 2026", "Three Months Ended March 31, 2026"],
    [
        ("Net income", ["60", "47"]),
        ("Interest expense", ["41", "40"]),
        ("Restructuring", ["9", "18"]),
        ("Litigation costs", ["5", "—"]),
        ("Adjusted EBITDA", ["115", "105"]),
    ],
)


def _ingest(store: Store, accession: str, html: str, filed: str, run_id: int) -> None:
    store.add_filing(
        FilingRow(
            accession, CIK, "8-K", "2.02,9.01", filed, "ex991.htm", None, None, None
        ),
        run_id,
    )
    hb = extract_headline_bridge(
        html,
        accession=accession,
        fiscal_year_end="1231",
        filed=date.fromisoformat(filed),
    )
    assert hb.draft is not None and all(c.passed for c in hb.draft.sum_checks)
    assert store.add_bridge(
        bridge_row(hb, accession, CIK, "ex991.htm"), CIK, filed, run_id
    )


@pytest.fixture
def store(tmp_path: Path) -> Store:
    s = Store(tmp_path / "footnote.db")
    s.upsert_issuer(IssuerRow(CIK, "TEST", "Fixture Holdings", "1231", "Fixtures"))
    run = s.start_run("test")
    _ingest(s, "0000000001-26-000001", Q1, "2026-04-30", run)
    _ingest(s, "0000000001-26-000002", Q2, "2026-07-30", run)
    s.finish_run(run, {})
    return s


def test_store_is_idempotent(store: Store) -> None:
    hb = extract_headline_bridge(Q1, accession="0000000001-26-000001")
    row = bridge_row(hb, "0000000001-26-000001", CIK, "ex991.htm")
    assert row.engine_version == ENGINE_VERSION
    assert not store.add_bridge(row, CIK, "2026-04-30", 1)
    assert store.query("SELECT COUNT(*) FROM bridges")[0][0] == 2


def test_latest_release_wins_and_recasts_are_kept(store: Store) -> None:
    quarters = quarter_series(store, CIK)
    assert [q.period_id for q in quarters] == [
        "3M-2025-03-31",
        "3M-2026-03-31",
        "3M-2026-06-30",
    ]
    q1 = quarters[1]
    assert q1.accession == "0000000001-26-000002"  # the later release reports it too
    found = {(r.line_key, r.period_id): r for r in recasts(store, CIK)}
    net = found[("net income", "3M-2026-03-31")]
    assert (net.first_value_usd, net.latest_value_usd) == (
        Decimal(50000000),
        Decimal(47000000),
    )
    # Both observations stay in the store.
    assert (
        store.query(
            "SELECT COUNT(*) FROM observations WHERE line_key = 'net income' "
            "AND period_id = '3M-2026-03-31'"
        )[0][0]
        == 2
    )


def test_definition_change_added_line(store: Store) -> None:
    changes = definition_changes(store, CIK)
    assert ("added", "Litigation costs") in {(c.kind, c.label) for c in changes}


def test_normalization_is_itemized_and_previewed(store: Store) -> None:
    quarters = quarter_series(store, CIK)
    results = normalize_issuer(store, CIK, quarters)
    latest = results[-1]
    assert latest.preview is True
    assert latest.policy_version == load_policy().version
    assert latest.status == "computed"
    # Window ending 2026-06-30: two quarters add back RESTR, two are unknown
    # (2025-09-30, 2025-12-31), so recurrence is unknown and the line is kept.
    restr = next(ln for ln in latest.lines if ln.code == "RESTR")
    assert restr.recurrence["RESTR"] == "unknown"
    assert restr.treatment == "accept"
    assert "recurrence_unknown" in restr.flags
    assert latest.normalized == Decimal(115)
    # Categories came from rules and are pending review.
    assert latest.pending_review == len(latest.lines)
    labels = store.query("SELECT DISTINCT source FROM label_memory")
    assert [r[0] for r in labels] == ["rule"]


def test_human_label_beats_rule(store: Store) -> None:
    store.set_label(CIK, "restructuring", "OTHER_NR", "human", "reviewer")
    store.set_label(CIK, "restructuring", "RESTR", "rule", "rules")
    row = store.query(
        "SELECT code, source FROM label_memory WHERE line_key = 'restructuring'"
    )[0]
    assert (row["code"], row["source"]) == ("OTHER_NR", "human")


def test_snapshot_api_and_excel(
    store: Store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snap = build_snapshot(store)
    doc = snap["issuers"][0]
    assert doc["ticker"] == "TEST"
    assert doc["recasts"] and doc["changes"]
    assert snap["coverage"]["bridges_all_periods_tie"] == 2

    from app.api import main as api
    from fastapi.testclient import TestClient

    monkeypatch.setenv("FOOTNOTE_DB", str(tmp_path / "footnote.db"))
    api._state.clear()
    client = TestClient(api.app)
    assert client.get("/api/health").json()["status"] == "ok"
    listing = client.get("/api/issuers").json()
    assert listing[0]["ticker"] == "TEST" and listing[0]["recasts"] >= 1
    assert client.get("/api/issuers/NOPE").status_code == 404
    xlsx = client.get("/api/issuers/TEST/export.xlsx")
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    assert client.get("/").text.startswith("<!doctype html>")


def test_recurring_category_is_reversed(store: Store) -> None:
    # Fill the two missing quarters so RESTR appears in 4 of the last 4.
    for acc, filed, cols, vals in [
        (
            "0000000001-26-000003",
            "2025-10-30",
            "September 30, 2025",
            ["35", "30", "4", "69"],
        ),
        (
            "0000000001-26-000004",
            "2026-02-20",
            "December 31, 2025",
            ["37", "30", "6", "73"],
        ),
    ]:
        html = _release(
            [f"Three Months Ended {cols}"],
            [
                ("Net income", [vals[0]]),
                ("Interest expense", [vals[1]]),
                ("Restructuring", [vals[2]]),
                ("Adjusted EBITDA", [vals[3]]),
            ],
        )
        _ingest(store, acc, html, filed, 1)
    quarters = quarter_series(store, CIK)
    latest = normalize_issuer(store, CIK, quarters)[-1]
    restr = next(ln for ln in latest.lines if ln.code == "RESTR")
    assert restr.recurrence["RESTR"] == "recurring"
    assert restr.treatment == "exclude"
    assert latest.normalized == Decimal(115) - Decimal(9)


def test_coverage_counts_only_the_current_extraction(store: Store) -> None:
    """Re-extracting with a new engine version must not double the check counts."""
    before = build_snapshot(store)["coverage"]["sum_checks"]
    hb = extract_headline_bridge(Q1, accession="0000000001-26-000001")
    row = bridge_row(hb, "0000000001-26-000001", CIK, "ex991.htm")
    row.engine_version = "test-next"
    assert store.add_bridge(row, CIK, "2026-04-30", 1)
    assert build_snapshot(store)["coverage"]["sum_checks"] == before


def test_review_export_and_apply(store: Store, tmp_path: Path) -> None:
    import csv

    from app.analytics.normalize import category_for
    from app.pipeline.review import apply_queue, export_queue

    quarter_series(store, CIK)
    normalize_issuer(store, CIK, quarter_series(store, CIK))  # records rule labels
    queue = tmp_path / "queue.csv"
    assert export_queue(store, queue) >= 2
    rows = list(csv.DictReader(queue.open(encoding="utf-8-sig")))
    for row in rows:
        if row["line_key"] == "restructuring":
            row["decision"] = "ok"
        if row["line_key"] == "litigation costs":
            row["decision"] = "OTHER_NR"
    with queue.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with pytest.raises(ValueError):
        apply_queue(store, queue, reviewer="")
    res = apply_queue(store, queue, reviewer="Test Reviewer")
    assert res.applied == 2 and res.errors == []
    assert category_for(store, CIK, "litigation costs").source == "human"
    assert category_for(store, CIK, "litigation costs").code == "OTHER_NR"
    assert category_for(store, CIK, "interest expense").source == "rule"


def test_review_rejects_unknown_codes(store: Store, tmp_path: Path) -> None:
    from app.pipeline.review import apply_queue

    normalize_issuer(store, CIK, quarter_series(store, CIK))
    bad = tmp_path / "bad.csv"
    bad.write_text(
        "line_key,suggested,components,decision\nrestructuring,RESTR,,NOPE\n",
        encoding="utf-8",
    )
    res = apply_queue(store, bad, reviewer="R")
    assert res.applied == 0 and res.errors


def test_digest_lists_watchlist_changes(store: Store) -> None:
    from app.analytics.digest import build_digest

    snap = build_snapshot(store)
    html, n = build_digest(snap, ["test"], date(2026, 1, 1), date(2026, 12, 31))
    assert n >= 2 and "Recast" in html and "Litigation costs" in html
    html, n = build_digest(snap, ["OTHER"], date(2026, 1, 1), date(2026, 12, 31))
    assert n == 0 and "No changes" in html
