"""
Tests for the A-07 harness. Every model call goes to a scripted fake client;
questions are the synthetic fixtures of the question-schema tests.
"""

from decimal import Decimal
from pathlib import Path

import pytest
from app.agent.model import ModelClient, Usage
from tools.agent_eval.questions import Question
from tools.agent_eval.records import AnswerValue, SystemAnswer, read_trials
from tools.agent_eval.run import (
    Budget,
    BudgetedClient,
    BudgetExceeded,
    Price,
    cost,
    load_pricing,
    run,
)
from tools.agent_eval.score import score
from tools.agent_eval.systems import SystemResult

from tests.agent.fakes import FakeClient, text_turn
from tests.tools.test_agent_questions import question

PRICE = Price(Decimal(4), Decimal(20), Decimal("0.2"), Decimal(5))
QS = [
    Question.model_validate(question()),
    Question.model_validate(question(id="fbc-c1-0002")),
]


class EchoSystem:
    """Fixture system: one model call, then the key's own value as its answer."""

    name = "ECHO"

    def answer(self, q: Question, client: ModelClient) -> SystemResult:
        turn = client.create(
            system="fixture",
            messages=[{"role": "user", "content": q.question}],
            tools=[],
            max_tokens=1000,
        )
        e = q.expected.values[0]
        return SystemResult(
            answer=SystemAnswer(
                status="answered",
                text=turn.text,
                values=[AnswerValue(value=e.value, unit=e.unit, scale=e.scale)],
            ),
            prompt_hash="fixture",
        )


def fresh() -> FakeClient:
    return FakeClient([text_turn("fixture answer")])


def test_pricing_file_and_cost() -> None:
    pricing = load_pricing()
    assert {"claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"} <= set(pricing)
    usage = Usage(
        input_tokens=1_000_000, output_tokens=100_000, cache_read_tokens=500_000
    )
    assert cost(PRICE, usage) == Decimal("6.1")


def test_run_writes_trials_with_cost_and_resumes(tmp_path: Path) -> None:
    budget = Budget(Decimal(1))
    summary = run(QS, [EchoSystem()], 2, fresh, PRICE, budget, tmp_path)
    assert summary["completed"] == 4 and summary["stopped"] is None
    trials = read_trials(tmp_path / "ECHO.jsonl")
    assert len(trials) == 4
    # 1,000 input + 100 output tokens at $4 / $20 per million = $0.006 a trial.
    assert all(t.cost_usd == Decimal("0.006") and t.model_calls == 1 for t in trials)
    assert budget.spent == Decimal("0.024")
    again = run(QS, [EchoSystem()], 2, fresh, PRICE, budget, tmp_path)
    assert again["completed"] == 0 and again["skipped"] == 4
    report = score(QS, read_trials(tmp_path / "ECHO.jsonl"))["ECHO"]["overall"]
    assert report["accuracy"]["rate"] == 1.0 and report["cost_usd"]["total"] == "0.024"


def test_budget_stops_before_crossing_the_cap(tmp_path: Path) -> None:
    # Reserve per call: ~ (chars/2) input tokens + 1,000 output tokens ≈ $0.02+.
    budget = Budget(Decimal("0.03"))
    summary = run(QS, [EchoSystem()], 3, fresh, PRICE, budget, tmp_path)
    assert summary["stopped"] and summary["stopped"].startswith("budget:")
    assert budget.spent <= budget.cap
    assert len(read_trials(tmp_path / "ECHO.jsonl")) == summary["completed"]


def test_budgeted_client_refuses_and_counts() -> None:
    budget = Budget(Decimal("0.01"))
    client = BudgetedClient(fresh(), PRICE, budget)
    with pytest.raises(BudgetExceeded):
        client.create(system="x", messages=[], tools=[], max_tokens=10_000)
    assert client.calls == 0 and budget.spent == 0
    with pytest.raises(ValueError):
        Budget(Decimal(0))
