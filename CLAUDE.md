# Working on Footnote

Read [ARCHITECTURE.md](ARCHITECTURE.md) first. This repo is a clean base. The
product direction is under review, so do not build an API, UI, database, or
orchestration layer unless the user asks for it.

## Commands

- `make check`: lint, format check, mypy strict, tests. Must pass before you
  commit. Without `make` (e.g. Windows), run `ruff check backend`,
  `ruff format --check backend`, `mypy`, and `cd backend && pytest`.
- `cd backend && pytest path/to/test.py`: run a single test file.
- Imports are rooted at `backend/` (`from app.extraction.models import ...`).

## Rules

- Numbers come only from deterministic code. Never let an LLM produce or alter a numeric value.
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
  `ingestion/edgar/` touches the network.
- Typing is `mypy --strict`; fix types rather than adding `# type: ignore`.
- Tests live in `backend/tests/<package>/`, grouped by the package they cover.
- Record irreversible decisions in [DECISIONS.md](DECISIONS.md).
- The removed PDF/workbook product lives at git tag `v0-extraction`. Consult it
  for reference, but do not restore it wholesale.
