# Fix progress (resume log)

Branch: `fix/audit-phases-0-3` (from `audit/phases-0-3` @ a0b2a14). Target batches this run: **1-3**.
Rule: a finding is only marked done here when the verifying command was run and its output pasted below.

## Environment
- `SEC_USER_AGENT` is **not set** (checked shell env, user env, `.env`). No live SEC requests are made in this run. Items needing live SEC data use synthetic fixtures under `backend/tests/fixtures/synthetic/` (clearly named) or are marked BLOCKED. **Action for user:** set `SEC_USER_AGENT="Your Name your@email"`.
- LibreOffice: not installed. Node v26.1.0 / npm 11.13.0. Python: `.venv/Scripts/python.exe` (3.11).
- User data in `backend/data/` is never used directly; experiments use copies via `FOOTNOTE_DATA_DIR`.

## Status table
| Finding | Batch | Status | Evidence section |
|---|---|---|---|
| infra: jsdom/Testing Library/Playwright deps, FOOTNOTE_DATA_DIR | - | committed (2133717, AUD-003+007 data-dir commit) | Log: infra |
| AUD-001 | 1 | FIXED | Log: AUD-001 |
| AUD-003 part 1 (D1) | 1 | FIXED | Log: AUD-003 |
| AUD-017 (D7) | 1 | FIXED | Log: AUD-017 |
| AUD-007 (D2) | 1 | FIXED | Log: AUD-007 |
| AUD-035 | 1 | FIXED | Log: AUD-035 |
| infra: test-session data isolation (conftest) | 1 | committed (c287099) | Log: AUD-035 |

## Log

### infra
- Frontend dev deps: jsdom, @testing-library/react, @testing-library/dom, @playwright/test; runtime dep @tanstack/react-virtual (for AUD-019). `npx playwright install chromium` failed here (`Error: Download failure, code=1`), so local Playwright runs use the installed Chrome (`channel: 'chrome'`); CI installs the bundled browser.
- `backend/app/config.py`: `FOOTNOTE_DATA_DIR` (all repositories), `ALLOW_PYMUPDF_FALLBACK`. Test `tests/test_config_data_dir.py` (subprocess with env set; 5 repositories resolve to tmp dir): `1 passed`.

