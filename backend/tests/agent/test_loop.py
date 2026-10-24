"""
Tests for the A-12 agent loop and model adapter. The store is the synthetic
fixture of the A-02 tests; every model turn is scripted (no network, no spend).
"""

import json
from datetime import date
from pathlib import Path
from typing import Any, cast

import anthropic
import pytest
from anthropic.types.beta import BetaMessage
from app.agent.llm import FALLBACK_BETA, AnthropicClient
from app.agent.loop import run_agent
from app.agent.model import ModelTurn
from app.agent.tools import AgentTools
from tools.agent_eval.agent_system import AgentSystem
from tools.agent_eval.questions import Question
from tools.agent_eval.records import Trial
from tools.agent_eval.score import grade

from tests.agent.fakes import FakeClient, text_turn, tool_turn
from tests.tools.test_agent_keys import Fixture, quarterly_issuer

A = "0000000001"
URL = "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/ex991.htm"
AS_OF = date(2026, 3, 1)
QUESTION = (
    "What is FIXT's LTM Adjusted EBITDA for the four quarters ended December 31, 2025?"
)


@pytest.fixture
def fx(tmp_path: Path) -> Fixture:
    f = Fixture(tmp_path / "s.db")
    quarterly_issuer(f, A, "FIXT", 100)  # 2025 totals 125, 135, 145, 155
    return f


def plan(fx: Fixture) -> tuple[list[str], str]:
    """The vids the scripted model will cite, found with a separate tool session."""
    probe = AgentTools(fx.store)
    q = probe.call(
        "get_quarters", {"ticker": "FIXT", "limit": 4, "as_of": "2026-03-01"}
    )
    vids = [v.vid for v in q.values]
    return vids, probe.call("compute", {"op": "sum", "vids": vids}).values[0].vid


def submit(text: str, values: list[dict[str, str]]) -> tuple[str, dict[str, Any]]:
    return ("submit_answer", {"status": "answered", "text": text, "values": values})


def research(vids: list[str]) -> list[ModelTurn]:
    return [
        tool_turn(("get_quarters", {"ticker": "FIXT", "limit": 4})),
        tool_turn(("compute", {"op": "sum", "vids": vids})),
    ]


def with_stop(turn: ModelTurn, stop_reason: str) -> ModelTurn:
    return ModelTurn(**{**turn.__dict__, "stop_reason": stop_reason})


def test_cited_answer_is_rendered(fx: Fixture) -> None:
    vids, calc = plan(fx)
    cite = "{{" + calc + "}}"
    client = FakeClient(
        [
            *research(vids),
            tool_turn(submit(f"LTM was {cite}.", [{"name": "LTM", "vid": calc}])),
        ]
    )
    run = run_agent(QUESTION, AS_OF, AgentTools(fx.store), client)
    assert run.error is None and run.rendered is not None
    assert "$560 million" in run.rendered.text
    assert run.rendered.values[0].period_id == "12M-2025-12-31"
    assert run.tool_calls == 2 and run.steps == 3
    # The model gave no as_of; the loop supplied the question's.
    result = json.loads(client.requests[1]["messages"][2]["content"][0]["content"])
    assert result["status"] == "ok"


def test_gate_rejection_gets_one_retry(fx: Fixture) -> None:
    vids, calc = plan(fx)
    cite = "{{" + calc + "}}"
    client = FakeClient(
        [
            *research(vids),
            tool_turn(submit("LTM Adjusted EBITDA was 560 million.", [])),
            tool_turn(submit(f"It was {cite}.", [{"name": "LTM", "vid": calc}])),
        ]
    )
    run = run_agent(QUESTION, AS_OF, AgentTools(fx.store), client)
    assert run.gate_rejections == 1 and run.error is None
    rejected = client.requests[3]["messages"][-1]["content"][-1]
    assert rejected["is_error"] and "bare numeral" in rejected["content"]


def test_second_rejection_is_a_refusal(fx: Fixture) -> None:
    client = FakeClient(
        [
            tool_turn(submit("It was 560.", [])),
            tool_turn(submit("{{obs:9:9:3M-2025-03-31}}", [])),
        ]
    )
    run = run_agent(QUESTION, AS_OF, AgentTools(fx.store), client)
    assert run.answer.status.value == "refused"
    assert run.answer.reason_codes[0].value == "unverifiable"
    assert run.error and "provenance gate" in run.error


