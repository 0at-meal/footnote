"""
Tests for the A-06 scorer. Questions, transcripts and the cached exhibit are
synthetic fixtures (FIX* tickers, zero CIK); no model was run.
"""

from decimal import Decimal
from pathlib import Path
from typing import Any

from tools.agent_eval.questions import Question
from tools.agent_eval.records import (
    AnswerValue,
    SystemAnswer,
    Trial,
    append_trial,
    read_trials,
)
from tools.agent_eval.score import (
    CitationChecker,
    grade,
    oracle_trials,
    score,
    value_matches,
)

from tests.tools.test_agent_questions import URL, question, refusal, value

LOOKUP = Question.model_validate(question())  # FIXT Adjusted EBITDA = 200 (millions)
C8 = Question.model_validate(refusal())  # expects refused / scale_unknown
PREMISE = Question.model_validate(
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


def v(amount: str, **over: Any) -> AnswerValue:
    fields: dict[str, Any] = {
        "value": Decimal(amount),
        "unit": "usd",
        "scale": "millions",
    }
    fields.update(over)
    return AnswerValue.model_validate(fields)


def trial(qid: str, answer: SystemAnswer | None, n: int = 1, **over: Any) -> Trial:
    fields: dict[str, Any] = {
        "question_id": qid,
        "system": "FIX",
        "trial": n,
        "model": "fixture-model",
        "prompt_hash": "fixture",
        "answer": answer,
    }
    fields.update(over)
    return Trial.model_validate(fields)


def answered(*values: AnswerValue) -> SystemAnswer:
    return SystemAnswer(status="answered", values=list(values))


def refused(*codes: str, values: tuple[AnswerValue, ...] = ()) -> SystemAnswer:
    return SystemAnswer.model_validate(
        {"status": "refused", "reason_codes": list(codes), "values": list(values)}
    )


def test_value_matching_scales_and_checks_period() -> None:
    e = LOOKUP.expected.values[0]
    assert value_matches(v("200"), e)
    assert value_matches(v("200000", scale="thousands"), e)
    assert value_matches(v("0.2", scale="billions"), e)
    assert not value_matches(v("200", scale="thousands"), e)
    assert not value_matches(v("200", scale=None), e)  # dollars without a scale
    assert not value_matches(v("200", period_id="3M-2025-06-30"), e)
    assert not value_matches(v("200", ticker="FIXB"), e)
    assert not value_matches(v("200", unit="percent", scale=None), e)


def test_grades_for_an_answerable_question() -> None:
    right = grade(LOOKUP, trial(LOOKUP.id, answered(v("200"))))
    assert right.correct and not right.wrong_number
    extra = grade(LOOKUP, trial(LOOKUP.id, answered(v("200"), v("999"))))
    assert extra.wrong_number and not extra.correct
    wrong = grade(LOOKUP, trial(LOOKUP.id, answered(v("201"))))
    assert wrong.wrong_number and not wrong.correct
    missing = grade(LOOKUP, trial(LOOKUP.id, answered()))
    assert not missing.correct and not missing.wrong_number
    over = grade(LOOKUP, trial(LOOKUP.id, refused("ambiguous")))
    assert over.outcome == "refused" and not over.answered
    err = grade(LOOKUP, trial(LOOKUP.id, None, error="fixture: timeout"))
    assert err.outcome == "error" and not err.correct


def test_grades_for_refusals_and_false_premises() -> None:
    assert grade(C8, trial(C8.id, refused("scale_unknown"))).correct
    wrong_reason = grade(C8, trial(C8.id, refused("ambiguous")))
    assert wrong_reason.status_ok and not wrong_reason.reason_ok
    number = grade(C8, trial(C8.id, answered(v("200"))))
    assert number.wrong_number and not number.correct
    corrected = SystemAnswer.model_validate(
        {
            "status": "answered",
            "reason_codes": ["false_premise"],
            "values": [v("200").model_dump()],
        }
    )
    assert grade(PREMISE, trial(PREMISE.id, corrected)).correct
    bad = refused("false_premise", values=(v("180"),))
    assert grade(PREMISE, trial(PREMISE.id, bad)).wrong_number


def test_score_metrics_and_pass_hat_k() -> None:
    trials = [
        trial(LOOKUP.id, answered(v("200")), 1, cost_usd="0.01", latency_s=1.0),
        trial(LOOKUP.id, answered(v("201")), 2, cost_usd="0.01", latency_s=3.0),
        trial(C8.id, refused("scale_unknown"), 1, cost_usd="0.02", latency_s=2.0),
        trial(C8.id, refused("scale_unknown"), 2, cost_usd="0.02", latency_s=2.0),
    ]
    report = score([LOOKUP, C8, PREMISE], trials)["FIX"]
    o = report["overall"]
    assert o["wrong_number_rate"] == {"rate": 0.5, "n": 1, "of": 2}
    assert o["accuracy"]["n"] == 3 and o["accuracy"]["of"] == 4
    assert o["correct_refusal"]["rate"] == 1.0
    assert o["pass_hat_k"] == {"k": 2, "rate": 0.5, "n": 1, "of": 2}
    assert o["pass_at_k"]["rate"] == 1.0
    assert o["cost_usd"]["total"] == "0.06" and o["cost_usd"]["per_correct"] == "0.02"
    assert o["confusion"]["expected_answer"] == {"answered": 2}
    assert report["unanswered_questions"] == [PREMISE.id]
    assert set(report["by_key_provenance"]) == {"store_status", "tieout"}
    assert report["by_key_provenance"]["store_status"]["accuracy"]["rate"] == 1.0


def test_unknown_question_is_an_error() -> None:
    try:
        score([LOOKUP], [trial("fbc-c1-unknown", answered())])
    except ValueError as exc:
        assert "unknown question" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_citation_checker_reads_the_cached_exhibit(tmp_path: Path) -> None:
    doc = tmp_path / "0000000000-26-000001" / "ex991.htm"
    doc.parent.mkdir()
    doc.write_text(
        "<html><body><table><tr><td>Adjusted EBITDA</td><td>$ 1,200</td></tr>"
        "<tr><td>Net loss</td><td>(45)</td></tr></table></body></html>",
        encoding="utf-8",
    )
    checker = CitationChecker(tmp_path)
    assert checker.valid(v("1200", source_url=URL))
    assert checker.valid(v("-45", source_url=URL))
    assert not checker.valid(v("1300", source_url=URL))
    assert checker.valid(
        v("1200", source_url=URL, xpath="/html/body/table/tr[1]/td[2]")
    )
    assert not checker.valid(v("1200", source_url=URL, xpath="/html/body/table/tr[2]"))
    other = URL.replace("000000000026000001", "000000000026000002")
    assert not checker.valid(v("1200", source_url=other))  # not cached
    g = grade(LOOKUP, trial(LOOKUP.id, answered(v("200", source_url=URL))), checker)
    assert (g.values_cited, g.values_cited_valid) == (1, 0)


def test_trials_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "run" / "FIX.jsonl"
    t = trial(LOOKUP.id, answered(v("200")))
    append_trial(path, t)
    append_trial(path, trial(LOOKUP.id, None, 2, error="fixture: invalid JSON"))
    back = read_trials(path)
    assert back[0] == t and back[1].error == "fixture: invalid JSON"


def test_oracle_keys_grade_as_correct() -> None:
    report = score([LOOKUP, C8, PREMISE], oracle_trials([LOOKUP, C8, PREMISE]))
    o = report["ORACLE"]["overall"]
    assert o["accuracy"]["rate"] == 1.0 and o["wrong_number_rate"]["rate"] == 0.0
