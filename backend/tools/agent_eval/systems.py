"""What every FootnoteBench-Credit system implements, and what it returns."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

from app.agent.model import ModelClient

from tools.agent_eval.questions import Question
from tools.agent_eval.records import SystemAnswer


@dataclass(frozen=True)
class SystemResult:
    answer: SystemAnswer | None
    prompt_hash: str
    error: str | None = None
    tool_calls: int = 0


class System(Protocol):
    name: str

    def answer(self, question: Question, client: ModelClient) -> SystemResult: ...


def prompt_hash(*parts: Any) -> str:
    blob = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