### AUD-001 — pdf.js render race (commit a883fa2)
- Tests (jsdom, real ReviewPage / AuditTrailView, pdf.js replaced by `src/test/fakePdf.ts`, which enforces pdf.js 4.10's one-render-per-canvas rule): `ReviewPage.render-race.test.tsx`, `AuditTrailView.render-race.test.tsx`. Ordering forced: PDF loads first, items/provenance arrive while page 1 renders, selected item on page 2.
- RED before fix: `AssertionError: expected [ 1 ] to include 2` and DOM contained "Page Rendering Error" (ReviewPage); same assertion for AuditTrailView.
- GREEN after fix: `Tests  1 passed (1)` each.
- Revert check (`git stash push -- <fix files>`): red again (`expected [ 1 ] to include 2`), then restored green.
- Fix: `createSerialRenderer()` in `lib/pdf/renderer.ts` cancels and awaits the in-flight RenderTask before the next render; effects no longer set the state they depend on; selecting another item retries after an error.
- Full frontend after fix: eslint clean, `tsc -b` clean, vitest `22 passed / 96 tests`.
- Runtime (commit 1d954ff): Playwright `e2e/review-pdf-race.spec.ts`, real backend (venv, isolated `FOOTNOTE_DATA_DIR` seeded by `tools/verify/seed_e2e.py` with a SYNTHETIC two-page filing through real Docling) + Vite dev, local Chrome.
  - With fix: `natural opens: 0/20 failed`, `forced slow-items opens: 0/20 failed` (items held until pdf.js loaded, CPU x6). `2 passed (2.4m)`.
  - Pre-fix viewer (`ReviewPage.tsx`, `renderer.ts`, `AuditTrailView.tsx` restored from `a883fa2^`): `natural opens: 0/20 failed`, `forced slow-items opens: 10/20 failed` → `1 failed, 1 passed`. Files restored afterwards (`git status` clean for src/).
  - Caveat: the e2e check reads canvas width, which is non-zero even for an undrawn canvas (default 300). Mutation M5 (never draw) is killed by the jsdom race test, not by this e2e; a pixel-level check is added with AUD-027 (batch 2).

### AUD-003 part 1 — D1 (commit 923cd94)
- Backend tests `tests/test_startup_docling.py` (5): refuse start; degraded /health; job stamped with parser + reason; job fails with reason when fallback not allowed; healthy health. Docling absence simulated via `docling_parser.DOCLING_IMPORT_ERROR` (what the module sets on ImportError).
  - RED (fix stashed): `5 failed` (e.g. `test_server_refuses_to_start_without_docling` DID NOT RAISE).
  - GREEN: `5 passed`. Revert check: red again, restored green.
- Frontend `src/components/degradedMode.test.tsx` (2): banner with reason from /health; queue row shows fallback reason and failure reason. RED: `Unable to find role="alert" and name /degraded/i`; GREEN `2 passed`; revert check red/green.
- `tools/run_backend.py`: launched with system Python, `--check` prints `interpreter: C:/footnote/.venv/Scripts/python.exe` / `docling: ok`. Test `tests/test_run_backend_launcher.py` passes. Makefile targets now all use the venv interpreter.
- Existing tests that patched `app.job_runner.parse_pdf` now patch `parse_pdf_with_report` (they mock the parser dependency; behaviour unchanged). Affected suites: `31 passed`.

### AUD-017 — D7 (commit 80017dc)
- Tests `src/components/productionSurface.test.tsx` (6, jsdom, real App/AppShell/UploadZone/DesignPreviewPage) + `src/lib/contrast.test.ts` (7; reference ratios computed independently in Python during the audit).
  - RED (fix stashed): `5 failed | 1 passed` (the 1 = dev route still reachable, expected).
  - GREEN: `6 passed`; revert check red/green.
- Bundle check `node tools/verify/check_bundle.mjs` on a fresh `vite build`:
  - BEFORE: `FAIL: production bundle contains dev-only/mock strings (7)` (Design System, Exit Design, Specification-compliant primitives, Single-User, Auto-detects company, Output Preview, Total Debt $2.5B).
  - AFTER: `OK: 4 bundle files, none contain: Design System | Exit Design | ...`. Also `npm run verify:bundle`.
- Full frontend: eslint clean, tsc clean, vitest `25 files / 111 tests passed`.
- Note: the design page now shows real FAILs for dark-theme white-on-accent (2.8:1) and light warn/ok status text (3.4/4.1:1). Fixing the tokens is AUD-030 (batch 9).

### AUD-007 — D2 (commit c2ac878)
- Backend `tests/test_reconciliation_not_found.py` (4): real pipeline (Docling and PyMuPDF) on SYNTHETIC PDFs from `tests/fixtures/synthetic/pdfs.py`; only the LLM client is stubbed.
  - RED (fix stashed): `3 failed, 1 passed` (bridge detection under both parsers; `AttributeError: not_found`). The bridge-listing test passes on old code too (old code showed everything).
  - GREEN `4 passed`; revert check red/green.
- Frontend `src/components/notFoundJob.test.tsx`: RED `Unable to find a label with the text of: Status: Not found`; GREEN; revert check red/green.
- Regression found and fixed before commit: my first row-label scan read `cell.text` unguarded and broke `test_per_cell_error_is_skipped_not_job_aborting`; now uses `_safe_cell_text`.
- Two existing tests (`test_job_runner_zero_auto_accepted_sets_model_ready_false`, `test_pipeline::test_process_queued_job_transitions_to_done`) fed non-candidate items yet expected `done`; under D2 that is `not_found`. Their fixtures now mark the items as reconciliation-table items (intent preserved, not weakened).
- VERIFY on a copy of the user's GOOGL 10-Q (`tools/verify/run_pipeline.py`, temp data dir, offline classifier stub):
  - Docling: `status = not_found`, `model_skip_reason = Adjusted EBITDA reconciliation not found in this filing`, `parser_used = docling`, `workbook_exists = False`, `review_items = 0`, `target_metric_found = False`.
  - `--force-pymupdf`: same outcome, `parser_used = pymupdf`, `parser_fallback_reason = Docling unavailable (simulated: --force-pymupdf); used PyMuPDF fallback.`
- Affected backend suites: `266 passed`.

### AUD-035 — zombie jobs (commits c287099, AUD-035 commit)
- First, `backend/tests/conftest.py` points `FOOTNOTE_DATA_DIR` at a temp dir before app import, so the new startup hook (and any `TestClient(app)`) can never write to `backend/data`. Full suite with isolation: `577 passed`. User data checksums (`md5sum -c`) before/after: `jobs.json: OK`, `taxonomy.json: OK`, `companies.json: OK`.
- Backend `tests/test_orphaned_jobs.py` (2): startup fails queued/extracting jobs with an "interrupted" reason, leaves done jobs alone; listing fails an `extracting` job older than `JOB_TIMEOUT_SECONDS` with a "timed out" reason, leaves a fresh one alone.
  - RED (fix stashed): `2 failed` (`assert 'extracting' == 'failed'`). GREEN `2 passed` (plus tests/ingestion: `122 passed`). Revert check red/green.
- Frontend `src/components/pollingCap.test.tsx` (fake timers, real App): RED `expected 621 to be 421` (still polling after 31 min); GREEN; revert check red/green. Full vitest `27 files / 113 tests`.

### Batch 1 checkpoint (tag fix-batch-1)
- VERIFY list:
  - Open-review race repro: 0/20 natural, 0/20 forced slow-items (AUD-001). ✔
  - Production bundle contains no "Design System": `check_bundle.mjs` OK (AUD-017). ✔
  - Starting without Docling fails clearly; degraded mode shows banner + job stamp (AUD-003 tests). ✔
  - GOOGL 10-Q (copy) yields `not_found`, no Adjusted EBITDA, no workbook (AUD-007). ✔
- Gates: backend pytest `577 passed` (isolated data dir); frontend eslint clean, `tsc -b` clean, vitest `27 files / 113 tests`, build OK, e2e `2 passed`.
- **DoD not fully met at this checkpoint:** `ruff check backend eval tools` reports 24 errors and `mypy backend/app` (strict) reports 20 errors. All are the pre-existing ones listed in the audit (AUD-033, batch 2); none are in files added or changed by batch 1 except where already present. Re-checked at the batch 2 checkpoint.

## Out-of-scope discoveries
- **Seed taxonomy is not version-controlled.** `classification/taxonomy.py` reads the seed from `<data dir>/taxonomy.json`; `backend/data/` is gitignored, so `test_master_taxonomy_loads_from_seed_json` only passes on this machine and would fail in CI. The test conftest copies the local file read-only as a stopgap. Proper fix belongs with AUD-028 (taxonomy injected explicitly) / AUD-033 (CI).
