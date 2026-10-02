# Audit running notes (phases 0-3)

Branch: audit/phases-0-3 (from main @ ffb3bcf). Date: 2026-10-02. Auditor: Claude (Opus 5.5).

## Step 0 baseline
- Plan: docs/footnote-enhancements.md (491 lines). FOUND.
- Commits: 1dd6560 (p0), df0334f (p1), 873f47a (p2), ffb3bcf (p3). All committed 2026-10-01 within ~8h (15:48 -> 23:46 IST).
- Plan sect 8 status tracker says FN-030..FN-067 = "todo" while headings + sect 9 claim [DONE]. Internal contradiction.
- p2 commit "complete EDGAR-native ingestion" touches ZERO frontend UI except ReviewPage.tsx (2 lines) + types/review.ts. No EDGAR route in main.py diffstat? (check)
- p3 commit removes 1 line from requirements.txt (networkx?).
- .env is untracked (gitignored), differs from .env.example (likely a real GROQ key locally; not committed). OK.
- README still says "local-first", "PDF upload", NetworkX, eval FROZEN, "narrative" components -> stale vs DECISIONS.

- Frontend: eslint exit 0, tsc -b exit 0, vitest 20 files / 94 tests pass, vite build OK (warning: index js 695 kB > 500 kB chunk; pdf.worker 1.37 MB).
- vitest environment = 'node' (vite.config.ts) -> no DOM; component tests use renderToString. No @testing-library, no jsdom, no Playwright in package.json.
- Prod bundle (scratchpad/dist) contains "Design System"x2, "Exit Design"x1, "Local · Single-User"x1, "localhost:8000"x4; "Ready for modeling" x0 (WorkbookPreview tree-shaken => not wired).
- frontend deps: no react-router, no @tanstack/react-virtual, no react-resizable-panels, no radix. Only lucide-react, pdfjs-dist, react.

