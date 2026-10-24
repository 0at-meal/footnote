"""
Scripted model clients for tests. They return canned ``ModelTurn``s and never
touch the network; every turn they produce is a fixture, not model output.
"""

from __future__ import annotations

from typing import Any

from app.agent.model import ModelTurn, ToolCall, Usage


def text_turn(text: str, usage: Usage | None = None) -> ModelTurn:
    return ModelTurn(
        content=[{"type": "text", "text": text}],
        stop_reason="end_turn",
        usage=usage or Usage(input_tokens=1000, output_tokens=100),
        model="fixture-model",
        text=text,
    )


def tool_turn(
    *calls: tuple[str, dict[str, Any]], usage: Usage | None = None
) -> ModelTurn:
    tool_calls = [
        ToolCall(f"toolu_{i}", name, args) for i, (name, args) in enumerate(calls)
    ]
    return ModelTurn(
        content=[
            {"type": "tool_use", "id": c.id, "name": c.name, "input": c.input}
            for c in tool_calls
        ],
        stop_reason="tool_use",
        usage=usage or Usage(input_tokens=1000, output_tokens=100),
        model="fixture-model",
        tool_calls=tool_calls,
    )


class FakeClient:
    """Plays back scripted turns in order and records every request."""

    def __init__(self, turns: list[ModelTurn], model: str = "fixture-model") -> None:
        self.turns = list(turns)
        self._model = model
        self.requests: list[dict[str, Any]] = []

    @property
    def model(self) -> str:
        return self._model

    def create(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> ModelTurn:
        self.requests.append(
            {
                "system": system,
                "messages": [dict(m) for m in messages],
                "tools": tools,
                "max_tokens": max_tokens,
            }
        )
        if not self.turns:
            raise AssertionError("FakeClient ran out of scripted turns")
        return self.turns.pop(0)
