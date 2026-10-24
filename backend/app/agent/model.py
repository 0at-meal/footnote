"""
The model-client interface the agent loop and the eval harness depend on.

No SDK is imported here: ``app/agent/llm.py`` adapts the Anthropic SDK to this
interface, and tests use scripted fakes. Messages use the Messages API shape
(``role`` plus a list of content blocks), and a ``ModelTurn`` keeps the raw
response blocks so the caller can append them back unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict


class Usage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

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


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ModelTurn:
    content: list[dict[str, Any]]  # the response blocks, to append back unchanged
    stop_reason: str  # end_turn | tool_use | max_tokens | refusal | ...
    usage: Usage
    model: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    text: str = ""


class ModelClient(Protocol):
    @property
    def model(self) -> str: ...

    def create(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> ModelTurn: ...
