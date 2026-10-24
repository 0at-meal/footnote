"""
Tests for the A-02 answer-key generators. The store built here is a synthetic
fixture: zero-padded fixture CIKs, FIX* tickers and made-up values. It describes
no filing.
"""

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from app.store.db import Store
from tools.agent_eval.keys import (
    AUTHOR,
    KeyData,
    c2,
    c3,
    c5,
    c6,
    c7,
    generate,
    select,
    write,
)
from tools.agent_eval.questions import Question, validate_dir

from tests.tools.test_labels import release_dict

Q_ENDS = [
    date(2024, 3, 31),
    date(2024, 6, 30),
    date(2024, 9, 30),
    date(2024, 12, 31),
    date(2025, 3, 31),
    date(2025, 6, 30),
    date(2025, 9, 30),
    date(2025, 12, 31),
]


def _url(cik: str, acc: str, frag: str = "") -> str:
    return (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{acc.replace('-', '')}/ex991.htm{frag}"
    )


class Fixture:
    def __init__(self, path: Path) -> None:
        self.store = Store(path)
        self.n = 0
        with self.store.tx() as c:
            c.execute(
                "INSERT INTO runs (started_at, command) VALUES ('2026-10-24', 'fixture')"
            )

    def issuer(self, cik: str, ticker: str, sector: str = "Fixtures") -> None:
        with self.store.tx() as c:
            c.execute(
                "INSERT INTO issuers VALUES (?, ?, ?, '1231', ?)",
                (cik, ticker, f"{ticker} fixture", sector),
            )

    def filing(self, cik: str, filed: date, acc: str | None = None) -> str:
        self.n += 1
        acc = acc or f"{cik}-26-{self.n:06d}"
        with self.store.tx() as c:
            c.execute(
                "INSERT INTO filings (accession, cik, form, items, filed, exhibit, url,"
                " sha256, bytes, first_run) VALUES (?, ?, '8-K', '2.02', ?, 'ex991.htm',"
                " ?, NULL, NULL, 1)",
                (acc, cik, filed.isoformat(), _url(cik, acc)),
            )
        return acc

    def release(
        self,
        cik: str,
        filed: date,
        columns: dict[date, dict[str, Decimal]],
        *,
        metric: str = "Adjusted EBITDA",
        anchor_ok: bool = True,
        sum_ok: bool = True,
        acc: str | None = None,
    ) -> str:
        """One release; each column maps line label -> value. The last label is
        the total, the first the GAAP start, the rest adjustments."""
        acc = self.filing(cik, filed, acc)
        with self.store.tx() as c:
            cur = c.execute(
                "INSERT INTO bridges (accession, engine_version, status, metric_label,"
                " scale, run_id) VALUES (?, 'fixture', 'ok', ?, 'millions', 1)",
                (acc, metric),
            )
            bid = cur.lastrowid
            for col, (end, lines) in enumerate(columns.items()):
                pid = f"3M-{end.isoformat()}"
                c.execute(
                    "INSERT INTO bridge_periods VALUES (?, ?, ?, 3, ?, ?)",
                    (bid, col, pid, end.isoformat(), pid),
                )
                labels = list(lines)
                for row, label in enumerate(labels):
                    role = (
                        "gaap_start"
                        if row == 0
                        else "total"
                        if row == len(labels) - 1
                        else "adjustment"
                    )
                    v = lines[label]
                    c.execute(
                        "INSERT INTO observations (bridge_id, cik, accession, filed,"
                        " row_order, label, line_key, role, sign, period_id, value_raw,"
                        " value, scale, value_usd, xpath, url) VALUES"
                        " (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, 'millions', ?, NULL, ?)",
                        (
                            bid,
                            cik,
                            acc,
                            filed.isoformat(),
                            row,
                            label,
                            label.lower(),
                            role,
                            pid,
                            str(v),
                            str(v),
                            str(v * 1_000_000),
                            _url(cik, acc, f"#:~:text={label.split()[0]}"),
                        ),
                    )
                for kind, ok in (("sum", sum_ok), ("anchor", anchor_ok)):
                    c.execute(
                        "INSERT INTO checks VALUES (?, ?, ?, ?, '{}')",
                        (bid, kind, pid, "pass" if ok else "fail"),
                    )
        return acc


def bridge(net: int, da: int, restr: int) -> dict[str, Decimal]:
    return {
        "Net income": Decimal(net),
        "Depreciation and amortization": Decimal(da),
        "Restructuring": Decimal(restr),
        "Adjusted EBITDA": Decimal(net + da + restr),
    }


def quarterly_issuer(fx: Fixture, cik: str, ticker: str, base: int) -> list[str]:
    """Four releases (2025 quarters), each with its prior-year comparative."""
    fx.issuer(cik, ticker)
    accs = []
    for i, end in enumerate(Q_ENDS[4:]):
        prior = Q_ENDS[i]
        accs.append(
            fx.release(
                cik,
                end + timedelta(days=35),
                {end: bridge(base + 10 * i, 20, 5), prior: bridge(base, 20, 5)},
            )
        )
    return accs


