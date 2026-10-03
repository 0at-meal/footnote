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
| AUD-033 | 2 | FIXED (CI workflow written, not executed here; 2 known-red CI steps) | Log: AUD-033 |
| AUD-034 | 2 | FIXED | Log: AUD-034 |
| AUD-027 | 2 | PARTIAL (public-filing Docling golden fixture BLOCKED on SEC_USER_AGENT; Lighthouse/axe not yet) | Log: AUD-027 |
| AUD-002 | 3 | FIXED (golden fixture is synthetic; public-filing fixture BLOCKED on SEC_USER_AGENT) | Log: AUD-002 |
| AUD-020 | 3 | FIXED (page thumbnails not added; not required by the fix) | Log: AUD-020 |

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

### AUD-033 — DoD tooling (commit dbab3ef)
- `backend/mypy.ini` (non-strict) deleted. `mypy backend/app` (root strict): **20 errors → `Success: no issues found in 96 source files`**.
- Two mypy errors were runtime bugs in `drift/router.py` (`ReviewItem.extracted_value`; `list_jobs(company_id=)`). New test `tests/drift/test_qoe_route_company.py`: RED `AttributeError: 'ReviewItem' object has no attribute 'extracted_value'`; GREEN `1 passed`; revert check red/green.
- `ruff check backend eval tools`: **24 → `All checks passed!`**. Behaviour change: a malformed `eval/gates.yaml` now raises (was silently ignored, I3).
- `.github/workflows/ci.yml`: backend (ruff, mypy --strict, pytest), frontend (eslint, tsc, vitest, build + bundle check), e2e (Playwright), eval (`--strict`). YAML parses; **not executed** (no GitHub run from here). Expected red until later: `eval` (batch 6) and 6 backend taxonomy tests that need a versioned seed taxonomy (see discoveries). `requirements.txt`: `pywin32` limited to Windows so Linux CI can install. `make eval` now `--strict`.

### AUD-034 — base URLs (commit ddbc4d1)
- Backend `tests/excel_export/test_public_base_url.py` (real generator): RED `assert not ['http://localhost:8000/api/review/...']`; GREEN; revert check red/green.
- Frontend `src/components/apiBase.test.tsx` (real App): RED `expected [ …(4) ] to include 'https://api.example.test/upload/jobs'`; GREEN; revert check red/green.
- `.env.example` / `frontend/.env.example` document VITE_API_BASE, PUBLIC_BASE_URL, SEC_USER_AGENT, FOOTNOTE_DATA_DIR, ALLOW_PYMUPDF_FALLBACK, JOB_TIMEOUT_SECONDS.

### AUD-027 — test infrastructure (commits 2133717, 1d954ff, 895a383, mutations tool)
- jsdom + Testing Library component tests (used by AUD-001/003/017/007/035/034).
- Playwright: `e2e/review-pdf-race.spec.ts` (AUD-001) and `e2e/review-smoke.spec.ts` (open review → canvas ink pixels > 2000 → every item highlight contains its value text (PyMuPDF search oracle) → Export to Excel → download is a real .xlsx). Full e2e: `3 passed (2.6m)`.
- Seed (`tools/verify/seed_e2e.py`): Docling job bbox probe `hit 0 / miss 12` (AUD-002, fixed in batch 3); PyMuPDF job `hit 12 / miss 0`.
- Replaced tautological flat-index tests with `test_pymupdf_path_bboxes_contain_their_value_text` (real parser + normaliser). Mutation check: the old flat_idx off-by-one **survives** it because PyMuPDF tables expose `rows[].cells`, so the branch changed by the p0 "FN-003 fix" is effectively dead code; a mutation of the live rows path is **killed** (`1 failed`).
- `tools/verify/mutations.py` (M1-M10). Batch 2 run: M1 K, M2 K, M3 K (tests still enforce the Docling inversion bug → AUD-002), M4 K, M5 K (vitest race test), M6 SURVIVED unit-only / **KILLED with `--e2e`** (smoke), M7 K, M8 S, M9 S, M10 S. M8/M9/M10 belong to AUD-005 (batch 5), AUD-038 (batch 7), AUD-021 (batch 8). `tracked changes after run: (none)`.
- BLOCKED: "real-Docling golden fixture built from a few pages of a public filing" needs SEC access (`SEC_USER_AGENT` unset). Batch 3 adds a real-Docling golden test on a SYNTHETIC PDF instead.
- Not yet: Lighthouse / axe (batch 9).

### Batch 2 checkpoint (tag fix-batch-2)
- ruff `All checks passed!`; mypy strict `no issues found in 96 source files`; backend pytest `575 passed` (580 before minus 7 tautological, plus 2 new); eslint clean; tsc clean (incl. e2e); vitest `28 files / 114 tests`; `npm run verify:bundle` OK; Playwright `3 passed`.

### AUD-002 — mirrored Docling highlights (commit d736c02)
- `DoclingItem.coord_origin` (TOPLEFT/BOTTOMLEFT) is set by the parser from each Docling box; the normalizer inverts Y only for BOTTOMLEFT. Removed a debug log line that printed `item.value` (I6).
- Replaced `test_normalize_item_bbox_docling_inversion_parametrized` (asserted the defect) with a BOTTOMLEFT-is-inverted test and a Docling-TOPLEFT-is-not-inverted test.
- New `tests/extraction/test_docling_golden_bbox.py`: real Docling parse of a SYNTHETIC two-table PDF; every item's box must contain its own value text as located independently by PyMuPDF.
  - RED (before the fix, earlier in this run): all 24 boxes mirrored, `assert misses == []` failed.
  - GREEN: `18 passed` (`test_docling_golden_bbox.py` + `test_coordinate_normalizer.py`).
  - Revert check (mutation M3, re-introduces the unconditional inversion): `3 failed, 15 passed` — `FAILED tests/extraction/test_docling_golden_bbox.py::test_docling_rows_keep_document_order` among them. Restored → green.
