"""
A-12: the agent loop (ADR-011).

The model calls Footnote's read-only tools and ``compute``, then submits an
``AgentAnswer`` through the ``submit_answer`` tool. The loop, not the model,
enforces the rules that keep numbers deterministic:

- every tool call gets the question's ``as_of``; a later date is capped to it, so
  the agent cannot read filings published after the question's date;
- a submitted answer must pass the provenance gate. A rejection goes back to the
  model with the problems, once; a second rejection becomes a refusal with
  reason ``unverifiable``;
- the step cap, a model refusal, a truncated turn and an answer never submitted
  all end in an explicit refusal and an error string, never a guessed answer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import ValidationError

from app.agent.answer import AgentAnswer, ReasonCode, refusal
from app.agent.gate import Rendered, check, render
from app.agent.model import ModelClient
from app.agent.tools import AgentTools, tool_specs

SUBMIT = "submit_answer"
MAX_STEPS = 16
MAX_TOKENS = 16_000
MAX_GATE_REJECTIONS = 1  # one retry after a rejection

SYSTEM_PROMPT = """You are Footnote's credit research agent. You answer questions \
about how US-listed issuers report and adjust EBITDA, using only Footnote's \
verified record of their earnings releases, through the tools provided.

Rules:
- Numbers: never type a number. Every figure in your answer must be a value ID \
returned by a tool, written as {{vid}} in the text and listed in "values". Dates, \
years and period IDs (e.g. 3M-2026-06-30) may be written. Put as-reported line \
labels in double quotes.
- Arithmetic: use the compute tool (sum, difference, change, pct_change, share, \
ratio, contribution, count) and cite the calc vid it returns. Never calculate \
yourself. An add-back's effect on the total is its contribution.
- Time: answer as of the question's date. Use the most recently reported figure \
unless the question asks for the first-reported one.
- Trust: prefer values marked verified. If the answer needs an unverified value, \
give it with status "partial" and reason "unverifiable".
- Refuse (status "refused", with reason codes) when the issuer is not covered \
(not_covered), the period was not yet reported (period_not_reported), the release \
has no EBITDA measure (metric_not_ebitda), no bridge was extracted (no_bridge), \
the scale is unknown (scale_unknown), the question asks for something outside \
reported EBITDA bridges such as covenant EBITDA or guidance (out_of_scope), or it \
is ambiguous (ambiguous). If the question's premise is false, say so with reason \
"false_premise" and cite the values that show it.
- For definition changes, list the as-reported labels in "labels". For rankings, \
list tickers in order in "ranking".
- Finish by calling submit_answer exactly once."""


def submit_spec() -> dict[str, Any]:
    return {
        "name": SUBMIT,
        "description": "Submit the final answer. Numbers only as {{vid}} placeholders.",
        "input_schema": AgentAnswer.model_json_schema(),
    }


@dataclass
class AgentRun:
    answer: AgentAnswer
    rendered: Rendered | None
    steps: int = 0
    tool_calls: int = 0
    gate_rejections: int = 0
    error: str | None = None
    messages: list[dict[str, Any]] = field(default_factory=list)


def _with_as_of(args: dict[str, Any], as_of: date, name: str) -> dict[str, Any]:
    if name in ("compute", "resolve_issuer"):
        return args
    out = dict(args)
    given = out.get("as_of")
    try:
        later = given is not None and date.fromisoformat(str(given)) > as_of
    except ValueError:
        later = True
    if given is None or later:
        out["as_of"] = as_of.isoformat()
    return out


def run_agent(
    question: str,
    as_of: date,
    tools: AgentTools,
    client: ModelClient,
    max_steps: int = MAX_STEPS,
    max_tokens: int = MAX_TOKENS,
) -> AgentRun:
    specs = [*tool_specs(), submit_spec()]
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": f"As of {as_of.isoformat()}: {question}"}
    ]
    run = AgentRun(answer=refusal(ReasonCode.unverifiable, ""), rendered=None)
    nudged = False

    def stop(error: str) -> AgentRun:
        run.answer = refusal(ReasonCode.unverifiable, f"No verified answer: {error}.")
        run.error = error
        run.messages = messages
        return run

    while run.steps < max_steps:
        run.steps += 1
        turn = client.create(
            system=SYSTEM_PROMPT, messages=messages, tools=specs, max_tokens=max_tokens
        )
        messages.append({"role": "assistant", "content": turn.content})
        if turn.stop_reason == "refusal":
            return stop("the model declined the request")
        if turn.stop_reason == "max_tokens":
            return stop("the model's turn was cut off at max_tokens")
        if not turn.tool_calls:
            if nudged:
                return stop("no answer was submitted")
            nudged = True
            messages.append(
                {
                    "role": "user",
                    "content": "Call submit_answer with your final answer.",
                }
            )
            continue

        results: list[dict[str, Any]] = []
        submitted: tuple[str, dict[str, Any]] | None = None
        for call in turn.tool_calls:
            if call.name == SUBMIT:
                submitted = (call.id, call.input)
                continue
            run.tool_calls += 1
            result = tools.call(call.name, _with_as_of(call.input, as_of, call.name))
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": json.dumps(result.for_model(), default=str),
                    "is_error": result.status == "invalid",
                }
            )
        if submitted is not None:
            call_id, raw = submitted
            problems: list[str]
            try:
                answer = AgentAnswer.model_validate(raw)
                problems = check(answer, tools.ledger).problems
            except ValidationError as exc:
                problems = [f"invalid answer: {exc}"]
            if not problems:
                run.answer = answer
                run.rendered = render(answer, tools.ledger)
                run.messages = messages
                return run
            run.gate_rejections += 1
            if run.gate_rejections > MAX_GATE_REJECTIONS:
                return stop(f"the answer failed the provenance gate: {problems}")
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "content": json.dumps({"rejected": problems}),
                    "is_error": True,
                }
            )
        messages.append({"role": "user", "content": results})
    return stop(f"the step cap ({max_steps}) was reached")
