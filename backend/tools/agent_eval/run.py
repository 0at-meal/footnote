"""
A-07: the FootnoteBench-Credit harness.

Runs systems (baselines B0–B2, the agent A1) over a question split for N trials
and writes one ``Trial`` JSONL line per attempt to ``<out>/<system>.jsonl``,
recording the model, a prompt hash, token usage, cost and latency. A run is
resumable: attempts already on disk are skipped.

**Budget.** Every model call goes through ``BudgetedClient``. Before a call it
reserves a conservative worst case (``max_tokens`` of output plus an
over-estimate of the input) and refuses the call if that could take spend past
the cap; after the call it charges the actual cost from ``eval/agent/pricing.yaml``.
A model without a price cannot be run. When the cap would be crossed the run
stops and says so; nothing is recorded for the unfinished attempt.

``--replay`` re-scores saved transcripts and calls no model.

Usage (from ``backend/``)::

    python -m tools.agent_eval.run --out ../eval/agent/runs/<name> --split dev \\
        --systems B0,B1,B2,A1 --trials 3 --model claude-opus-5-5 --budget-usd 5
    python -m tools.agent_eval.run --out ../eval/agent/runs/<name> --replay
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from app.agent.model import ModelClient, ModelTurn, Usage
from app.store.db import Store

from tools.agent_eval.agent_system import AgentSystem
from tools.agent_eval.baselines import ClosedBook, Corpus, LongContext, Retrieval
from tools.agent_eval.keys import DEFAULT_DB
from tools.agent_eval.questions import QUESTIONS_DIR, Question
from tools.agent_eval.records import Trial, append_trial, read_trials
from tools.agent_eval.score import CitationChecker, load_questions, score
from tools.agent_eval.systems import System

PRICING = Path(__file__).resolve().parents[3] / "eval" / "agent" / "pricing.yaml"
_MTOK = Decimal(1_000_000)
_CHARS_PER_TOKEN_FLOOR = Decimal(2)  # over-estimates input tokens for the reserve


class BudgetExceeded(RuntimeError):
    """The next call could take spend past the cap; the run stops."""


@dataclass(frozen=True)
class Price:
    input: Decimal
    output: Decimal
    cache_read: Decimal
    cache_write: Decimal


def load_pricing(path: Path = PRICING) -> dict[str, Price]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {
        model: Price(**{k: Decimal(str(v)) for k, v in rates.items()})
        for model, rates in data["models"].items()
    }


def cost(price: Price, usage: Usage) -> Decimal:
    return (
        usage.input_tokens * price.input
        + usage.output_tokens * price.output
        + usage.cache_read_tokens * price.cache_read
        + usage.cache_write_tokens * price.cache_write
    ) / _MTOK


class Budget:
    def __init__(self, cap_usd: Decimal) -> None:
        if cap_usd <= 0:
            raise ValueError("the budget cap must be positive")
        self.cap = cap_usd
        self.spent = Decimal(0)


class BudgetedClient:
    """Wraps a model client: refuses calls that could cross the cap, charges each."""

    def __init__(self, inner: ModelClient, price: Price, budget: Budget) -> None:
        self.inner = inner
        self.price = price
        self.budget = budget
        self.usage = Usage()
        self.calls = 0

    @property
    def model(self) -> str:
        return self.inner.model

    def create(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> ModelTurn:
        chars = (
            len(system)
            + len(json.dumps(messages, default=str))
            + len(json.dumps(tools, default=str))
        )
        reserve = (
            Decimal(chars) / _CHARS_PER_TOKEN_FLOOR * self.price.input
            + max_tokens * self.price.output
        ) / _MTOK
        if self.budget.spent + reserve > self.budget.cap:
            raise BudgetExceeded(
                f"spent ${self.budget.spent}; the next call may cost up to "
                f"${reserve.quantize(Decimal('0.0001'))}; cap ${self.budget.cap}"
            )
        turn = self.inner.create(
            system=system, messages=messages, tools=tools, max_tokens=max_tokens
        )
        self.budget.spent += cost(self.price, turn.usage)
        self.usage = self.usage + turn.usage
        self.calls += 1
        return turn


def run(
    questions: list[Question],
    systems: list[System],
    trials: int,
    client_factory: Callable[[], ModelClient],
    price: Price,
    budget: Budget,
    out_dir: Path,
) -> dict[str, Any]:
    """Run every (system, question, trial) not already on disk."""
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {"completed": 0, "skipped": 0, "stopped": None}
    for system in systems:
        path = out_dir / f"{system.name}.jsonl"
        done = (
            {(t.question_id, t.trial) for t in read_trials(path)}
            if path.exists()
            else set()
        )
        for q in questions:
            for n in range(1, trials + 1):
                if (q.id, n) in done:
                    summary["skipped"] += 1
                    continue
                client = BudgetedClient(client_factory(), price, budget)
                before = budget.spent
                started = time.perf_counter()
                try:
                    result = system.answer(q, client)
                except BudgetExceeded as exc:
                    summary["stopped"] = f"budget: {exc}"
                    summary["spent_usd"] = str(budget.spent)
                    return summary
                append_trial(
                    path,
                    Trial(
                        question_id=q.id,
                        system=system.name,
                        trial=n,
                        model=client.model,
                        prompt_hash=result.prompt_hash,
                        answer=result.answer,
                        error=result.error,
                        usage=client.usage,
                        cost_usd=budget.spent - before,
                        latency_s=round(time.perf_counter() - started, 3),
                        model_calls=client.calls,
                        tool_calls=result.tool_calls,
                    ),
                )
                summary["completed"] += 1
    summary["spent_usd"] = str(budget.spent)
    return summary


def available_systems(store: Store) -> dict[str, Callable[[], System]]:
    """Every runnable system: baselines B0-B2 and the agent A1."""
    corpus = Corpus(store)
    return {
        "B0": lambda: ClosedBook(),
        "B1": lambda: Retrieval(corpus),
        "B2": lambda: LongContext(corpus),
        "A1": lambda: AgentSystem(store),
    }


def real_client_factory(model: str) -> Callable[[], ModelClient]:
    """The Anthropic client. Only main() uses it, and only under a budget cap."""
    from app.agent.llm import AnthropicClient  # the SDK loads only for a paid run

    return lambda: AnthropicClient(model)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="run directory")
    parser.add_argument("--questions", type=Path, default=QUESTIONS_DIR)
    parser.add_argument("--split", choices=["dev", "test"])
    parser.add_argument(
        "--replay", action="store_true", help="re-score; no model calls"
    )
    parser.add_argument("--systems", default="")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--model", default="claude-opus-5-5")
    parser.add_argument("--budget-usd", type=Decimal)
    args = parser.parse_args()
    questions = load_questions(args.questions, args.split)
    ids = {q.id for q in questions}

    if not args.replay:
        if args.budget_usd is None:
            parser.error("--budget-usd is required for a run that calls a model")
        pricing = load_pricing()
        if args.model not in pricing:
            parser.error(f"{args.model} has no price in {PRICING}; refusing to run")
        store = Store(DEFAULT_DB)
        registry = available_systems(store)
        names = [s for s in args.systems.split(",") if s]
        unknown = [s for s in names if s not in registry]
        if not names or unknown:
            parser.error(f"unknown systems {unknown}; available: {sorted(registry)}")
        manifest = {
            "started": datetime.now(UTC).isoformat(timespec="seconds"),
            "model": args.model,
            "split": args.split,
            "systems": names,
            "trials": args.trials,
            "budget_usd": str(args.budget_usd),
            "questions": len(questions),
        }
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        summary = run(
            questions,
            [registry[n]() for n in names],
            args.trials,
            real_client_factory(args.model),
            pricing[args.model],
            Budget(args.budget_usd),
            args.out,
        )
        print(json.dumps(summary))
        if summary["stopped"]:
            return 2

    trials = [
        t
        for p in sorted(args.out.glob("*.jsonl"))
        for t in read_trials(p)
        if t.question_id in ids
    ]
    report = score(questions, trials, CitationChecker())
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    for system, r in report.items():
        o = r["overall"]
        print(
            f"{system:8} wrong-number {o['wrong_number_rate']['rate']}  accuracy "
            f"{o['accuracy']['rate']}  pass^{o['pass_hat_k']['k']} "
            f"{o['pass_hat_k']['rate']}  cost ${o['cost_usd']['total']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
