"""
Tests for the A-08 baselines. The store, cached exhibits and model replies are
synthetic fixtures; the model is a scripted fake client.
"""

import json
from datetime import date
from pathlib import Path

import pytest
from tools.agent_eval import baselines
from tools.agent_eval.baselines import (
    BM25,
    ClosedBook,
    Corpus,
    LongContext,
    Retrieval,
    parse_answer,
)
from tools.agent_eval.questions import Question

from tests.agent.fakes import FakeClient, text_turn
from tests.tools.test_agent_keys import Fixture
from tests.tools.test_agent_questions import question

A = "0000000001"
Q = Question.model_validate(question())  # FIXT, as of 2026-08-15
GOOD = json.dumps(
    {
        "status": "answered",
        "values": [
            {
                "name": "Adjusted EBITDA",
                "value": 200,
                "unit": "usd",
                "scale": "millions",
                "period_id": "3M-2026-06-30",
            }
        ],
        "text": "FIXT reported Adjusted EBITDA of $200 million.",
    }
)


def corpus(tmp_path: Path) -> Corpus:
    fx = Fixture(tmp_path / "s.db")
    fx.issuer(A, "FIXT")
    cache = tmp_path / "cache"
    for filed, body in (
        (date(2026, 5, 5), "Restructuring charges rose. " * 40),
        (
            date(2026, 8, 5),
            "<table><tr><td>Adjusted EBITDA</td><td>200</td></tr></table>",
        ),
        (date(2026, 11, 5), "Filed after as_of: must never be shown."),
    ):
        acc = fx.filing(A, filed)
        (cache / acc).mkdir(parents=True)
        (cache / acc / "ex991.htm").write_text(f"<html><body>{body}</body></html>")
    return Corpus(fx.store, cache)


def test_corpus_respects_as_of_and_keeps_table_rows(tmp_path: Path) -> None:
    exhibits = corpus(tmp_path).exhibits(["FIXT"], date(2026, 8, 15))
    assert [e.filed for e in exhibits] == [date(2026, 8, 5), date(2026, 5, 5)]
    assert "Adjusted EBITDA | 200" in exhibits[0].text


def test_bm25_ranks_the_matching_chunk_first() -> None:
    index = BM25(["restructuring charges rose", "adjusted ebitda was 200", "weather"])
    assert index.top("What was adjusted EBITDA?", 2) == [1]


def test_b0_sends_only_the_question_and_parses() -> None:
    client = FakeClient([text_turn(f"Here you go: {GOOD}")])
    result = ClosedBook().answer(Q, client)
    assert result.error is None and result.answer is not None
    assert result.answer.values[0].value == 200
    sent = client.requests[0]["messages"][0]["content"]
    assert sent.startswith("Question (as of 2026-08-15") and sent.count("\n") == 1


def test_b1_and_b2_build_context_from_filings(tmp_path: Path) -> None:
    c = corpus(tmp_path)
    for system in (Retrieval(c), LongContext(c)):
        client = FakeClient([text_turn(GOOD)])
        system.answer(Q, client)
        body = client.requests[0]["messages"][0]["content"]
        assert "Adjusted EBITDA | 200" in body and "must never be shown" not in body
        assert "https://www.sec.gov/Archives/edgar/data/1/" in body


def test_b2_stops_at_the_character_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(baselines, "B2_CHAR_BUDGET", 200)
    client = FakeClient([text_turn(GOOD)])
    LongContext(corpus(tmp_path)).answer(Q, client)
    assert "Restructuring" not in client.requests[0]["messages"][0]["content"]


def test_invalid_output_and_refusal_are_errors() -> None:
    assert parse_answer("no json here")[1] == "invalid output: no JSON object"
    bad = parse_answer('{"status": "maybe"}')
    assert bad[0] is None and bad[1] and bad[1].startswith("invalid output")
    refused = text_turn(GOOD)
    refused = refused.__class__(**{**refused.__dict__, "stop_reason": "refusal"})
    result = ClosedBook().answer(Q, FakeClient([refused]))
    assert result.answer is None and result.error == "stop_reason refusal"
