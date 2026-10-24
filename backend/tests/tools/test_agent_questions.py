"""
Tests for the A-01 FootnoteBench-Credit question schema and validator. Every
ticker, URL and number here is a synthetic fixture (zero CIK, example values);
none describe a filing.
"""

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from tools.agent_eval.questions import (
    QUESTIONS_DIR,
    Question,
    load_universe,
    validate_dir,
)

URL = "https://www.sec.gov/Archives/edgar/data/1/000000000026000001/ex991.htm"
UNIVERSE = {"FIXT": "0000000001", "FIXB": "0000000002"}


def value(**over: Any) -> dict[str, Any]:
    v: dict[str, Any] = {
        "name": "Adjusted EBITDA",
        "ticker": "FIXT",
        "period_id": "3M-2026-06-30",
        "value": "200",
        "unit": "usd",
        "scale": "millions",
        "tolerance": "0.5",
        "source_urls": [URL],
    }
    v.update(over)
    return v


def question(**over: Any) -> dict[str, Any]:
    q: dict[str, Any] = {
        "schema_version": 1,
        "benchmark": "footnotebench-credit-v0",
        "id": "fbc-c1-0001",
        "split": "dev",
        "category": "point_lookup",
        "question": "What Adjusted EBITDA did FIXT report for the quarter?",
        "as_of": "2026-08-15",
        "tickers": ["FIXT"],
        "expected": {"status": "answered", "values": [value()]},
        "key_provenance": "tieout",
        "author": "fixture",
        "written_on": "2026-10-24",
    }
    q.update(over)
    return q


def refusal(**over: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "id": "fbc-c8-0001",
        "category": "must_refuse",
        "expected": {"status": "refused", "reason_codes": ["scale_unknown"]},
        "key_provenance": "store_status",
    }
    fields.update(over)
    return question(**fields)


def test_valid_point_lookup() -> None:
    q = Question.model_validate(question())
    assert q.expected.values[0].tolerance == Decimal("0.5")
    assert q.expected.values[0].value == 200


def test_valid_refusal_and_false_premise() -> None:
    Question.model_validate(refusal())
    Question.model_validate(
        question(
            id="fbc-c9-0001",
            category="false_premise",
            question="Why did FIXT's Adjusted EBITDA fall 40% this quarter?",
            expected={
                "status": "refused",
                "reason_codes": ["false_premise"],
                "values": [value()],
            },
        )
    )


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda q: q.update(id="Q1"), "id must look like"),
        (lambda q: q["expected"]["values"][0].update(tolerance="5"), "looser than 1%"),
        (lambda q: q["expected"]["values"][0].update(scale=None), "scale is required"),
        (
            lambda q: q["expected"]["values"][0].update(unit="percent"),
            "scale is required",
        ),
        (
            lambda q: q["expected"]["values"][0].update(period_id="Q2-2026"),
            "period_id must look like",
        ),
        (
            lambda q: q["expected"]["values"][0].update(period_id="3M-2026-09-30"),
            "ends after as_of",
        ),
        (
            lambda q: q["expected"]["values"][0].update(
                source_urls=["https://example.com/x.htm"]
            ),
            "not a sec.gov Archives URL",
        ),
        (
            lambda q: q["expected"]["values"][0].update(source_urls=[]),
            "needs its sec.gov source_urls",
        ),
        (
            lambda q: q["expected"]["values"][0].update(ticker="FIXB"),
            "not asked about",
        ),
        (lambda q: q["expected"].update(values=[]), "needs values, labels"),
        (lambda q: q["expected"].update(reason_codes=["ambiguous"]), "no reason codes"),
        (
            lambda q: q.update(
                expected={"status": "refused", "reason_codes": ["ambiguous"]}
            ),
            "must be answerable",
        ),
        (lambda q: q.update(key_provenance="human_checked"), "checked_by"),
        (lambda q: q.update(checked_by="owner"), "go together"),
        (lambda q: q.update(unknown_field=1), "Extra inputs"),
    ],
)
def test_rejects_bad_answerable_questions(mutate: Any, message: str) -> None:
    q = copy.deepcopy(question())
    mutate(q)
    with pytest.raises(ValidationError, match=message):
        Question.model_validate(q)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda q: q["expected"].update(reason_codes=[]), "needs reason codes"),
        (lambda q: q["expected"].update(status="answered"), "no reason codes"),
        (
            lambda q: q["expected"].update(values=[value()]),
            "only to refute a false premise",
        ),
        (lambda q: q.update(key_provenance="tieout"), "need values, labels"),
    ],
)
def test_rejects_bad_refusals(mutate: Any, message: str) -> None:
    q = copy.deepcopy(refusal())
    mutate(q)
    with pytest.raises(ValidationError, match=message):
        Question.model_validate(q)


