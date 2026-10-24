"""
Tests for the A-09 agent tools. The store is a synthetic fixture (FIX* tickers,
zero-padded CIKs, made-up values) built with the A-02 test helpers.
"""

from datetime import date
from pathlib import Path

import pytest
from app.agent.tools import AgentTools, tool_specs

from tests.tools.test_agent_keys import Q_ENDS, Fixture, bridge, quarterly_issuer

A = "0000000001"


@pytest.fixture
def fx(tmp_path: Path) -> Fixture:
    f = Fixture(tmp_path / "s.db")
    quarterly_issuer(f, A, "FIXT", 100)
    return f


def test_resolve_issuer(fx: Fixture) -> None:
    tools = AgentTools(fx.store)
    r = tools.call("resolve_issuer", {"query": "fixt"})
    assert r.status == "ok" and r.data["issuers"][0]["releases"] == 4
    miss = tools.call("resolve_issuer", {"query": "NOPE"})
    assert miss.status == "not_found" and miss.reason and "not_covered" in miss.reason


def test_get_bridge_latest_by_as_of_and_ledger(fx: Fixture) -> None:
    tools = AgentTools(fx.store)
    r = tools.call("get_bridge", {"ticker": "FIXT", "as_of": "2025-09-01"})
    assert r.status == "ok" and r.data["filed"] == "2025-08-04"
    total = next(
        v for v in r.values if v.role == "total" and v.period_id == "3M-2025-06-30"
    )
    assert total.value == 135 and total.verified and total.vid.startswith("obs:")
    assert total.vid in tools.ledger
    assert all(v.vid in tools.ledger for v in r.values)
    one = tools.call(
        "get_bridge",
        {"ticker": "FIXT", "filed": "2025-05-05", "period_id": "3M-2024-03-31"},
    )
    assert {v.period_id for v in one.values} == {"3M-2024-03-31"}


def test_unverified_values_are_flagged_not_dropped(fx: Fixture) -> None:
    fx.release(
        A, date(2026, 5, 5), {date(2026, 3, 31): bridge(1, 2, 3)}, anchor_ok=False
    )
    r = AgentTools(fx.store).call("get_bridge", {"ticker": "FIXT"})
    assert r.values and not any(v.verified for v in r.values)
    assert r.values[0].checks == {"sum": "pass", "anchor": "fail"}


def test_bridge_not_extracted_is_unavailable(fx: Fixture) -> None:
    acc = fx.filing(A, date(2026, 6, 1))
    with fx.store.tx() as c:
        c.execute(
            "INSERT INTO bridges (accession, engine_version, status, reason, run_id)"
            " VALUES (?, 'fixture', 'not_found', 'fixture reason', 1)",
            (acc,),
        )
    r = AgentTools(fx.store).call("get_bridge", {"ticker": "FIXT"})
    assert r.status == "unavailable" and r.reason == "no_bridge: fixture reason"


def test_line_history_and_quarters(fx: Fixture) -> None:
    fx.release(
        A,
        date(2026, 5, 5),
        {date(2026, 3, 31): bridge(150, 20, 5), Q_ENDS[4]: bridge(90, 20, 5)},
    )
    tools = AgentTools(fx.store)
    h = tools.call("get_line_history", {"ticker": "FIXT", "period_id": "3M-2025-03-31"})
    assert [v.value for v in h.values] == [125, 115]  # first reported, then recast
    q = tools.call("get_quarters", {"ticker": "FIXT", "as_of": "2026-04-01"})
    assert [v.value for v in q.values][-4:] == [125, 135, 145, 155]
    q2 = tools.call("get_quarters", {"ticker": "FIXT"})
    assert q2.values[-5].value == 115  # Q1 2025 as most recently reported
    r = tools.call(
        "get_quarters", {"ticker": "FIXT", "line": "Restructuring", "limit": 2}
    )
    assert [v.label for v in r.values] == ["Restructuring", "Restructuring"]


def test_get_changes(fx: Fixture) -> None:
    fx.release(
        A,
        date(2026, 5, 5),
        {
            date(2026, 3, 31): {
                "Net income": bridge(100, 20, 5)["Net income"],
                "Depreciation and amortization": bridge(100, 20, 5)[
                    "Depreciation and amortization"
                ],
                "Restructuring": bridge(100, 20, 5)["Restructuring"],
                "Litigation": bridge(7, 0, 0)["Net income"],
                "Adjusted EBITDA": bridge(132, 0, 0)["Net income"],
            }
        },
    )
    r = AgentTools(fx.store).call("get_changes", {"ticker": "FIXT"})
    assert (
        r.status == "ok"
        and r.data["added"] == ["Litigation"]
        and r.data["dropped"] == []
    )


def test_get_normalized(fx: Fixture) -> None:
    tools = AgentTools(fx.store)
    missing = tools.call("get_normalized", {"ticker": "FIXT"})
    assert missing.status == "unavailable" and "unclassified_line" in (
        missing.reason or ""
    )
    with fx.store.tx() as c:
        for key, code in (
            ("depreciation and amortization", "DA"),
            ("restructuring", "RESTR"),
        ):
            c.execute(
                "INSERT INTO label_memory VALUES (?, ?, ?, '[]', '[]', 'human',"
                " 'fixture', '2026-10-24')",
                (A, key, code),
            )
    r = tools.call("get_normalized", {"ticker": "FIXT"})
    assert r.status == "ok" and r.values[0].vid.startswith("norm:")
    # Restructuring recurs in every quarter, so it is excluded: 155 - 5.
    assert r.values[0].value == 150
    old = tools.call("get_normalized", {"ticker": "FIXT", "as_of": "2025-06-01"})
    assert old.status == "unavailable"


def test_invalid_calls_and_no_writes(fx: Fixture) -> None:
    tools = AgentTools(fx.store)
    before = fx.store.conn.total_changes
    assert tools.call("nope", {}).status == "invalid"
    assert tools.call("get_bridge", {"ticker": "FIXT", "bogus": 1}).status == "invalid"
    assert tools.call("get_bridge", {"ticker": "NOPE"}).status == "not_found"
    for name in tools.names:
        tools.call(
            name, {"ticker": "FIXT"} if name != "resolve_issuer" else {"query": "F"}
        )
    tools.call("get_normalized", {"ticker": "FIXT"})
    assert fx.store.conn.total_changes == before


def test_tool_specs_cover_every_tool(fx: Fixture) -> None:
    specs = tool_specs()
    assert [s["name"] for s in specs] == AgentTools(fx.store).names
    assert all(s["input_schema"]["type"] == "object" for s in specs)


def test_compute_through_the_tool_interface(fx: Fixture) -> None:
    tools = AgentTools(fx.store)
    q = tools.call("get_quarters", {"ticker": "FIXT", "limit": 4})
    r = tools.call("compute", {"op": "sum", "vids": [v.vid for v in q.values]})
    assert (
        r.status == "ok"
        and r.values[0].value == 560
        and r.values[0].vid in tools.ledger
    )
    bad = tools.call("compute", {"op": "sum", "vids": ["obs:0:0:3M-2025-03-31"]})
    assert bad.status == "invalid"
