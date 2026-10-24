"""
Shared records for Track A runs: what a system answered and what it cost.

Every system (baselines B0–B2, the agent A1) is scored from the same
``SystemAnswer``. Baselines fill it from the model's JSON output. The agent fills
it from rendered value IDs, so its numbers carry their source URL and XPath. One
``Trial`` per (question, system, trial number) is written as a JSONL line.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from tools.agent_eval.questions import LabelChange, ReasonCode, Scale, Status, Unit


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AnswerValue(_Strict):
    name: str = ""
    value: Decimal
    unit: Unit
    scale: Scale | None = None
    period_id: str | None = None
    ticker: str | None = None
    source_url: str | None = None
    xpath: str | None = None
    vid: str | None = None  # set only by the agent
    # A value computed from several cited values (an LTM sum, a percentage) is
    # not expected to appear in any one document, so citation checks skip it.
    computed: bool = False


class AnswerLabel(_Strict):
    label: str
    change: LabelChange
    ticker: str | None = None


class SystemAnswer(_Strict):
    status: Status
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    values: list[AnswerValue] = Field(default_factory=list)
    labels: list[AnswerLabel] = Field(default_factory=list)
    ranking: list[str] = Field(default_factory=list)
    text: str = ""


class Usage(_Strict):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
        )


class Trial(_Strict):
    """One system's attempt at one question. ``answer`` is None when the run
    failed; ``error`` then says why (never a silent default)."""

    question_id: str
    system: str
    trial: int = Field(..., ge=1)
    model: str
    prompt_hash: str
    answer: SystemAnswer | None
    error: str | None = None
    usage: Usage = Usage()
    cost_usd: Decimal = Decimal(0)
    latency_s: float = 0.0
    model_calls: int = 0
    tool_calls: int = 0


def read_trials(path: Path) -> list[Trial]:
    return [
        Trial.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def append_trial(path: Path, trial: Trial) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(trial.model_dump_json() + "\n")
