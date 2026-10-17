"""
Tests for the P0-08 scorer. Every table, identifier and number here is a
synthetic fixture (zero CIK, example values); none describe a real filing.
"""

import gzip
import hashlib
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml
from tools.eval.score import (
    ExtractedValue,
    ExtractorOutput,
    PeriodHint,
    ScoreError,
    aggregate,
    parse_period_hint,
    resolve_period,
    run_extractor,
    score_gold_set,
    score_release,
)
from tools.gold.labels import GoldRelease, Scale

ACC = "0000000000-26-000001"
EXHIBIT = "ex991.htm"
URL = f"https://www.sec.gov/Archives/edgar/data/1/000000000026000001/{EXHIBIT}"
P26 = "3M-2026-06-30"
P25 = "3M-2025-06-30"

HTML = b"""<html><body>
<p>Fixture release. Not a real filing.</p>
<table><tr><td>Revenue</td><td>1</td></tr></table>
<table>
<caption>Reconciliation of Net Income to Adjusted EBITDA (in millions)</caption>
<tr><td></td><td>Three Months Ended June 30, 2026</td>
<td>Three Months Ended June 30, 2025</td></tr>
<tr><td>Net income (loss)</td><td>50</td><td>(10)</td></tr>
<tr><td>Interest expense</td><td>40</td><td>30</td></tr>
<tr><td>Depreciation and amortization</td><td>60</td><td>55</td></tr>
<tr><td>Less: gain on sale</td><td>5</td><td>\xe2\x80\x94</td></tr>
<tr><td>Adjusted EBITDA</td><td>145</td><td>75</td></tr>
</table></body></html>"""


def _v(period: str, raw: str, value: str | None, by: str) -> dict[str, Any]:
    return {
        "period_id": period,
        "value_raw": raw,
        "value": value,
        "verified_by": by,
        "labeler": "fixture",
        "labeled_on": "2026-10-17",
    }


def _line(order: int, label: str, role: str, sign: int, *vals: Any) -> dict[str, Any]:
    return {
        "row_order": order,
        "label_raw": label,
        "role": role,
        "sign": sign,
        "values": list(vals),
    }


def gold_dict(table_index: int = 1) -> dict[str, Any]:
    ma = "model_agreement"
    return {
        "ticker": "FIXT",
        "cik": "0000000001",
        "accession": ACC,
        "exhibit": EXHIBIT,
        "source_url": URL,
        "sha256": hashlib.sha256(HTML).hexdigest(),
        "metric_label_raw": "Adjusted EBITDA",
        "scale": "millions",
        "scale_quote": "(in millions)",
        "table": {"table_index": table_index},
        "periods": [
            {
                "period_id": P26,
                "label_raw": "Three Months Ended June 30, 2026",
                "end_date": "2026-06-30",
                "months": 3,
            },
            {
                "period_id": P25,
                "label_raw": "Three Months Ended June 30, 2025",
                "end_date": "2025-06-30",
                "months": 3,
            },
        ],
        "lines": [
            _line(
                0,
                "Net income (loss)",
                "gaap_start",
                1,
                _v(P26, "50", "50", ma),
                _v(P25, "(10)", "-10", "human"),
            ),
            _line(
                1,
                "Interest expense",
                "adjustment",
                1,
                _v(P26, "40", "40", ma),
                _v(P25, "30", "30", ma),
            ),
            _line(
                2,
                "Depreciation and amortization",
                "adjustment",
                1,
                _v(P26, "60", "60", ma),
                _v(P25, "55", "55", ma),
            ),
            _line(
                3,
                "Less: gain on sale",
                "adjustment",
                -1,
                _v(P26, "5", "5", ma),
                _v(P25, "—", None, ma),
            ),
            _line(
                4,
                "Adjusted EBITDA",
                "total",
                1,
                _v(P26, "145", "145", "human"),
                _v(P25, "75", "75", ma),
            ),
        ],
    }


def gold(**overrides: Any) -> GoldRelease:
    return GoldRelease.model_validate({**gold_dict(), **overrides})


