# ADR-011: Track A — an evaluated agent that cites numbers by reference and never writes them

- **Status:** Accepted (owner approval of `docs/agent/PLAN.md`, 2026-10-24)
- **Date:** 2026-10-24
- **Deciders:** owner; drafted by the agent run of 2026-10-24
- **Phase introduced:** Track A, which runs alongside the phases (see ROADMAP §7, Track A)

## Context

The owner wants an AI agent on top of Footnote that credit analysts would adopt at once. The
plan is [docs/agent/PLAN.md](../agent/PLAN.md). The agent must not become another "chat with a
10-K" demo. Public benchmarks show that tool-using frontier models still give wrong answers on a
large share of SEC-filing questions, and that accuracy falls further on multi-period and
cross-company questions. Those are the question types credit work needs (PLAN.md, Context).

The roadmap has no agent, and three standing rules stand in its way:
- only `ingestion/edgar/` touches the network;
- no module imports an LLM SDK;
- no LLM produces or alters a served number.

Phase 0's gate is still open (rows 4 and 5, owner-only). ADR-010 already built Phases 1–4
engineering ahead of the gate on the owner's instruction, without changing any gate.

## Decision

1. **Track A is a separate, gated track.** It runs alongside the phases and does not open,
   close or change any phase gate. Its tickets are A-00 to A-20 (ROADMAP §7, Track A). Its exit
   gate is the Track A gate below. No accuracy figure from it is shown to customers or
   published before both that gate and P4-13 are met.
2. **The evaluation comes first.** FootnoteBench-Credit v0 (A-01 to A-08): a question set with
   deterministic answer keys, a frozen hashed test split, a deterministic scorer and three
   baselines. The agent (A-09 onward) is built against it, not the other way round.
3. **Numbers by reference.** The agent never writes a number an analyst will read.
   - Tools return each value with a stable value ID (`vid`): `obs:…` for a stored observation,
     `calc:…` for a deterministic computation.
   - The model writes prose with placeholders. A deterministic renderer substitutes the value
     and its sec.gov link.
   - A deterministic **provenance gate** rejects an answer that contains:
     - a bare numeral outside an allow-list (years, period labels, names);
     - an unknown vid;
     - a vid not retrieved in that session.

     A rejected answer gets one retry. If that also fails, the answer becomes `refused`,
     reason `unverifiable`.

   So the CLAUDE.md rule "never let an LLM produce or alter a served numeric value" holds by
   construction, and the gate is tested.
4. **Refusal is an answer.** Every answer has a status (`answered`, `partial`, `refused`) and,
   when not answered, a reason code. Refusal behaviour is measured: correct refusals on
   must-refuse and false-premise questions, and over-refusal on answerable ones.
5. **Scoped exceptions to the boundary rules.** They are added to
   `test_architecture_boundaries.py` in the ticket that first needs them (A-08 for baselines,
   A-12 for the agent loop), not before:
   - an LLM SDK may be imported only by `app/agent/llm.py` and `tools/agent_eval/`;
   - that module is the only network code outside `ingestion/edgar/`, and it calls the model
     API only, never EDGAR;
   - `app/agent/` never imports `ingestion/` or `pipeline/`, and never writes to the store;
   - agent tools never import the LLM module.
6. **Model.** Claude through the Anthropic API, with the key in an environment variable or a
   GitHub secret, never in the repository or chat. Model IDs and prices are read from current
   documentation at build time. Every eval run records the model ID and prompt hash, and stops
   at an owner-set budget cap in USD.
7. **Track A gate** (owner may adjust; changes go in DECISIONS):
   - wrong-number rate ≤ 1% on answered test questions, overall and on the gold-keyed slice;
   - correct refusal ≥ 90% on must-refuse and false-premise questions;
   - over-refusal ≤ 10% on answerable questions;
   - pass^3 reported for every system;
   - the agent beats the long-context baseline (B2) on wrong-number rate, with the gap and N
     stated;
   - a human check of 30 agent answers against sec.gov (A-17).

## Consequences

- Footnote can ship an agent and an MCP server without weakening "deterministic numbers":
  the only thing the model chooses is *which* verified value to cite. That choice can be
  wrong (wrong period, wrong line), and the eval measures exactly that.
- `tieout`-keyed questions test retrieval and reasoning, not extraction, because the agent
  reads the same store as the key generator. Every metric is reported split by key
  provenance, so this is visible.
- The project takes on its first paid dependency, the model API, before revenue. This is
  bounded by the per-run budget cap and an owner-set monthly limit. ADR-009 is otherwise
  unchanged, and no hosting is added.
- Eval transcripts are saved, so scores can be re-computed offline (`--replay`) and CI needs
  no API key.
