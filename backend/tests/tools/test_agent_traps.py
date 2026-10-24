"""
Tests for the A-03 must-refuse and false-premise builders. The store, exhibits
and universe file are synthetic fixtures (FIX* tickers, zero-padded CIKs).
"""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from tools.agent_eval.keys import KeyData
from tools.agent_eval.questions import Question
from tools.agent_eval.traps import (
    c8_noebitda,
    c8_notcovered,
    c8_unreported,
    c9_recast,
    c9_scale,
    c9_yoy,
    generate,
)

from tests.tools.test_agent_keys import Q_ENDS, Fixture, bridge, quarterly_issuer

A = "0000000001"


def test_c8_unreported_as_of_is_the_day_before_the_release(tmp_path: Path) -> None:
    fx = Fixture(tmp_path / "s.db")
    quarterly_issuer(fx, A, "FIXT", 100)
    cands = {c.key: c for c in c8_unreported(KeyData(fx.store))}
    c = cands[f"c8-unreported|{A}|3M-2025-06-30"]
    assert c.fields["as_of"] == Q_ENDS[5] + timedelta(days=34)
    assert c.fields["reason_codes"] == ["period_not_reported"]


def _not_found(
    fx: Fixture, cik: str, filed: date, exhibit_html: str, cache: Path
) -> None:
    acc = fx.filing(cik, filed)
    with fx.store.tx() as c:
        c.execute(
            "INSERT INTO bridges (accession, engine_version, status, run_id)"
            " VALUES (?, 'fixture', 'not_found', 1)",
            (acc,),
        )
    (cache / acc).mkdir(parents=True)
    (cache / acc / "ex991.htm").write_text(exhibit_html, encoding="utf-8")


def test_c8_noebitda_reads_the_exhibit_text(tmp_path: Path) -> None:
    fx = Fixture(tmp_path / "s.db")
    fx.issuer(A, "FIXT")
    cache = tmp_path / "cache"
    filler = "Fixture press release text about operating income. " * 60
    _not_found(fx, A, date(2025, 2, 1), f"<p>{filler}</p>", cache)
    _not_found(
        fx, A, date(2025, 5, 1), f"<p>{filler} Adjusted EBITDA was up.</p>", cache
    )
    _not_found(fx, A, date(2025, 8, 1), "<img src='page1.png'>", cache)
    data = KeyData(fx.store)
    cands = list(c8_noebitda(data, fx.store, cache))
    assert len(cands) == 1
    assert cands[0].fields["as_of"] == date(2025, 2, 1)
    assert cands[0].fields["reason_codes"] == ["metric_not_ebitda", "no_bridge"]
    assert data.skips["C8: exhibit is mostly images"] == 1


def test_c8_notcovered_uses_rejected_tickers(tmp_path: Path) -> None:
    path = tmp_path / "universe.yaml"
    path.write_text(
        "generated: '2026-10-22'\nissuers: []\nrejected:\n"
        "- ticker: FIXZ\n  reason: fixture rejection\n",
        encoding="utf-8",
    )
    (c,) = list(c8_notcovered(path))
    assert c.tickers == ("FIXZ",) and c.fields["as_of"] == date(2026, 10, 22)


def test_c9_yoy_flips_the_direction(tmp_path: Path) -> None:
    fx = Fixture(tmp_path / "s.db")
    quarterly_issuer(fx, A, "FIXT", 100)  # 2025 totals 125..155 vs 125 a year earlier
    cands = {c.key: c for c in c9_yoy(KeyData(fx.store))}
    c = cands[f"c9-yoy|c2-yoy|{A}|3M-2025-09-30"]
    assert "fall 16%" in c.fields["question"]  # it rose 16%
    assert c.fields["values"][1]["value"] == "16.00"
    assert f"c9-yoy|c2-yoy|{A}|3M-2025-03-31" not in cands  # 0%: no premise to flip


def test_c9_recast_needs_the_same_value_everywhere(tmp_path: Path) -> None:
    fx = Fixture(tmp_path / "s.db")
    quarterly_issuer(fx, A, "FIXT", 100)
    fx.release(
        A,
        date(2026, 5, 5),
        {date(2026, 3, 31): bridge(150, 20, 5), Q_ENDS[4]: bridge(100, 20, 5)},
    )
    keys = {c.key for c in c9_recast(KeyData(fx.store))}
    assert f"c9-recast|c3|{A}|3M-2025-03-31|total" in keys
    fx.release(
        A,
        date(2026, 8, 5),
        {date(2026, 6, 30): bridge(150, 20, 5), Q_ENDS[4]: bridge(100, 20, 5)},
    )
    fx.release(  # a later release restates, then the next one reverts
        A,
        date(2026, 2, 1),
        {Q_ENDS[7]: bridge(130, 20, 5), Q_ENDS[4]: bridge(90, 20, 5)},
    )
    data = KeyData(fx.store)
    keys = {c.key for c in c9_recast(data)}
    assert f"c9-recast|c3|{A}|3M-2025-03-31|total" not in keys


def test_c9_scale_states_the_wrong_unit(tmp_path: Path) -> None:
    fx = Fixture(tmp_path / "s.db")
    quarterly_issuer(fx, A, "FIXT", 100)
    c = next(iter(c9_scale(KeyData(fx.store))))
    assert " billion for " in c.fields["question"]
    assert c.fields["values"][0]["scale"] == "millions"
    assert Decimal(c.fields["values"][0]["value"]) > 0


def test_generate_yields_valid_refusals(tmp_path: Path) -> None:
    fx = Fixture(tmp_path / "s.db")
    quarterly_issuer(fx, A, "FIXT", 100)
    universe = tmp_path / "universe.yaml"
    universe.write_text(
        "generated: '2026-10-22'\nissuers: []\nrejected:\n- ticker: FIXZ\n",
        encoding="utf-8",
    )
    questions, _ = generate(
        fx.store,
        date(2026, 10, 24),
        cache_dir=tmp_path / "none",
        universe_path=universe,
    )
    assert questions
    for q in questions:
        Question.model_validate(q.model_dump())
        assert q.expected.status.value == "refused"
        assert q.author == "tools.agent_eval.traps"