@pytest.fixture
def fx(tmp_path: Path) -> Fixture:
    return Fixture(tmp_path / "fixture.db")


A = "0000000001"


def test_quarter_uses_latest_release_and_never_falls_back(fx: Fixture) -> None:
    quarterly_issuer(fx, A, "FIXT", 100)
    data = KeyData(fx.store)
    q = data.quarter(A, "3M-2025-03-31")
    assert q is not None and q.release.filed == date(2025, 5, 5)
    # A newer release recasts Q1 2025 but fails its anchor: no key, no fallback.
    fx.release(
        A,
        date(2026, 5, 5),
        {date(2026, 3, 31): bridge(150, 20, 5), Q_ENDS[4]: bridge(99, 20, 5)},
        anchor_ok=False,
    )
    data = KeyData(fx.store)
    assert data.quarter(A, "3M-2025-03-31") is None
    assert data.skips["latest release not verified for the period"] == 1


def test_later_filing_without_bridge_blocks_the_quarter(fx: Fixture) -> None:
    quarterly_issuer(fx, A, "FIXT", 100)
    fx.filing(A, date(2025, 6, 1))  # an 8-K whose bridge was not extracted
    data = KeyData(fx.store)
    assert data.quarter(A, "3M-2025-03-31") is None
    assert data.quarter(A, "3M-2025-06-30") is not None


def test_c2_ltm_and_yoy(fx: Fixture) -> None:
    quarterly_issuer(fx, A, "FIXT", 100)
    cands = {c.key: c for c in c2(KeyData(fx.store))}
    ltm = cands[f"c2-ltm|{A}|3M-2025-12-31"].fields["values"][0]
    # Totals 125, 135, 145, 155.
    assert ltm["value"] == "560" and ltm["period_id"] == "12M-2025-12-31"
    yoy = cands[f"c2-yoy|{A}|3M-2025-06-30"].fields["values"]
    assert yoy[0]["value"] == "135"
    assert yoy[1]["value"] == "8.00"  # (135 - 125) / 125


def test_c2_never_sums_different_metrics(fx: Fixture) -> None:
    fx.issuer(A, "FIXT")
    for i, end in enumerate(Q_ENDS[4:]):
        metric = "EBITDA" if i == 0 else "Adjusted EBITDA (a)"
        fx.release(
            A, end + timedelta(days=35), {end: bridge(100, 20, 5)}, metric=metric
        )
    keys = {c.key for c in c2(KeyData(fx.store))}
    assert not any(k.startswith("c2-ltm") for k in keys)


def test_c3_recast_and_unchanged_control(fx: Fixture) -> None:
    quarterly_issuer(fx, A, "FIXT", 100)
    fx.release(
        A,
        date(2026, 5, 5),
        {date(2026, 3, 31): bridge(150, 20, 5), Q_ENDS[4]: bridge(100, 10, 5)},
    )
    cands = {c.key: c for c in c3(KeyData(fx.store))}
    recast = cands[f"c3|{A}|3M-2025-03-31|total"]
    assert recast.family == "c3_recast"
    first, latest = recast.fields["values"]
    assert (first["value"], latest["value"]) == ("125", "115")
    # Net income is the same in both releases: a control question.
    assert cands[f"c3|{A}|3M-2025-03-31|gaap_start"].family == "c3_unchanged"


def test_c3_skips_a_renamed_metric(fx: Fixture) -> None:
    fx.issuer(A, "FIXT")
    fx.release(A, date(2025, 5, 5), {Q_ENDS[4]: bridge(1, 0, 0)}, metric="EBITDA")
    fx.release(A, date(2026, 5, 5), {Q_ENDS[4]: bridge(50, 20, 5)})
    data = KeyData(fx.store)
    assert [c.key for c in c3(data) if "total" in c.key] == []
    assert data.skips["C3: a different metric or line, not a recast"] >= 1


def test_c5_added_only_and_rename_skipped(fx: Fixture) -> None:
    fx.issuer(A, "FIXT")
    end1, end2, end3 = Q_ENDS[4], Q_ENDS[5], Q_ENDS[6]
    fx.release(A, date(2025, 5, 5), {end1: bridge(100, 20, 5)})
    with_litigation = {
        "Net income": Decimal(100),
        "Depreciation and amortization": Decimal(20),
        "Restructuring": Decimal(5),
        "Litigation": Decimal(7),
        "Adjusted EBITDA": Decimal(132),
    }
    fx.release(A, date(2025, 8, 5), {end2: with_litigation})
    renamed = {
        "Net income": Decimal(100),
        "Depreciation and amortization": Decimal(20),
        "Restructuring": Decimal(5),
        "Legal settlements": Decimal(7),
        "Adjusted EBITDA": Decimal(132),
    }
    fx.release(A, date(2025, 11, 5), {end3: renamed})
    data = KeyData(fx.store)
    cands = list(c5(data))
    assert len(cands) == 1
    fields = cands[0].fields
    assert [lb["label_raw"] for lb in fields["labels"]] == ["Litigation"]
    assert [v["value"] for v in fields["values"]] == ["1", "0"]
    assert data.skips["C5: lines both added and dropped (possible rename)"] == 1


