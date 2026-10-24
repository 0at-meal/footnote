"""
A1: the Footnote agent as a FootnoteBench-Credit system (A-12).

A fresh tool session (and ledger) per question; the rendered answer's values
carry their vid, source URL and XPath, so the scorer can check citations.
"""

from __future__ import annotations

from app.agent.loop import SYSTEM_PROMPT, run_agent, submit_spec
from app.agent.model import ModelClient
from app.agent.tools import AgentTools, tool_specs
from app.store.db import Store

from tools.agent_eval.questions import LabelChange, Question, Scale, Unit
from tools.agent_eval.records import AnswerLabel, AnswerValue, SystemAnswer
from tools.agent_eval.systems import SystemResult, prompt_hash


class AgentSystem:
    name = "A1"

    def __init__(self, store: Store) -> None:
        self.store = store

    def answer(self, question: Question, client: ModelClient) -> SystemResult:
        tools = AgentTools(self.store)
        phash = prompt_hash("A1", SYSTEM_PROMPT, tool_specs(), submit_spec())
        run = run_agent(question.question, question.as_of, tools, client)
        a = run.answer
        values = []
        for v in run.rendered.values if run.rendered else []:
            if v.value is None:
                continue
            values.append(
                AnswerValue(
                    name=v.name,
                    value=v.value,
                    unit=Unit(v.unit),
                    scale=Scale(v.scale) if v.scale else None,
                    period_id=v.period_id,
                    ticker=None if "," in v.ticker else v.ticker,
                    source_url=v.source_url,
                    xpath=v.xpath,
                    vid=v.vid,
                    computed=v.computed,
                )
            )
        answer = SystemAnswer(
            status=a.status,
            reason_codes=list(a.reason_codes),
            values=values,
            labels=[
                AnswerLabel(label=lb.label, change=LabelChange(lb.change))
                for lb in a.labels
            ],
            ranking=list(a.ranking),
            text=run.rendered.text if run.rendered else a.text,
        )
        return SystemResult(answer, phash, error=run.error, tool_calls=run.tool_calls)