def test_as_of_is_capped(fx: Fixture) -> None:
    client = FakeClient(
        [
            tool_turn(("get_bridge", {"ticker": "FIXT", "as_of": "2030-01-01"})),
            tool_turn(
                ("submit_answer", {"status": "refused", "reason_codes": ["ambiguous"]})
            ),
        ]
    )
    run_agent(QUESTION, date(2025, 6, 1), AgentTools(fx.store), client)
    result = json.loads(client.requests[1]["messages"][2]["content"][0]["content"])
    assert result["data"]["filed"] == "2025-05-05"  # not a later release


@pytest.mark.parametrize(
    "turns, error",
    [
        (
            [text_turn("I think it is fine."), text_turn("Done.")],
            "no answer was submitted",
        ),
        ([with_stop(text_turn("x"), "refusal")], "declined"),
        ([with_stop(text_turn("x"), "max_tokens")], "max_tokens"),
    ],
)
def test_failures_end_in_explicit_refusals(
    fx: Fixture, turns: list[ModelTurn], error: str
) -> None:
    run = run_agent(QUESTION, AS_OF, AgentTools(fx.store), FakeClient(turns))
    assert run.answer.status.value == "refused" and run.error and error in run.error


def test_step_cap(fx: Fixture) -> None:
    turns = [tool_turn(("resolve_issuer", {"query": "FIXT"})) for _ in range(3)]
    run = run_agent(
        QUESTION, AS_OF, AgentTools(fx.store), FakeClient(turns), max_steps=3
    )
    assert run.error == "the step cap (3) was reached"


def test_agent_system_scores_correct(fx: Fixture) -> None:
    vids, calc = plan(fx)
    client = FakeClient(
        [
            *research(vids),
            tool_turn(submit("{{" + calc + "}}", [{"name": "LTM", "vid": calc}])),
        ]
    )
    q = Question.model_validate(
        {
            "id": "fbc-c2-fixture",
            "split": "dev",
            "category": "multi_period",
            "question": QUESTION,
            "as_of": "2026-03-01",
            "tickers": ["FIXT"],
            "expected": {
                "status": "answered",
                "values": [
                    {
                        "name": "LTM Adjusted EBITDA",
                        "ticker": "FIXT",
                        "period_id": "12M-2025-12-31",
                        "value": "560",
                        "unit": "usd",
                        "scale": "millions",
                        "tolerance": "0",
                        "source_urls": [URL],
                    }
                ],
            },
            "key_provenance": "tieout",
            "author": "fixture",
            "written_on": "2026-10-24",
        }
    )
    result = AgentSystem(fx.store).answer(q, client)
    trial = Trial(
        question_id=q.id,
        system="A1",
        trial=1,
        model="fixture-model",
        prompt_hash=result.prompt_hash,
        answer=result.answer,
    )
    assert grade(q, trial).correct
    assert result.answer is not None and result.answer.values[0].computed


class _StubMessages:
    """Stands in for ``client.beta.messages``; returns a fixture SDK message."""

    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> BetaMessage:
        self.kwargs = kwargs
        return BetaMessage.model_validate(
            {
                "id": "msg_fixture",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-5-5",
                "content": [
                    {"type": "text", "text": "Looking it up."},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "get_bridge",
                        "input": {"ticker": "FIXT"},
                    },
                ],
                "stop_reason": "tool_use",
                "stop_sequence": None,
                "usage": {
                    "input_tokens": 1200,
                    "output_tokens": 80,
                    "cache_read_input_tokens": 900,
                    "cache_creation_input_tokens": 0,
                },
            }
        )


class _StubBeta:
    def __init__(self) -> None:
        self.messages = _StubMessages()


class _StubClient:
    def __init__(self) -> None:
        self.beta = _StubBeta()


def test_adapter_request_shape_and_conversion() -> None:
    stub = _StubClient()
    client = AnthropicClient(client=cast(anthropic.Anthropic, stub))
    turn = client.create(
        system="sys",
        messages=[{"role": "user", "content": "q"}],
        tools=[{"name": "a", "input_schema": {}}, {"name": "b", "input_schema": {}}],
        max_tokens=100,
    )
    kw = stub.beta.messages.kwargs
    assert kw["model"] == "claude-opus-5-5" and kw["output_config"] == {
        "effort": "high"
    }
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" in kw["tools"][-1] and "cache_control" not in kw["tools"][0]
    assert kw["betas"] == [FALLBACK_BETA] and kw["fallbacks"] == "default"
    assert "tool_choice" not in kw
    assert turn.tool_calls[0].name == "get_bridge" and turn.text == "Looking it up."
    assert turn.usage.cache_read_tokens == 900 and turn.stop_reason == "tool_use"