def test_c6_removes_named_items(fx: Fixture) -> None:
    quarterly_issuer(fx, A, "FIXT", 100)
    cands = [
        c
        for c in c6(KeyData(fx.store))
        if c.key == f"c6|{A}|3M-2025-12-31|restructuring"
    ]
    assert len(cands) == 1
    assert cands[0].fields["values"][0]["value"] == "150"  # 155 - 5


def test_c7_ranking_needs_clear_gaps(fx: Fixture) -> None:
    quarterly_issuer(fx, A, "FIXA", 100)
    quarterly_issuer(fx, "0000000002", "FIXB", 300)
    quarterly_issuer(fx, "0000000003", "FIXC", 200)
    rankings = [c.fields["ranking"] for c in c7(KeyData(fx.store))]
    assert rankings == [["FIXB", "FIXC", "FIXA"]]
    quarterly_issuer(fx, "0000000004", "FIXD", 201)  # within 2% of FIXC
    groups = [c.fields["ranking"] for c in c7(KeyData(fx.store))]
    assert ["FIXB", "FIXC", "FIXA"] in groups
    assert not any("FIXC" in g and "FIXD" in g for g in groups)


def test_select_is_deterministic_and_round_robin(fx: Fixture) -> None:
    quarterly_issuer(fx, A, "FIXA", 100)
    quarterly_issuer(fx, "0000000002", "FIXB", 300)
    cands = list(c6(KeyData(fx.store)))
    picked = select(cands, {"c6": 4})
    assert [c.key for c in picked] == [
        c.key for c in select(reversed(cands), {"c6": 4})
    ]
    assert {c.tickers for c in picked} == {("FIXA",), ("FIXB",)}


def _gold_dir(tmp_path: Path) -> Path:
    d = tmp_path / "gold"
    d.mkdir(parents=True)
    rel = release_dict()
    (d / f"{rel['accession']}.json").write_text(json.dumps(rel), encoding="utf-8")
    return d


def test_generate_and_write_round_trip(fx: Fixture, tmp_path: Path) -> None:
    quarterly_issuer(fx, A, "FIXT", 100)
    quarterly_issuer(fx, "0000000002", "FIXB", 300)
    quarterly_issuer(fx, "0000000003", "FIXC", 200)
    gold = release_dict()
    fx.filing(A, date(2027, 6, 1), acc=gold["accession"])  # > 400 days later
    qdir = tmp_path / "questions"
    qdir.mkdir()
    manual: dict[str, Any] = {
        "id": "fbc-c8-manual",
        "split": "dev",
        "category": "must_refuse",
        "question": "What is FIXT's covenant EBITDA under its credit agreement?",
        "as_of": "2026-08-15",
        "tickers": ["FIXT"],
        "expected": {"status": "refused", "reason_codes": ["out_of_scope"]},
        "key_provenance": "human_checked",
        "author": "fixture person",
        "written_on": "2026-10-24",
        "checked_by": "fixture person",
        "checked_on": "2026-10-24",
    }
    (qdir / "dev.jsonl").write_text(json.dumps(manual) + "\n", encoding="utf-8")

    questions, _ = generate(
        fx.store, date(2026, 10, 24), labels_dir=_gold_dir(tmp_path)
    )
    fams = {q.notes.split("|")[0] for q in questions if q.notes}
    assert {"generated from c1", "generated from c2-ltm", "generated from c7"} <= fams
    gold_q = [q for q in questions if q.key_provenance.value == "gold_model_agreement"]
    assert gold_q == []  # the fixture gold labels say verified_by=tieout
    assert all(q.author == AUTHOR for q in questions)

    write(questions, qdir)
    universe = {"FIXT": A, "FIXB": "0000000002", "FIXC": "0000000003"}
    assert validate_dir(qdir, universe) == []
    rows = [
        Question.model_validate_json(line)
        for p in sorted(qdir.glob("*.jsonl"))
        for line in p.read_text(encoding="utf-8").splitlines()
    ]
    assert any(q.id == "fbc-c8-manual" for q in rows)  # other authors kept
    assert len(rows) == len(questions) + 1

    before = {p.name: p.read_bytes() for p in qdir.glob("*.jsonl")}
    again, _ = generate(
        fx.store, date(2026, 11, 1), labels_dir=_gold_dir(tmp_path / "g2")
    )
    write(again, qdir)
    assert {p.name: p.read_bytes() for p in qdir.glob("*.jsonl")} == before
