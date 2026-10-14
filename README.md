# Footnote

Deterministic building blocks for extracting company-reported non-GAAP
reconciliations (Adjusted EBITDA and similar) from SEC EDGAR filings, with
provenance on every number.

> **Status (2026-10-14): clean base, direction under review.**
> The repository was reset to the reusable core of the earlier product. The
> next product direction will be decided from a separate review. The earlier
> PDF → Excel workbook product (FastAPI app, React UI, Groq classifier, formula
> engine, audit reports) was removed from `main`. It is preserved at git tag
> [`v0-extraction`](https://github.com/0at-meal/footnote/tree/v0-extraction).
>
> **No accuracy claims.** Everything here is covered by unit tests on fixtures
> and mocked HTTP only. Nothing has yet been validated against real saved SEC
> filings checked by a human. The old evaluation corpus was found to be
> fabricated and was deleted. Do not cite numbers from the `v0-extraction` tag.

---

## What is here

| Package | What it does |
|---|---|
| `backend/app/ingestion/edgar/` | SEC EDGAR client: ticker → CIK, submissions API, filing index / exhibit discovery, document download. Token-bucket rate limit (≤10 req/s), retries, circuit breaker, immutable on-disk cache. Rejects foreign filers explicitly. |
| `backend/app/ingestion/exhibit_99/` | Detects 8-K Item 2.02 earnings releases and their EX-99.1 exhibit; extracts reconciliation records from HTML exhibits; tags guidance rows. |
| `backend/app/extraction/html/` | HTML table parser (colspan/rowspan grid, numeric cells, XPath per cell), reconciliation-table detector, iXBRL fact parser, and the `HtmlExtractor` that ties them together. |
| `backend/app/extraction/locator.py`, `models.py` | `ExtractedRecord` and its provenance `Locator` (`HtmlLocator` for EDGAR documents, `PdfLocator` for page + bbox). |
| `backend/app/extraction/scale_and_sign.py` | Pure scale ("in millions") and sign ("(1,234)", "Less:") normalization. Unknown scale is flagged, never guessed. |
| `backend/app/classification/` | Master financial taxonomy (tracked seed JSON) with deterministic alias matching, fuzzy *suggestions* that never auto-match, and add-back categories. No LLM. |

See [ARCHITECTURE.md](ARCHITECTURE.md) for boundaries, principles, and known gaps.

## Setup

Requires Python 3.11.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

The EDGAR client needs a declared User-Agent (SEC fair-access policy). Set it in
your shell. The code does not load `.env` files automatically:

```bash
export SEC_USER_AGENT="Your Name you@example.com"
```

See [.env.example](.env.example) for all variables. CI runs the same checks on
every push (`.github/workflows/ci.yml`).

## Commands

Run from the repo root with the venv active. `make` targets are shortcuts for
the same commands.

| Task | Command | `make` |
|---|---|---|
| Tests | `cd backend && pytest` | `make test` |
| Lint + format check | `ruff check backend && ruff format --check backend` | `make lint` |
| Type check (mypy strict) | `mypy` | `make typecheck` |
| Auto-fix + format | `ruff check backend --fix && ruff format backend` | `make format` |
| Everything | all of the above | `make check` |

## Documentation

| Doc | Purpose |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Modules, dependency rules, engineering principles, known gaps |
| [DECISIONS.md](DECISIONS.md) | Decision log |
| [docs/glossary.md](docs/glossary.md) | Domain terms (SEC filings, reconciliations, provenance) |
| [CLAUDE.md](CLAUDE.md) | Working rules for coding agents |
