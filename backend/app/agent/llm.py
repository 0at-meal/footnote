"""
A-12: the Anthropic SDK adapter, the only module that imports an LLM SDK
(ADR-011; enforced by ``test_architecture_boundaries.py``).

It implements ``app.agent.model.ModelClient`` over the Messages API:

- prompt caching on the tool list and the system prompt (both are frozen per
  run, so later requests read them from cache);
- ``output_config.effort`` set explicitly (Claude Opus 5.5 defaults to
  ``medium``); thinking is left adaptive (it cannot be disabled on Opus 5.5);
- the server-side refusal fallback (``fallbacks: "default"``) on models that
  accept it, so a policy decline is retried on a fallback model in the same call;
- no forced ``tool_choice`` (Opus 5.5 rejects it): the loop asks for the
  ``submit_answer`` tool in the prompt instead.

Constructing the client makes no request; ``create`` is the only network call.
The eval harness never runs it without a budget cap (A-07).
"""

from __future__ import annotations

from typing import Any, cast

import anthropic

from app.agent.model import ModelTurn, ToolCall, Usage

FALLBACK_BETA = "server-side-fallback-2026-07-01"
_FALLBACK_MODELS = frozenset(
    {"claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1"}
)


class AnthropicClient:
    def __init__(
        self,
        model: str = "claude-opus-5-5",
        effort: str = "high",
        client: anthropic.Anthropic | None = None,
    ) -> None:
        self._model = model
        self.effort = effort
        self.client = client or anthropic.Anthropic()

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
        cached_tools = [dict(t) for t in tools]
        if cached_tools:
            cached_tools[-1]["cache_control"] = {"type": "ephemeral"}
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ],
            "messages": messages,
            "output_config": {"effort": self.effort},
        }
        if cached_tools:
            kwargs["tools"] = cached_tools
        if self._model in _FALLBACK_MODELS:
            kwargs["betas"] = [FALLBACK_BETA]
            kwargs["fallbacks"] = "default"
        response = self.client.beta.messages.create(**kwargs)
        content = [
            cast(dict[str, Any], b.model_dump(exclude_none=True))
            for b in response.content
        ]
        calls = [
            ToolCall(b.id, b.name, cast(dict[str, Any], b.input))
            for b in response.content
            if b.type == "tool_use"
        ]
        text = "".join(b.text for b in response.content if b.type == "text")
        u = response.usage
        return ModelTurn(
            content=content,
            stop_reason=str(response.stop_reason),
            usage=Usage(
                input_tokens=u.input_tokens,
                output_tokens=u.output_tokens,
                cache_read_tokens=u.cache_read_input_tokens or 0,
                cache_write_tokens=u.cache_creation_input_tokens or 0,
            ),
            model=response.model,
            tool_calls=calls,
            text=text,
        )