def _ev(
    row: int, label: str, period: str | None, raw: str, direction: int = 1
) -> ExtractedValue:
    num = Decimal(raw.strip("()")) * (-1 if raw.startswith("(") else 1)
    return ExtractedValue(row, label, period, raw, num, direction)


def output(
    values: list[ExtractedValue], table: int = 1, title: str = "x (in millions)"
) -> ExtractorOutput:
    return ExtractorOutput(
        status="success",
        not_found_reason=None,
        candidate_tables=(table, 5),
        table_index=table,
        table_title=title,
        scale=Scale.millions if "millions" in title else None,
        scale_reason=None if "millions" in title else "no caption",
        values=tuple(values),
    )


# ---------------------------------------------------------------- periods


def test_period_hint_forms() -> None:
    assert parse_period_hint("Three Months Ended June 30, 2026").months == 3
    assert parse_period_hint("June 30, 2026").end_date is not None
    assert parse_period_hint("Q2 FY26") == PeriodHint(None, 2026, 3)
    assert parse_period_hint("2025") == PeriodHint(None, 2025, None)
    assert parse_period_hint(None) == PeriodHint(None, None, None)


def test_resolve_period_unique_ambiguous_wrong_missing() -> None:
    periods = gold().periods
    assert resolve_period("2026", periods) == (P26, "ok")
    assert resolve_period("2024", periods) == (None, "period_wrong")
    assert resolve_period(None, periods) == (None, "period_missing")
    six = GoldRelease.model_validate(
        {
            **gold_dict(),
            "periods": [
                *gold_dict()["periods"][:1],
                {
                    "period_id": "6M-2026-06-30",
                    "label_raw": "Six Months Ended June 30, 2026",
                    "end_date": "2026-06-30",
                    "months": 6,
                },
            ],
            "lines": [
                {
                    **ln,
                    "values": [
                        ln["values"][0],
                        {**ln["values"][0], "period_id": "6M-2026-06-30"},
                    ],
                }
                for ln in gold_dict()["lines"]
            ],
        }
    )
    assert resolve_period("June 30, 2026", six.periods) == (None, "period_ambiguous")
    assert resolve_period("Six Months Ended June 30, 2026", six.periods)[0] == (
        "6M-2026-06-30"
    )


# ---------------------------------------------------------------- scoring


def _perfect() -> list[ExtractedValue]:
    rows = [
        (1, "Net income (loss)", ["50", "(10)"]),
        (2, "Interest expense", ["40", "30"]),
        (3, "Depreciation and amortization", ["60", "55"]),
        (4, "Less: gain on sale", ["5"]),
        (5, "Adjusted EBITDA", ["145", "75"]),
    ]
    out = []
    for idx, label, raws in rows:
        for raw, per in zip(raws, ["2026", "2025"]):
            direction = -1 if raw.startswith("(") or label.startswith("Less") else 1
            out.append(_ev(idx, label, per, raw, direction))
    return out


def test_perfect_extraction_scores_every_value() -> None:
    score = score_release(gold(), output(_perfect()))
    assert score.null_values == 1
    assert len(score.outcomes) == 9
    assert all(o.line_exact and o.sign_ok and o.scale_ok for o in score.outcomes)
    assert score.gold_table_rank == 1


def test_wrong_table_fails_lines_and_signs() -> None:
    score = score_release(gold(), output(_perfect(), table=0))
    assert {o.line_failure for o in score.outcomes} == {"wrong_table"}
    assert {o.sign_failure for o in score.outcomes} == {"not_located"}
    assert score.gold_table_rank is None


def test_period_label_and_value_failures_are_classified() -> None:
    values = _perfect()
    values[0] = _ev(1, "Net income (loss)", None, "50")  # no period string
    values[2] = _ev(2, "Interest exp.", "2026", "40")  # label differs
    values[3] = _ev(2, "Interest exp.", "2025", "30")
    values[4] = _ev(3, "Depreciation and amortization", "2026", "61")
    by_label = {
        (o.label, o.period_id): o
        for o in score_release(gold(), output(values)).outcomes
    }
    net = by_label[("Net income (loss)", P26)]
    assert net.line_failure == "period_missing"
    assert net.line_label_value and not net.line_exact
    assert by_label[("Interest expense", P26)].line_failure == "label_not_found"
    assert by_label[("Depreciation and amortization", P26)].line_failure == (
        "value_mismatch"
    )


