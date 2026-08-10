# Footnote — Constitution

This file is the fixed rulebook for any coding agent working on this project.
It does not change for the lifetime of the project. If a request conflicts
with a rule here, the rule wins — stop and ask, do not improvise around it.

---

## 1. Coding Standards

1. Every module in `extraction/`, `formula_engine/`, `excel_export/`, and
   `audit_report/` must be fully typed. Run `mypy --strict` on these before
   any commit touching them.
2. `classification/` (the LLM boundary) may be typed more loosely, but its
   public interface must never expose a numeric return field.
3. No `dict`/`Any` payloads crossing a pipeline-stage boundary. Use a
   Pydantic model. If no model exists for the data, create one first.
4. `formula_engine/` functions must be pure: no I/O, no clock, no random,
   no global state. If a function needs any of these, it does not belong
   in this package — move it.
5. Never write a numeric literal directly into a generated `.xlsx` cell
   unless it is explicitly tagged as a manual hardcode per NFR2.
6. Every PR touching `formula_engine/` or `excel_export/` must include or
   update a test. No exceptions for "small" changes.
7. Run `ruff` + `black` (Python) and `eslint` + `prettier` (TS/React)
   before every commit. Do not disable a rule to make code pass; fix the
   code.
8. Do not add a new third-party dependency without checking it against
   Section 6, Rule 5 (data egress) first.
9. Do not catch and swallow an exception in `extraction/` or
   `formula_engine/` to keep a pipeline run "green." Surface it as a
   flagged item instead — silent failure is worse than a visible one.
10. Do not use `# type: ignore` or `@ts-ignore` to silence a real type
    error. Fix the underlying type, or escalate if the library's own
    types are wrong.

## 2. Naming Conventions

1. Python: `snake_case` functions/variables, `PascalCase` classes and
   Pydantic models.
2. Modules are named after pipeline stage, never `utils.py`, `helpers.py`,
   or `misc.py`. If code doesn't fit an existing stage, that's a signal to
   create a new named module, not a junk drawer.
3. JSON schema field names (`value`, `label`, `page`, `bbox`,
   `source_file`) are frozen. Never rename, even for a "cleaner" name —
   drift-tracking graph state on disk depends on them (NFR7).
4. React components: `PascalCase.tsx`, one component per file.
5. Excel-facing artifacts (named ranges, cell comments) follow IB
   convention: blue = hardcode, black = formula, green = sheet-link. This
   is enforced in code, not left to the generator's default styling.
6. Git commits: Conventional Commits (`feat:`, `fix:`, `chore:`, etc.).
   Branches: `feat/`, `fix/`, `chore/` prefix required.
7. Test files mirror the source module name exactly
   (`formula_engine/tree.py` → `tests/formula_engine/test_tree.py`).
   Never bundle unrelated tests into one file for convenience.

## 3. Folder Structure

1. Do not create new top-level folders under `backend/app/` without
   updating this file first. The folder boundary is the LLM-isolation
   boundary — treat it as load-bearing, not organizational preference.
2. `extraction/` must never import from `classification/`. Enforce via
   import-linter or equivalent in CI if it doesn't already exist.
3. `classification/` must never import from `formula_engine/` or
   `excel_export/`.
4. Tests live under `backend/tests/`, mirroring the `app/` structure
   exactly — one test module maps to one source module.
5. `eval/` (benchmark harness) never imports application code by copy;
   it imports the real pipeline modules, so eval always tests what ships.
6. `docs/` (MkDocs) is generated/maintained separately from code comments
   — do not let architecture docs drift by editing only one of the two.
7. Frontend `lib/pdf/` may only talk to `components/review/`. It must
   not reach into backend modules directly; all data crosses via the
   FastAPI API layer.

## 4. Tech Stack

1. Do not swap a stack component (Docling, PyMuPDF, xlsxwriter, NetworkX,
   FastAPI, React, PDF.js, Groq) without an explicit, separate decision —
   never as a side effect of fixing an unrelated bug.
2. xlsxwriter generates fresh workbooks only. Do not attempt to patch an
   existing `.xlsx` with it. If "edit an existing model" is requested,
   flag that this requires an openpyxl migration — do not hack around it.
