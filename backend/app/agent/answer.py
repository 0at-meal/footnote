"""
A-11: the agent's answer schema (ADR-011).

The model submits an ``AgentAnswer``. Its prose cites numbers only as
placeholders, ``{{obs:812:3:3M-2026-06-30}}``; ``values`` names each figure the
answer gives, by vid. The provenance gate (``app.agent.gate``) checks it and the
renderer writes the numbers. ``Status`` and ``ReasonCode`` are shared with the
FootnoteBench-Credit question schema.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Status(str, Enum):
    answered = "answered"
    partial = "partial"
    refused = "refused"


class ReasonCode(str, Enum):
    """Why an answer is partial or refused."""

    not_covered = "not_covered"  # issuer outside the universe
    metric_not_ebitda = "metric_not_ebitda"  # e.g. "Adjusted Operating Income"
    no_bridge = "no_bridge"  # no headline bridge found (recorded failure)
    scale_unknown = "scale_unknown"
    period_not_reported = "period_not_reported"
    unclassified_line = "unclassified_line"  # an OTHER line blocks normalization
    out_of_scope = "out_of_scope"  # covenant EBITDA, guidance, segment bridges
    false_premise = "false_premise"
    ambiguous = "ambiguous"
    unverifiable = "unverifiable"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CitedValue(_Strict):
    name: str = Field(..., min_length=1, description="what the figure is, in words")
    vid: str


class CitedLabel(_Strict):
    label: str = Field(..., min_length=1, description="a line label, as reported")
    change: Literal["added", "dropped", "renamed", "recast", "recurring"]
    vid: str | None = None


class AgentAnswer(_Strict):
    status: Status
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    text: str = Field("", description="prose; numbers only as {{vid}} placeholders")
    values: list[CitedValue] = Field(default_factory=list)
    labels: list[CitedLabel] = Field(default_factory=list)
    ranking: list[str] = Field(default_factory=list, description="tickers, in order")


def refusal(reason: ReasonCode, text: str) -> AgentAnswer:
    return AgentAnswer(status=Status.refused, reason_codes=[reason], text=text)