def test_sign_compares_contribution_direction() -> None:
    values = _perfect()
    values[6] = _ev(4, "Less: gain on sale", "2026", "5", direction=1)
    outcome = next(
        o
        for o in score_release(gold(), output(values)).outcomes
        if o.label == "Less: gain on sale"
    )
    assert outcome.sign_failure == "direction_wrong"
    assert outcome.line_exact  # value and period right, direction wrong


def test_missing_scale_is_a_failure_not_a_guess() -> None:
    score = score_release(gold(), output(_perfect(), title="Table 2"))
    assert {o.scale_failure for o in score.outcomes} == {"scale_not_detected"}


def test_aggregate_splits_by_verified_by() -> None:
    values = _perfect()
    values[1] = _ev(1, "Net income (loss)", "2025", "(11)", -1)  # the human value
    report = aggregate([score_release(gold(), output(values))], {"fixture": True})
    line = report["metrics"]["line_exact_match"]
    assert line["overall"] == {"n": 9, "correct": 8, "rate": 0.8889}
    assert line["by_verified_by"]["human"] == {"n": 2, "correct": 1, "rate": 0.5}
    assert line["by_verified_by"]["tieout"] == {"n": 0, "correct": 0, "rate": None}
    assert report["failures"]["line_exact_match"]["value_mismatch"]["count"] == 1
    assert report["metrics"]["table_found"]["releases"]["correct"] == 1


# ---------------------------------------------------------------- end to end


def test_run_extractor_on_synthetic_release() -> None:
    out = run_extractor(HTML, ACC, EXHIBIT, URL, "0000000001")
    assert out.table_index == 1
    assert out.scale is Scale.millions
    score = score_release(gold(), out)
    assert all(o.line_exact for o in score.outcomes)
    assert all(o.sign_ok for o in score.outcomes)


def _gold_dir(tmp_path: Path, html: bytes = HTML) -> Path:
    raw = tmp_path / "raw"
    (raw / ACC).mkdir(parents=True)
    (raw / ACC / f"{EXHIBIT}.gz").write_bytes(gzip.compress(html, mtime=0))
    manifest = {
        "releases": [
            {
                "ticker": "FIXT",
                "cik": "0000000001",
                "accession": ACC,
                "exhibit": EXHIBIT,
                "url": URL,
                "sha256": hashlib.sha256(HTML).hexdigest(),
                "path": f"{ACC}/{EXHIBIT}.gz",
            }
        ]
    }
    (raw / "manifest.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    (tmp_path / "labels").mkdir()
    (tmp_path / "labels" / f"{ACC}.json").write_text(
        json.dumps(gold_dict()), encoding="utf-8"
    )
    return tmp_path


def test_score_gold_set_is_deterministic(tmp_path: Path) -> None:
    gold_dir = _gold_dir(tmp_path)
    first = score_gold_set(gold_dir)
    assert first == score_gold_set(gold_dir)
    assert first["gold"]["verified_by"] == {
        "tieout": 0,
        "model_agreement": 8,
        "human": 2,
    }
    assert first["metrics"]["line_exact_match"]["overall"]["rate"] == 1.0


def test_tampered_exhibit_raises(tmp_path: Path) -> None:
    gold_dir = _gold_dir(tmp_path, html=HTML.replace(b"145", b"146"))
    with pytest.raises(ScoreError, match="sha256"):
        score_gold_set(gold_dir)


def test_scorer_never_imports_network_code() -> None:
    code = (
        "import sys, tools.eval.score; "
        "print(any(m.startswith('app.ingestion') for m in sys.modules))"
    )
    backend = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=backend,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "False"