def test_store_status_key_cannot_carry_values() -> None:
    q = question(
        id="fbc-c9-0002",
        category="false_premise",
        expected={
            "status": "refused",
            "reason_codes": ["false_premise"],
            "values": [value()],
        },
        key_provenance="store_status",
    )
    with pytest.raises(ValidationError, match="store_status keys"):
        Question.model_validate(q)


def test_cross_issuer_ranking_may_name_other_tickers() -> None:
    Question.model_validate(
        question(
            id="fbc-c7-0001",
            category="cross_issuer",
            question="Which covered issuers have the highest add-back intensity?",
            tickers=["FIXT"],
            expected={"status": "answered", "ranking": ["FIXT", "FIXB"]},
        )
    )
    with pytest.raises(ValidationError, match="duplicate ticker"):
        Question.model_validate(
            question(
                id="fbc-c7-0002",
                category="cross_issuer",
                expected={"status": "answered", "ranking": ["FIXT", "FIXT"]},
            )
        )


def test_human_checked_key() -> None:
    Question.model_validate(
        question(
            key_provenance="human_checked",
            checked_by="owner",
            checked_on="2026-10-25",
        )
    )
    with pytest.raises(ValidationError, match="before written_on"):
        Question.model_validate(question(checked_by="owner", checked_on="2026-10-01"))


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_validate_dir_accepts_good_files(tmp_path: Path) -> None:
    _write(tmp_path / "dev.jsonl", [question()])
    _write(tmp_path / "test.jsonl", [refusal(split="test")])
    assert validate_dir(tmp_path, UNIVERSE) == []


def test_validate_dir_reports_file_level_problems(tmp_path: Path) -> None:
    bad_json = question(id="fbc-c1-0003")
    bad_json["expected"]["values"][0]["tolerance"] = "50"
    _write(
        tmp_path / "dev.jsonl",
        [
            question(),
            question(),  # duplicate id
            question(id="fbc-c1-0002", split="test"),  # wrong file
            refusal(tickers=["NOPE"]),  # not in universe, yet not not_covered
            bad_json,
        ],
    )
    (tmp_path / "train.jsonl").write_text("", encoding="utf-8")
    problems = validate_dir(tmp_path, UNIVERSE)
    text = "\n".join(problems)
    assert "train.jsonl: file name" in text
    assert "duplicate id" in text
    assert "split test in dev.jsonl" in text
    assert "not in the universe" in text
    assert "dev.jsonl:5: 1 schema error" in text
    assert len(problems) == 5


def test_not_covered_must_name_an_uncovered_ticker(tmp_path: Path) -> None:
    ok = refusal(
        tickers=["NOPE"],
        expected={"status": "refused", "reason_codes": ["not_covered"]},
    )
    wrong = refusal(
        id="fbc-c8-0002",
        expected={"status": "refused", "reason_codes": ["not_covered"]},
    )
    _write(tmp_path / "dev.jsonl", [ok, wrong])
    problems = validate_dir(tmp_path, UNIVERSE)
    assert problems == [
        "dev.jsonl: fbc-c8-0002: not_covered but every ticker is covered"
    ]


def test_blank_line_is_a_problem(tmp_path: Path) -> None:
    (tmp_path / "dev.jsonl").write_text(
        json.dumps(question()) + "\n\n", encoding="utf-8"
    )
    assert validate_dir(tmp_path, UNIVERSE) == ["dev.jsonl:2: blank line"]


def test_real_universe_and_question_dir_are_valid() -> None:
    universe = load_universe()
    assert len(universe) >= 50
    assert validate_dir(QUESTIONS_DIR, universe) == []