3. Local/offline inference (Ollama) is a documented future path, not
   built now. Do not silently start building it inside an unrelated task.
4. Heavy extraction runs locally/notebook-side, never on the hosted
   free-tier backend. Do not move extraction into the FastAPI hosted
   service to "simplify deployment."
5. Do not add a database beyond SQLite for graph persistence without an
   explicit decision — MVP is intentionally single-user, single-session.
6. Do not introduce a paid infrastructure dependency (hosted DB, paid
   LLM tier, paid compute) to solve a performance problem. Solve within
   NFR3/NFR4 constraints or flag the constraint as no longer workable.
7. The LLM classifier is Groq's API (`openai/gpt-oss-120b`), not Claude.
   Groq serves open-source models only — do not write prompts or fallback
   logic that assumes access to a proprietary model.
8. Groq's free tier is rate-limited per model (RPM, TPM, and RPD caps,
   whichever is hit first — see `plan.md` §5 for current figures). Batch
   sizes and retry/backoff logic in `classification/` must be designed
   against these published limits, not an assumed-unlimited budget.

## 5. External Documentation

Consult before deviating from documented library behavior — do not guess:

- FastAPI: https://fastapi.tiangolo.com/
- Docling: https://docling-project.github.io/docling/
- PyMuPDF: https://pymupdf.readthedocs.io/
- xlsxwriter: https://xlsxwriter.readthedocs.io/
- openpyxl (future): https://openpyxl.readthedocs.io/
- NetworkX: https://networkx.org/documentation/stable/
- React: https://react.dev/
- PDF.js: https://mozilla.github.io/pdf.js/
- ReportLab: https://www.reportlab.com/docs/reportlab-userguide.pdf
- WeasyPrint: https://doc.courtbouillon.org/weasyprint/
- Pytest: https://docs.pytest.org/
- MkDocs: https://www.mkdocs.org/
- Pydantic: https://docs.pydantic.dev/
- NumPy (if used in eval diffing): https://numpy.org/doc/stable/
- GitHub Actions: https://docs.github.com/en/actions
- Groq API (OpenAI-compatible): https://console.groq.com/docs/overview
- Groq rate limits: https://console.groq.com/docs/rate-limits

Do not cite a library's behavior from memory when writing extraction or
formula-generation logic. Look it up here first, every time.

## 6. Never Do Automatically

1. Never let classifier output populate a numeric cell, formula argument,
   or table value — not even as a low-confidence fallback.
2. Never widen the classifier interface to accept or return numbers,
   ranges, or any computed field, for any reason.
3. Never auto-merge conflicting taxonomy labels. Queue for human
   confirmation, always — this is what the review step exists for.
4. Never overwrite a generated `.xlsx` model without preserving and
   reattaching its existing provenance metadata, even for a quick fix.
5. Never send raw filing content, filenames, or extracted text to any
   remote service beyond the documented Groq classifier call. No
   incidental analytics, telemetry, or error-reporting SDKs that transmit
   document content.
6. Never programmatically mark a flagged/unverified cell as verified.
   That state change is human-only, permanently.
7. Never introduce non-determinism into `formula_engine/` — no random
   seeds, no wall-clock branching, no unordered iteration affecting
   output — without a documented, explicit exception approved outside
   this file.
8. Never weaken or skip a CI gate (formula correctness, provenance
   resolvability, type checks) to make a demo work faster.
9. Never rename or restructure a persisted schema field or SQLite/graph
   key without a migration path — cross-year history must survive
   (NFR7).
10. Never add authentication, billing, or multi-tenant data isolation
    unless explicitly requested — these are out of scope by design, not
    by oversight.
11. Never delete or bypass a manual-review flag to make an extraction
    pass the eval harness's accuracy threshold.
12. Never treat this file as editable during normal development work.
    Changing it requires an explicit, separate request to do so.
13. Never present eval-harness accuracy numbers without also stating the
    benchmark size and how many items were manually corrected.
14. Never assume a low-confidence extraction flag can be resolved by
    re-running with different parsing settings — surface it for human
    review rather than retrying silently until it looks clean.