- New `frontend/e2e/review-highlight.spec.ts` (seeded Docling + PyMuPDF jobs): with the fix both jobs pass and the Docling job's highlights contain their value text 12/12; with the backend fix stashed the Docling test fails (0 hits).
- VERIFY on copies of the user's filings (`run_pipeline.py` in throwaway data dirs, offline classifier stub; `tools/verify/bbox_probe.py --source normalized`, every extracted cell):

  | Filing (copy) | Parser | hit | miss | value text not on page | rate |
  |---|---|---|---|---|---|
  | GOOGL 10-Q | docling | 103 | 0 | 2 | 1.0 |
  | GOOGL 10-Q | pymupdf | 104 | 0 | 0 | 1.0 |
  | Amazon | docling | 475 | 0 | 0 | 1.0 |
  | Amazon | pymupdf | 954 | 0 | 0 | 1.0 |

  Audit baseline for Docling was 3 hit / 100 miss. The first Amazon/Docling probe reported 15 misses; all 15 boxes contain exactly an em dash (U+2014) that Docling stores as `-`, i.e. the probe searched for the wrong glyph. The probe now matches dash variants; boxes were not changed.
  User data checksums after the runs: `3906eb32…pdf: OK`, `a04a4f1e…pdf: OK`, `jobs.json: OK`.
- Gates for touched files: ruff `All checks passed!`, mypy strict `no issues found in 96 source files`, e2e `tsc` and eslint clean.

### AUD-020 — viewer navigation and zoom (commits d4be892 + mutation-run commit)
- Drawn page = page control (`currentPage`), not `selectedItem.page`; selecting an item moves to its page. Zoom re-renders at `PDF_RENDER_SCALE * zoom` (25% steps, so 100%/150% are exact); overlay sized from the canvas CSS size, not a transformed rect. Fit width computed from the stage width. Stage centring moved from `justify-content: center` (inline style **and** `ReviewPage.css`) to auto margins, so a zoomed page's left edge stays in scroll reach. Each item click scrolls its highlight into view.
- Unit `src/components/review/ReviewPage.viewer.test.tsx` (4; fakes only pdf.js and fetch):
  - First RED attempt was invalid: all 4 failed in setup because jsdom reports a 0x0 `getBoundingClientRect`, so the old code drew no overlay. The test now stubs the canvas rect to its CSS size (what a browser reports for an untransformed canvas).
  - RED (ReviewPage.tsx stashed): `expected [ 1 ] to include 2`; `expected '900px' to be '1035px'`; `expected 900 to be greater than or equal to 1198`; `expected [] to include <div role="img" …>` — `4 failed`.
  - GREEN: `4 passed`. (Zoom expectation later updated to the 25% step: 1125px.)
- Playwright `e2e/review-highlight.spec.ts` (Batch 3 VERIFY), seeded Docling + PyMuPDF jobs:
  - GREEN: `5 passed` — highlights contain their value text for both parsers at zoom 100% and 150%, with the canvas bitmap re-rendered to the zoomed width; Next/Prev draw another page while an item is selected (canvas pixel fingerprint changes) and back restores the highlight; at 200% the page's left edge is reachable and the clicked item's highlight is inside the visible stage.
  - RED (ReviewPage.tsx stashed): `Received: 550.8` for the bitmap-width check at 150% (both parsers: CSS scale, no re-render); `expect(await canvasFingerprint(page)).not.toBe(startPixels)` failed (Next changed the label but redrew the same page) — `3 failed, 2 passed` (the two 100% tests pass on old code, as expected).
  - Two real bugs found by the e2e run itself and fixed before commit: the stylesheet still centred the stage (`left edge reachable` failed with the inline fix alone; measured wrap left = -55px at scrollLeft 0), and clicking the already-selected item did not re-scroll to it.
- Regression: race e2e `natural opens: 0/20 failed`, `forced slow-items opens: 0/20 failed`; smoke `ok`. eslint clean, `tsc -b` clean, vitest `29 files / 118 tests`, build OK, `verify:bundle` OK.
- Mutations: M5 anchor updated to the new render call — KILLED (vitest). M6 — KILLED by `review-smoke.spec.ts e2e/review-highlight.spec.ts` (`--e2e`; the highlight spec is now part of the mutation e2e run).

## Out-of-scope discoveries
- **FN-003 `flat_idx` change is dead code.** PyMuPDF `find_tables()` tables expose `rows[].cells`; the `elif table.cells` branch with `flat_idx` (docling_parser.py) is not reached for them. Left in place (harmless); removal is cleanup (AUD-041 batch 10).
- **Seed taxonomy is not version-controlled.** `classification/taxonomy.py` reads the seed from `<data dir>/taxonomy.json`; `backend/data/` is gitignored, so `test_master_taxonomy_loads_from_seed_json` only passes on this machine and would fail in CI. The test conftest copies the local file read-only as a stopgap. Proper fix belongs with AUD-028 (taxonomy injected explicitly) / AUD-033 (CI).