## Symptom C (design button)
- AppShell.tsx:153-176 renders '/design' button whenever onNavigate passed; App.tsx passes onNavigate on every screen. No import.meta.env.DEV gate anywhere (grep: zero hits for import.meta.env in src).
- App.tsx:37-44 route chosen by pathname/hash, no DEV gate.
- AppShell.tsx:149 hard-coded badge "Local · Single-User" (FN-060 #7 removed footer "MVP · Single-user · Local extraction" but re-added equivalent to header).
- AppShell.tsx:29 default theme 'dark' (plan Appendix A: light-first). Theme toggle = FN-065 scope (phase 4) started early.

## Wiring map (production importers, excluding tests)
- app/ingestion/router_engine.py (FN-024): NO importer.
- app/extraction/shared_cache.py (FN-025): NO importer.
- app/formula_engine/tie_out_checker.py (FN-012): NO importer.
- app/ingestion/edgar/ (FN-020): only router_engine + exhibit_99 (both unwired).
- app/extraction/html/ (FN-021): only router_engine + exhibit_99 (unwired).
- Pre-existing app/ingestion/edgar_client.py (2026-08-29, Step D) + routes /upload/edgar/search, /upload/edgar/filings/{cik}, POST /upload/edgar (downloads PDF!). Frontend never calls them (types EdgarCompanyResult/EdgarFiling exist in types/job.ts, unused).
- Frontend: WorkbookPreview (FN-067) imported only by its test. DriftFlagCard, ModelViewer imported nowhere (orphans).
- ReviewPage iframe src `${apiBase}/filings/${jobId}/html` -> no backend route /filings/* exists (main.py routers).

## Backend baseline
- pytest (backend/): 566 passed, 0 skipped, 0 xfail, 14 DeprecationWarnings (docling generate_table_images), 248s.
- No .github / CI config exists at all. import-linter not installed. Architecture boundary test = backend/tests/test_architecture_boundaries.py (AST import check; formula_engine forbidden list omits pathlib/json/open/os/logging).
- backend/mypy.ini added in p2 is NON-strict (warn_return_any=False, ignore_missing_imports=True, no strict) -> `cd backend; mypy app` (as ARCHITECTURE.md instructs) runs non-strict. Root mypy.ini strict.

## Symptom D (over-flagging) - VERIFIED from stored data
- Same GOOGL 10-Q (125,546 bytes) processed: job 9d00e013 (review.json 2026-09-17): 98 locked / 6 pending; job 3906eb32 (2026-10-02, post-phases): 34 locked, 64 needs_review, 6 pending (70/104 = 67% flagged).
- Confidence bands IDENTICAL in both runs: 77 needs_review, 27 auto_accepted. Status derivation code unchanged 202f154->HEAD (review/repository.py _from_classified_records). Old run's extra locks came from user batch-confirm (old "Generate Model (N)" button called confirm-batch then generate - ReviewPage.test.tsx:208). FN-030/062 removed that path => now the scorer's needs_review band is visible as-is.
- Scorer math (extraction/confidence.py:96-125): start 1.0; flat label (no " / ") -0.15 'missing_header_hierarchy'; reconciliation-candidate +0.15; numeric +0.05. All 104 records is_reconciliation_candidate=False (GOOGL 10-Q has no Adj. EBITDA bridge) -> flat labels score 0.90 < 0.95 threshold -> needs_review. 75 items exactly (0.9, [missing_header_hierarchy, value_is_numeric]).
- summary.json: parser_used='pymupdf' (Docling fell back), filtered_non_reconciliation_count=104 yet all 104 shown (review/repository.py:511-517 only filters if ANY candidate exists), target_metric_found=True although no candidate (job_runner.py:133 `pack_candidate_found or bool(docling_items)`) -> I3 masking.
- msft-10q.pdf job edcedfa2 stuck in 'extracting' (zombie) — no recovery on restart.
- Duplicate queue rows: 3x 'GOOGL (10-Q) 2025-04.pdf' + 'goog trial file.pdf' same size; client dedupe = filename+size (App.tsx:130-141) not content hash (FN-060 #6).
- review/models.py (p2) silently defaults page=1, bbox full page, source_file='' -> fabricates provenance (I3/I4).

## Lint/type baseline (VERIFIED, scratchpad/backend_lint.txt)
- `ruff check backend`: 9 errors (exit 1): taxonomy.py:11 I001, qoe_diff.py:16 I001, drift/router.py:242 I001 + :307 FURB192, formula_engine/reader.py:77 SIM102, tests/drift/test_qoe_diff.py unused imports (TestClient, app.main.app, Path).
- `ruff check eval`: 15 errors incl. eval/metrics.py:781 try/except/pass (S110, BLE001), record_replay.py:47 BLE001.
- `ruff format --check backend`: 62 files would be reformatted.
- `mypy backend/app` (root strict): 20 errors in 7 files (exit 1). Real bugs: drift/router.py:279 ReviewItem.extracted_value (no such attr), drift/router.py:303 list_jobs(company_id=) unexpected kwarg -> TypeError whenever job.company_id set; provenance.py:175/177 Optional deref; edgar/client.py:332; html/ixbrl_parser.py & table_parser.py bs4 AttributeValueList typing; multi_year_generator.py:97.
- `cd backend && mypy app` (backend/mypy.ini non-strict): still 19 errors.
- => DoD "ruff, mypy (strict) pass" false for p1-p3.

## Runtime (isolated copy: scratchpad/run/backend, data copied; uvicorn 127.0.0.1:8000; vite dev 5173)
- /review/{job}/pdf 200 application/pdf, CORS ok (allow-origin localhost:5173), OPTIONS preflight ok.
- /filings/{job}/html -> 404 (VERIFIED).
- Headless Chrome (scratchpad/cdp.py) at 1280: PDF for job 3906eb32 DID render (canvas 892x1263, Page 1 of 3, highlight drawn). Symptom A not reproduced on first-load path -> need other triggers (StrictMode? page nav? zoom? HTML-named source? different job).
- Console: 404 GET /footnote/{job}/lease (x2, StrictMode double fetch) on every review open for non-capital-structure jobs.
- QoE GET /drift/jobs/{job}/qoe (VERIFIED): "(4,800)" -> value 0.0 (drift/router.py:276-281 float() on raw string, except ValueError -> 0.0); 102/104 rows category 'Other' incl. Total assets; total_addbacks 5,948,647.45; company 'Company', period 'Current'. Not called by frontend.
- POST /upload/jobs accepted byte-identical duplicate (5th copy) -> no server-side content-hash dedupe.
- Zombie job msft-10q.pdf 'extracting' -> frontend polls /upload/jobs + /companies every 3s forever (App.tsx:106-125).

## Symptom A (PDF not loading) - REPRODUCED
- Forced ordering (items request paused via CDP Fetch until PDF doc loaded, CPU x6): viewer shows "Page Rendering Error: Cannot use the same canvas during multiple render() operations..." canvas-wrap display:none, stuck. screens/review_race_1280.png
- Natural (no interception) 5 opens each: dev amazon 2/5 FAIL, dev goog dpr1.25 1/5 FAIL, prod(5174) amazon 1/5 FAIL, prod goog 0/5. => intermittent, 4/20.
- Root cause: ReviewPage.tsx:315-344 draw effect deps [pdfDoc, selectedItem, currentPage]; renderPage() (lib/pdf/renderer.ts:42-75) never cancels previous RenderTask; cleanup only sets `cancelled` flag. When PDF loads before /items (PDF endpoint 2-6x faster: 6ms vs 10-80ms), effect renders page 1, then items arrive -> setSelectedItem+setCurrentPage -> second page.render on same canvas while first in flight -> pdf.js 4.10 #canvasInUse guard throws (pdf.mjs:13118). Error sets pageRenderError -> wrap display none (ReviewPage.tsx:1583); never retried. Also setCurrentPage(targetPage) inside the effect re-triggers it.
- Pre-existing pattern (same effect at 202f154) => latent bug, not introduced by phases; but phases claimed FN-003/FN-062 PDF pane done and added no viewer test.
- Next/Prev page buttons no-op while an item is selected (always): after "Next page" still "Page 1 of 3" (targetPage = selectedItem.page). VERIFIED.
- Zoom = CSS transform scale on wrapper (ReviewPage.tsx:1588): no re-render (blurry), left part of page goes under sidebar / unreachable (canvas rect x=283 at 130%, sidebar ends 440). screens/review_zoom130_1280.png. canvasSize from getBoundingClientRect (ReviewPage.tsx:329) inside a scaled wrapper -> overlay mis-sized if re-render happens while zoom != 1 (HYPOTHESIS, FN-003 regression risk).
- Review layout: .review-layout height 800 (=100vh) inside AppShell w/ 48px sticky bar -> document 848px tall; if window scrolled (scroll retained from home), sticky app bar covers the review header incl. Export to Excel (screens/review_1280.png shows header hidden).
- Default selection = items[0] (locked item) while default tab = Flagged -> highlighted item not in list.
- React warning "Encountered two children with the same key" on amazon job (dev) — review IDs unique (954/954), so from another list (DataTable rowKey / cards). TODO identify.

## Symptom D ROOT CAUSE (VERIFIED by experiment)
- All 5 user jobs (Sep 9 -> Oct 2) summary.parser_used = 'pymupdf' with identical 27 auto / 77 needs_review for GOOGL.
- `uvicorn` on PATH = C:\Users\NIRAJ\AppData\Roaming\Python\Python311\Scripts\uvicorn.exe (system user-site). System python has fastapi/uvicorn/pymupdf but NOT docling.
- scratchpad/parse_probe.py on same GOOGL PDF: system python -> "Docling library is not installed" -> pymupdf, 104 items, bands needs_review 77 / auto 27 (EXACT match to user's runs). venv python -> docling, 105 items, auto 104 / needs_review 1.
- PyMuPDF labels lack the column header ("Cash and cash equivalents") vs docling ("Cash and cash equivalents / As of December 31, 2024") -> scorer -0.15 missing_header_hierarchy -> 0.90 < 0.95.
- ALSO: PyMuPDF path loses the period column -> two values for same label w/o period (23,466 Dec-24 vs 23,264 Mar-25) => period ambiguity (P0 risk for model numbers).
- Fresh venv run (job 8716f887): 98 locked / 6 pending / 1 needs_review (7/105 flagged).
- I3: docling_parser.py:328-339 catches ANY Exception, logs WARNING (no app log config) and falls back; user sees only "ENGINE: PYMUPDF" badge; no reason, no requirement check at startup; health endpoint doesn't report docling.

## FN-003 bbox (VERIFIED by probe scratchpad/bbox_probe.py: value text center inside item bbox)
- Docling job 8716f887 (venv run): hit 3 / miss 100 / not-found 2. Mirrored vertically: item y 706-716 vs text y 284-294 (=1000-y).
- PyMuPDF jobs 3906eb32 104/104 hit, 9d00e013 104/104, a04a4f1e 954/954.
- Raw docling cell bbox (docling.json) y0=239.36,y1=247.79 on 842pt page => already TOP-LEFT; coordinate_normalizer.py:74-90 inverts unconditionally (assumes bottom-left, ignores bbox.coord_origin) => mirrored. Screen: highlight top 891px/1263 for 23,466 (should be ~359px). screens/review_docling_mirrored_highlight_1280.png (highlight off-screen).
- p0 'bbox fix' only changed PyMuPDF flat_idx (docling_parser.py:646) and rewrote test_coordinate_normalizer.py:227-270 to recompute the formula inline (tautological, never calls production code).
- Docling is the INTENDED parser; the user's env hides this because system-python falls back to PyMuPDF. Fixing env (symptom D) will expose mirrored highlights.

## Workbook (spot-checked agent claims, VERIFIED)
- 3906eb32_model.xlsx: Reconciliation!B1 'VERIFIED', A2 'Amounts in thousands' (filing is in millions), Review 'Verified: All items confirmed'; 'Adjusted EBITDA' row 143 = sum of balance-sheet/OCI items; Checks rows 5/6 literal 0/1/'PASS'; Source_Inputs!A2 hyperlink http://localhost:8000/api/review/{job}/source -> 404.
- Source_Inputs: 'Total cash, cash equivalents, and marketable securities' 95,657 normalized as 'Accrued Expenses and Other Current Liabilities' (taxonomy misclassification); duplicate period columns unlabeled under PyMuPDF.
- reader.py:72-80 treats taxonomy match (is_confirmed) as review-confirmed.
- Agent reports: scratchpad/agent_phase1.md, agent_phase3.md (detailed, file:line). Spot-checks of generator.py:434-436, :650-690, build_benchmark_corpus.py:973-977, MSFT labels under CIK 0001018724 all confirmed.
- AuditTrailView same un-cancelled render pattern (AuditTrailView.tsx:296-310); screens/audit_trail_1280.png shows "Cannot use the same canvas" error.

## Mutation testing (scratchpad/mutate.py, mutate2.py; each reverted via git checkout; git status after = only ?? docs/audit/)
- M1 confidence threshold 0.95->0.85: KILLED (4 failed tests/extraction/test_confidence.py)
- M2 needs_review band -> locked in review/repository.py: KILLED (5 failed tests/review/test_actions.py)
- M3 remove Docling Y-inversion (the CORRECT fix): KILLED (3 failed test_coordinate_normalizer docling_y_inversion) => tests enshrine the bug
- M4 header always VERIFIED: KILLED (1 failed test_generate_first_zero_reviewed_workflow)
- M5 ReviewPage never calls renderPage: SURVIVED (vitest 94/94)
- M6 highlight y-mirrored in ReviewPage: SURVIVED (vitest 94/94)
- M7 job_runner read_formula_inputs([]): KILLED (3 failed)
- M8 Checks footing status '=IF(TRUE,...)': SURVIVED (70 passed excel_export+formula_engine)
- M9 EDGAR token bucket capacity 10->1000: SURVIVED (120 passed tests/ingestion)
- M10 QoE value parser always 0.0: SURVIVED (45 passed tests/drift)

## Misc VERIFIED
- I1: decision_log.jsonl a04a4f1e: 178/677 Groq payloads contain figures e.g. 'CASH, CASH EQUIVALENTS, AND RESTRICTED CASH, END OF PERIOD / 69,893'.
- I2: classification/taxonomy.py:33-46 SEED_MASTER_TAXONOMY loaded from data/taxonomy.json at import (mutable via bulk_confirm_taxonomy); formula_engine/tree.py:15,560 uses it. Pre-existing (same at 202f154).
- Debt card: footnote/extractor.py:224 total_debt = sum(principals) -> DebtScheduleCard.tsx:151-163 tie-out tautological. GOOGL total $21,769M = 10,883 (Dec-24) + 10,886 (Mar-25). Amazon (non_gaap job) total_debt 3,172,102 from 75 tranches; dup tranche id debt-36df33cef318 -> React duplicate-key warning.
- Favicon = Vite default (frontend/public/favicon.svg, last changed 8ee5b49 scaffold).
- FN-001 remnants: formula_engine/models.py:293 ComprehensiveModelTree, tree.py:17 import, excel_export/repository.py:43 '_multi_statement.xlsx', multi_year_generator.py:2 'DEPRECATED: Use multi_statement_generator.py'.
- No secrets in git history (0 gsk_ matches); .env untracked.

## Wrap-up
- Report: docs/audit/AUDIT_PHASES_0-3.md; findings: docs/audit/findings.json (44 findings: P0 13, P1 15, P2 10, P3 6), generated from scratchpad/findings_src.py.
- Sub-agent reports kept in scratchpad (agent_phase1.md, agent_phase2.md, agent_phase3.md); key claims spot-checked (see above).
- Servers stopped (uvicorn 8000, vite 5173, preview 5174). Isolated run data lives only in the scratchpad.
