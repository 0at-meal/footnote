# Working on Footnote

Read [ARCHITECTURE.md](ARCHITECTURE.md) and [docs/ROADMAP.md](docs/ROADMAP.md)
first. **Current phase: 0** (ground truth, ICP validation, normalization spec).
Work only on tickets of the current phase; a phase opens only when the previous
phase's exit gate is met and recorded in `eval/RESULTS.md`. Do not build an API,
UI, database or orchestration layer before the phase that introduces it.
**Track A** (evaluated agent, [ADR-011](docs/adr/ADR-011-agent-numbers-by-reference.md),
[docs/agent/PLAN.md](docs/agent/PLAN.md)) runs alongside the phases; its tickets
(A-xx) may be worked on now, in order, and change no phase gate.

## Commands

- `make check`: lint, format check, mypy strict, tests. Must pass before you
  commit. Without `make` (e.g. Windows), run `ruff check backend`,
  `ruff format --check backend`, `mypy`, and `cd backend && pytest`.
- `cd backend && pytest path/to/test.py`: run a single test file.
- Imports are rooted at `backend/` (`from app.extraction.models import ...`).

## Rules

- Gates, not dates. Atomic tickets: ≤1 day, one concern, one PR, with tests.
- Public filing data is global (keyed by CIK + accession + period); customer data
  is tenant-scoped. Reported values are append-only observations, never overwritten.
- An LLM may at most *suggest labels* for human confirmation, and only where the
  roadmap allows it (P3-08). Exception: as an independent second reader of gold-set
  filings (P0-05b). That output is evaluation data, never served, and every gold
  label records `verified_by` (`tieout` / `model_agreement` / `human`).
- Served numbers come only from deterministic code. Never let an LLM produce or alter
  a served numeric value (the P0-05b gold-set reading above is evaluation data only).
  The Track A agent cites values by ID only; a deterministic renderer writes the
  number and a provenance gate rejects any numeral the model typed (ADR-011).
- No silent failure. Return an explicit status or reason; never swallow an
  exception or default a value to keep things green (e.g. no `except: pass`, no
  guessed scale).
- Every extracted value keeps its as-reported string and a `Locator`.
- Never fabricate data: no invented SEC URLs, CIKs, contact emails, or labels.
  Test fixtures must be clearly fixtures. Gold labels need labeler, date, and
  source URL.
- Do not call a feature done until it has run on a real saved SEC filing and a
  human has checked the output.
- Keep the boundaries in `backend/tests/test_architecture_boundaries.py`. Only
  `ingestion/edgar/` touches the network. The one planned exception (model API
  calls from `app/agent/llm.py` and `tools/agent_eval/`, ADR-011) enters the
  boundary test only with the ticket that first needs it.
- Typing is `mypy --strict`; fix types rather than adding `# type: ignore`.
- Tests live in `backend/tests/<package>/`, grouped by the package they cover.
- Record irreversible decisions in [DECISIONS.md](DECISIONS.md).
- The removed PDF/workbook product lives at git tag `v0-extraction`. Consult it
  for reference, but do not restore it wholesale.
