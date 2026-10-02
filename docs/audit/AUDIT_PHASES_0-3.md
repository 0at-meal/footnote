# Footnote: Audit of Phases 0-3 (FN-000 … FN-067)

Branch `audit/phases-0-3` from `main` @ `ffb3bcf` · audited 2026-10-02 · scope: commits `1dd6560` (p0), `df0334f` (p1), `873f47a` (p2), `ffb3bcf` (p3) · plan: `docs/footnote-enhancements.md` (found). No source, test, config or doc outside `docs/audit/` was changed (see section 2 for `git status`). Running notes: `docs/audit/_notes.md`. Machine-readable findings: `docs/audit/findings.json`. Screenshots: `docs/audit/screens/`.

Labels: **VERIFIED** = observed by the audit (by me, or by one of three read-only sub-agents whose probes are named; the most serious sub-agent claims were re-checked by me and say so). **HYPOTHESIS** = inferred. **UNVERIFIED-RUNTIME** = could not be run here.

---

## 1. Executive summary

- **Health: Phases 0-3 are not done.** The tests pass (backend 566, frontend 94), but they don't exercise the paths that fail. Of 26 tickets, 1 is DONE, 15 PARTIAL, 9 STUBBED and 1 MISSING. All of Phase 2 (EDGAR) is libraries with no route or UI.
- **44 findings: 13 P0, 15 P1, 10 P2, 6 P3.** Several P0s break an invariant (I1, I3, I4, I6) or produce untrustworthy numbers.
- **Most damaging:**
  1. **AUD-003 (symptom D).** The server runs without Docling and silently falls back to PyMuPDF. Its flat labels score 0.90 against a 0.95 threshold, so 67% of items are flagged and period columns become indistinguishable. Under `.venv` the same PDF flags 7/105.
  2. **AUD-001 (symptom A).** A pdf.js render race on a shared canvas intermittently blanks the review and audit-trail PDF (4 of 20 natural opens).
  3. **AUD-002.** Every Docling highlight is vertically mirrored (100 of 105 boxes miss). The FN-003 fix touched only the fallback parser, and the tests assert the bug.
  4. **AUD-004, AUD-005, AUD-007 (workbook).** A GOOGL 10-Q with no EBITDA bridge yields an "Adjusted EBITDA" that is the sum of balance-sheet lines. It is stamped VERIFIED, with a Checks sheet that can only say PASS and units stated as thousands when the filing is in millions (AUD-006).
  5. **AUD-010, AUD-014 (eval).** The 40-filing "benchmark" is hand-typed with wrong accession numbers and CIKs, and the gate passes an extractor that gets 0% of values right.
- **Symptom E (AUD-015).** FN-020 to FN-025 exist only as unwired modules and tests. **Symptom C (AUD-017).** `/design` ships to production with a header button, and mock copy is hard-coded into production screens. **Symptom B:** per-screen list in section 4.
- **Could not verify:**
  - LibreOffice recalculation (not installed).
  - Lighthouse and axe scores (no Playwright or Lighthouse).
  - The interpreter the user's own server ran under (inferred from identical 27/77 counts).
  - Excel's rendering of formulas.

---

## 2. Environment and what was actually run

| Item | Command / method | Result |
|---|---|---|
| History | `git log`, `git show --stat` for 4 commits | p0 84 files (+2251/−4858), p1 88 (+10352/−1173), p2 39 (+4423/−61), p3 33 (+4945/−897). All on `main` within 8 h (2026-10-01 15:48-23:46 IST). p2 "complete EDGAR-native ingestion" touched no frontend except 2 lines of ReviewPage and `types/review.ts`. |
| Backend tests | `cd backend && ../.venv/Scripts/python.exe -m pytest -q -rsxX -p no:cacheprovider` | **566 passed**, 0 skipped, 0 xfail, 14 DeprecationWarnings (docling `generate_table_images`), 248 s |
| Ruff | `ruff check backend` / `ruff check eval` / `ruff format --check backend` | **9 errors** (exit 1) / **15 errors** / 62 files would be reformatted |
| mypy | `mypy backend/app` (root `mypy.ini`, strict) | **20 errors in 7 files** (exit 1). `cd backend && mypy app` uses the p2-added non-strict `backend/mypy.ini`: 19 errors |
| Frontend | `npx eslint .`, `npx tsc -b`, `npx vitest run`, `npx vite build` (outDir in scratchpad) | eslint exit 0; tsc exit 0; **20 files / 94 tests pass**; build OK with warning (main chunk 695 kB; pdf worker 1.37 MB) |
| Tooling availability | `which make`, `soffice`, Playwright | `make` **absent** (ran Makefile commands directly); LibreOffice **absent**; Playwright/Lighthouse/axe **absent**, so I used headless Chrome over the DevTools protocol (`scratchpad/cdp.py`) |
| App run | Isolated copy of `backend/` + `backend/data` in the scratchpad; `.venv` uvicorn on 127.0.0.1:8000; `vite` dev on 5173; `vite preview` of the production build on 5174 | Health `{"status":"ok"}`. User data in `backend/data` was **not** touched. |
| Sample filing | The user's GOOGL 10-Q (`backend/data/uploads/e63f6530….pdf`, 125,546 B) re-submitted to the isolated backend | Job `8716f887`: parser **docling**, 105 items, 98 locked / 6 pending / 1 needs_review. Also analysed the 5 existing user jobs read-only. |
| Screens | Home, `/design`, review, audit trail, command palette, queue overflow at 1280 and 1920, dark (default) and light | `docs/audit/screens/*.png` (24 files), console and failed requests captured (`scratchpad/out_*.json`) |
| Network | sec.gov reachable | Phase 2 sub-agent: 9 SEC requests. Phase 1 sub-agent: accession checks for 40 labels (count not logged). My fresh pipeline run sent unmatched labels to Groq using the local `.env` key (normal app behaviour). |
| Mutations | `scratchpad/mutate.py`, `mutate2.py` | 10 mutations, each reverted with `git checkout -- <file>`. Final `git status --porcelain` before commit: `?? docs/audit/` only |

**Assumptions** (no questions asked mid-run):
- The user's sample is `GOOGL (10-Q) 2025-04.pdf`. `goog trial file.pdf` (job `3906eb32`, 2026-10-02) is byte-identical and is the post-phase run that shows symptom D.
- "mypy strict" means the root `mypy.ini`.
- Running the app against a copy is acceptable, and preferable to writing jobs into the user's data.

**Blocked, marked UNVERIFIED-RUNTIME where relevant:**
- LibreOffice recalculation ACs (FN-012, FN-031, FN-033).
- Lighthouse ≥ 95 and axe (FN-062, FN-065).
- The FN-062 keyboard-only "clear 20 items" AC: J moved the selection, and Y/E were not exercised end-to-end.
- The user's real server process.

---

## 3. Ticket scorecard

| Ticket | Status | One-line evidence | Findings |
|---|---|---|---|
| FN-000 Audit | PARTIAL | `docs/AUDIT.md` exists and resolves the VERIFY items (it correctly flags "Docling Y-axis inversion still open"). Test counts are approximate and were not run. Shares a commit with source changes. | AUD-040, AUD-043 |
| FN-001 Delete dead features | **DONE** | Tag `archive/pre-cleanup` exists. narrative, `ENABLE_NARRATIVE`, the 6-tab generator, its route and buttons are gone, with no dangling imports. Minor leftovers remain. | AUD-041, AUD-044 |
| FN-002 Collapse docs | PARTIAL | Docs archived; ARCHITECTURE and DECISIONS written; README links resolve. No CI or import-linter (weak AST test only). README and CONSTITUTION stale. | AUD-033, AUD-040, AUD-028 |
| FN-003 PDF P0 bugs | PARTIAL | Only the PyMuPDF `flat_idx` changed. Docling inversion not fixed (100/105 mirrored). clientWidth/zoom issue reintroduced by p3. Golden test is synthetic. | AUD-002, AUD-001, AUD-020, AUD-027 |
| FN-060 Visible UI defects | PARTIAL | #1, #3, #4, #8 OK. #2 debt table REGRESSED. #5 fiscal label and #6 dedupe not fixed. #7 replaced by a header badge. | AUD-029, AUD-017 |
| FN-010 Benchmark corpus | STUBBED | Labels hand-typed in a script; accessions/CIKs wrong; second annotator copied; no XBRL seeding. | AUD-010, AUD-042 |
| FN-011 Eval runner + gate | STUBBED | `make eval` ignores the corpus and `--split`; gate passes 0% exact match; no cassette; no CI; exits 0 on failure. | AUD-014 |
| FN-012 Tie-outs + Checks sheet | STUBBED | Engine unwired; Checks sheet tautological plus constant "PASS"; demotion impossible; no recalc test. | AUD-005 |
| FN-013 Scale and sign | PARTIAL | Pure helpers tested, never called by the pipeline; header hard-coded "thousands"; silent default. | AUD-006 |
| FN-061 Tokens, type, shell | PARTIAL | Tokens and shell exist. 4 primitives missing; fonts not self-hosted; `/design` not dev-only; raw colors in new code; AA failures. | AUD-030, AUD-017 |
| FN-066 Brand + SourceChip | PARTIAL | Wordmark and SourceChip in the review list. Favicon still Vite; no chip in the debt card. | AUD-039 |
| FN-023 Locator union | PARTIAL | Real discriminated union; old jobs load; IDs stable. No migration script, no canonical serializer, provenance defaults fabricated. | AUD-025, AUD-037, AUD-018 |
| FN-020 EDGAR client | STUBBED | Works live for GOOGL but has no route or caller; duplicates the old wired client; burst 20 req/s. | AUD-015, AUD-038 |
| FN-021 iXBRL/HTML extractor | STUBBED | Unwired; on real filings it collapses periods, drops `(5)` negatives, and calls the cash-flow statement a reconciliation. | AUD-015, AUD-016, AUD-007 |
| FN-022 EX-99.1 | STUBBED | Unwired; picks the wrong 8-K; diff ignores periods (1,000 vs 1,050 gives "no discrepancy"). | AUD-015, AUD-016 |
| FN-024 Ingestion router | STUBBED | No API reaches it; accession path invents a CIK; cache key collides across users. | AUD-015, AUD-016, AUD-003 |
| FN-025 Shared cache | STUBBED | In-memory only; corrections keyed by label; user ids in the shared layer; no lazy recompute. | AUD-015, AUD-016 |
| FN-030 Generate-first | PARTIAL | Review sheet, DRAFT header, yellow/red cells on the `/generate` path. Auto path stamps VERIFIED; pending/unparsed items silently dropped. | AUD-004, AUD-008 |
| FN-062 Review redesign | PARTIAL | Popover, split button, stacked bar, J/K/Y/E/? and ●◐○ exist. No virtualization, nested scroll, broken page nav and zoom, no Playwright or Lighthouse. | AUD-019, AUD-020, AUD-032, AUD-001 |
| FN-063 Home + queue | PARTIAL | Pack cards, palette and split queue exist. Previews are mock text; "Request this" local-only; stepper not event-driven; Assign-to-Company kept. | AUD-031, AUD-017 |
| FN-064 Debt card + DataTable | PARTIAL | DataTable has sticky header and resize. Debt card clips at 1280, totals wrong, tie-out tautological. | AUD-013, AUD-029, AUD-036 |
| FN-031 Multi-period | PARTIAL | Columns and LTM exist. `period` is never set, so quarters collapse; last value wins; LTM arbitrary; no ticker trigger. p3 regressed same-year columns. | AUD-009 |
| FN-032 Deep links + viewer | PARTIAL | `write_url` on label cells, but every link is 404 on localhost; SEC URLs malformed; HTML viewer iframe is 404. | AUD-018 |
| FN-033 Add-back standardization | MISSING | Only a 7-category keyword function used by the QoE API. No toggles, LLM step, versioning or eval metric. | AUD-023, AUD-011 |
| FN-034 QoE + diff | PARTIAL | NetworkX import removed; pure diff exists. No sheet, panel or migration; endpoint returns nonsense and crashes. | AUD-021, AUD-022 |
| FN-067 Workbook preview | STUBBED | Component never imported by the app; renders built-in sample rows. | AUD-024 |

**Dependencies not satisfied:**
- FN-032 HTML deep links and viewer: needs FN-021 data in production, and there is none.
- FN-031: "trigger from ticker flow" (none exists) and FN-013 scale (unwired).
- FN-033: gated by FN-011, which is stubbed.
- FN-067: depends on FN-012 (stubbed).
- FN-062: depends on FN-003 (not fixed).
- FN-013: "iXBRL scale once FN-021 exists" was never integrated.

**Out-of-scope or early work:** the dark theme default and a manual theme toggle are FN-065 (Phase 4). No other Phase 4/5 ticket has been started: no auth, Postgres, billing or LLM abstraction.

**Reachability:**
- Unreachable from the UI or API: FN-020/021/022/024/025 code, FN-012's engine, FN-067's preview, and FN-034's QoE (API only, no UI).
- Section 8 of the plan still lists FN-030 to FN-067 as `todo`, while section 9 says done.

---

## 4. Symptom root-cause analyses

### A. The review screen's PDF does not load (AUD-001; related AUD-020, AUD-019)
- **End-to-end trace:**
  - Route: `ReviewPage` mounts.
  - Two parallel fetches: `GET /review/{id}/items` and `loadPdf(GET /review/{id}/pdf)`.
  - The server side is correct: 200 `application/pdf`, `access-control-allow-origin: http://localhost:5173`, and the OPTIONS preflight succeeds.
  - The pdf.js worker loads locally via Vite `?url` (no CDN).
  - The locator change in FN-023 doesn't affect PDF items, since page and bbox are synced from `PdfLocator`.
- **Failing step: client-side canvas rendering.**
  - The draw effect (`ReviewPage.tsx:315-344`) re-runs when `pdfDoc`, `selectedItem` or `currentPage` change. It sets `currentPage` itself and never cancels the previous `RenderTask` (`renderer.ts:42-75`).
  - If the PDF arrives first, the effect renders page 1. The items response then sets `selectedItem` and `currentPage`, and a second `page.render()` starts on the same canvas.
  - pdf.js 4.10 throws: *"Cannot use the same canvas during multiple render() operations"* (`pdf.mjs:13118`).
  - The catch sets `pageRenderError`, which hides the canvas wrapper (`display:none`), and nothing ever retries.
- **Reproduction:**
  - Natural: 4 of 20 opens failed across dev and prod builds and two jobs (`screens/review_dev_amazon_1280.png`, `review_prod_amazon_1280.png`, `review_dev_goog_dpr125_1280.png`).
  - Deterministic: holding `/items` until the PDF has loaded gives `screens/review_race_1280.png` every time.
  - The PDF endpoint answers 2-6× faster than `/items` (6-17 ms vs 10-83 ms), so the bad ordering is common, especially for large item lists (Amazon: 670 KB of items).
- **Same bug in the Audit Trail:** `AuditTrailView.tsx:269-310` uses the same pattern (`screens/audit_trail_1280.png`).
- **Age:** the race predates the phases (identical effect at `202f154`). The phases claimed the PDF pane fixed and redesigned, yet added no viewer test: mutation M5, where the page is never drawn, survives.
- **Related viewer defects:**
  - Next/Prev do nothing while an item is selected.
  - CSS-transform zoom clips the page under the sidebar.
  - The header with Export can be hidden under the sticky app bar.

### B. Broken UI/layout (per screen; screenshots in `docs/audit/screens/`)

**Home / queue** (`home_1280.png`, `home_1920.png`, `home_light_1280.png`, `home_light_1920.png`, `home_staged_light_1280.png`):
1. Wordmark appears twice: in the top bar and again in the page header.
2. `/design` button and a "Local · Single-User" badge in the production top bar (AUD-017).
3. Pack "OUTPUT PREVIEW" boxes are hard-coded mock lines with "—" values ("= Total Debt $2.5B").
4. "Auto-detects company and fiscal period" is false.
5. Fiscal-year column: the GOOGL Q1 10-Q shows **FY2025** (FN-060 #5 unfixed); Amazon shows a bare "Q2"; one row shows "—".
6. Duplicate rows: GOOGL ×3, plus a byte-identical file under another name (FN-060 #6 unfixed). The client skips duplicates by name+size but says "1 file was rejected".
7. A zombie "EXTRACTING" row never resolves; the UI polls every 3 s forever (AUD-035).
8. Row divider lines span only the FILE column, so the borders break at "Workflow pack".
9. "Assign to Company (Optional)" field still present (FN-063 said delete).
10. Default theme is dark (plan: light-first).

**Design** (`design_1280.png`, `design_1920.png`):
- Reachable in production.
- Ticket IDs in user-facing headings.
- Hard-coded "WCAG AA … PASS" badges with wrong ratios.
- Shows only the active theme, not light and dark.

**Review** (`review_1280.png`, `review_1920.png`, `review_light_1280.png`, `review_light_list_1280.png`, `review_zoom130_1280.png`, `review_afterJ_1280.png`, `review_afterJrapid_1280.png`, `review_race_1280.png`, `review_docling_mirrored_highlight_1280.png`):
1. The review header (title, back button, **Export to Excel**) is hidden under the sticky app bar when the window keeps its queue scroll position (`review_1280.png`).
2. "← ← Back to Queue": icon plus a literal arrow.
3. Debt card for a non-GAAP job sits above the list: header clipped at "MATURI", "Long-term debt" wraps to 3 lines (FN-060 #2 **regressed**), "$21,769M" is wrong, and "TIE-OUT: PASS" is tautological (AUD-013).
4. Item list is below the fold (first card at y=893 of 800). There are nested scroll areas and no virtualization (AUD-019).
5. Default selected item is not in the default Flagged tab.
6. Each card carries both "Page 1" and a "[p.1]" chip.
7. Light theme shows a dark band above the white PDF page.
8. Zoom 130% pushes the page under the sidebar and blurs it. Next/Prev are no-ops (AUD-020).
9. Docling jobs: the highlight is mirrored to the bottom of the page (AUD-002).
10. Intermittent "Page Rendering Error" (A).
11. Console: `GET /footnote/{id}/lease` 404 ×2 on every open; "two children with the same key" from duplicate debt tranche ids (Amazon).

**Audit trail** (`audit_trail_1280.png`, `audit_trail_1920.png`):
- Same canvas error as A.
- Page header cut under the sticky bar.
- The sidebar is a wall of ~140 cell chips.

**Command palette** (`command_palette_light_1280.png`, `command_palette_GOOGL_1280.png`): typing "GOOGL" returns only "Upload a filing", because there is no ticker search (AUD-015).

**Queue overflow menu:** `queue_overflow_menu_1280.png`.

**Checked OK:**
- No horizontal page scroll at 1280 or 1920 on home, design or review.
- Queue buttons don't wrap.
- No "?" glyphs.
- The company input is themed.

### C. "Design" button and hard-coded design suggestions (AUD-017)
- **Where the button comes from:** `AppShell.tsx:153-176` renders the button whenever `onNavigate` is passed, and `App.tsx` passes it on every screen. `App.tsx:37-44` and `:251-264` route `/design` and `#/design` unconditionally. There are zero uses of `import.meta.env` in `frontend/src`, so nothing is dev-only.
- **It ships:** the production bundle contains the design page ("Design System" ×2, "Exit Design" ×1).
- **Hard-coded "suggestions" in production screens:**
  - Pack-card previews (`UploadZone.tsx:16-38`).
  - "Auto-detects company and fiscal period".
  - The "Local · Single-User" badge (`AppShell.tsx:149`).
  - Fake contrast-audit badges (`DesignPreviewPage.tsx:566-603`).
  - Ticket IDs in headings.
- **Not shipped:** the WorkbookPreview `sampleData.ts` is not wired (AUD-024), so it doesn't appear in production; the build tree-shakes it.

### D. Correct values, ~two-thirds flagged (AUD-003; counts below)

| Run | Parser | Items | auto_accepted / needs_review band | Final status | Flagged |
|---|---|---|---|---|---|
| User `9d00e013` (2026-09-17, pre-phase) | pymupdf | 104 | 27 / 77 | 98 locked, 6 pending | 6% (after batch-confirm by the old "Generate Model (N)" button) |
| User `3906eb32` (2026-10-02, post-phase) | pymupdf | 104 | 27 / 77 | 34 locked, 64 needs_review, 6 pending | **67%** |
| User `a04a4f1e` Amazon (2026-10-02) | pymupdf | 954 | 609 / 345 | 601 locked, 171 needs_review, 182 pending | 37% |
| Audit `8716f887`, same GOOGL PDF, `.venv` | **docling** | 105 | 104 / 1 | 98 locked, 6 pending, 1 needs_review | **7%** |

**Reasons for the 77 needs_review items in the user's GOOGL runs:**

| Reason | Count | Mechanism |
|---|---|---|
| Flat label | 75 | Score exactly 0.90: `missing_header_hierarchy` (−0.15, label has no " / ") + `value_is_numeric` (+0.05) |
| Flat label + footnote marker | 2 | 0.85 and 0.80 |

The 6 pending items are taxonomy misses.

**Precise cause:**
1. **The server ran without Docling.** System Python, which `uvicorn` on PATH resolves to, lacks `docling`. `docling_parser.py:328-339` catches the ImportError-derived failure and silently uses PyMuPDF. Reproduced: `scratchpad/parse_probe.py` under system Python gives exactly 27/77, and under `.venv` gives 104/1.
2. **PyMuPDF labels omit the column header.** Docling: "Cash and cash equivalents / As of December 31, 2024". PyMuPDF: "Cash and cash equivalents". The two period values become indistinguishable.
3. **The scorer's −0.15 alone crosses the 0.95 threshold** (`confidence.py:96-125`, `:68`). The +0.15 offset applies only to reconciliation candidates, and a 10-Q has none.
4. **Status assignment is unchanged** since before the phases (`review/repository.py:521-535`). The phases removed the "Generate Model (N)" button that used to batch-confirm everything, so the flag rate became visible.
5. **Tie-out downgrades (FN-012) and FN-030 rules play no part.** FN-012 is not wired, and FN-030 does not change statuses.

**Recommended fix:**
- Fail fast or show a banner when Docling is unavailable, and stamp the reason on the job.
- Start the server from `.venv`.
- Give PyMuPDF labels their column header.
- Make the hierarchy penalty depend on a detected header row.

Expected outcome: under 10% flagged on this filing, as already measured.

### E. EDGAR / ticker ingestion missing (AUD-015, AUD-016, AUD-038)

| Ticket | Exists | Wired? | State |
|---|---|---|---|
| FN-020 | `app/ingestion/edgar/` (client, rate limiter, circuit breaker, models) | No route or caller | Works live (GOOGL latest 10-Q/10-K correct, per sub-agent) |
| FN-021 | `app/extraction/html/` (detector, iXBRL parser, table parser, extractor) | Only via router_engine/exhibit_99 | Period collapse, `(5)` dropped, false-positive detection |
| FN-022 | `app/ingestion/exhibit_99/` | Same | EX-99.1 discovery works; 8-K choice and diff wrong |
| FN-024 | `app/ingestion/router_engine.py` | **No importer** | Accession path fabricates `cik="0000000000"`; cache key collisions |
| FN-025 | `app/extraction/shared_cache.py` | **No importer** | In-memory only, keyed by label |
| UI | none | n/a | No ticker input; ⌘K palette filters local companies only |

**Pre-existing pieces:**
- `ingestion/edgar_client.py` (2026-08-29), behind `/upload/edgar/search`, `/upload/edgar/filings/{cik}` and `POST /upload/edgar`, which downloads a **PDF**. Modern primary documents are `.htm`, so it likely fails (HYPOTHESIS).
- The frontend never calls these routes.

**Depends on Phase 2:**
- FN-031 ticker trigger.
- FN-032 SEC links and HTML viewer.
- FN-062 HTML sweep.
- FN-063 ticker search.
- Phase 5 FN-050/051.

---

## 5. Invariant check results

| Invariant | Verdict | Evidence |
|---|---|---|
| I1: classifier/LLM never reads or writes numbers | **BREACH** (AUD-011) | **Output side holds:** result models carry no value field (`ClassifierRawResponse` has label plus a `confidence` float, consistent with FN-044's shape). **Input side breaks:** 178 of 677 Groq payloads in `a04a4f1e_decision_log.jsonl` contain figures ("… END OF PERIOD / 69,893"). The architecture test checks field names only. |
| I2: formula engine pure | **WEAKENED** (AUD-028) | **Pure:** `tie_out_checker` and `qoe_diff`, deterministic sorting. **Hidden input:** `tree.py` uses `SEED_MASTER_TAXONOMY`, read from the mutable `data/taxonomy.json` at import; `reader.py` logs labels. The boundary test does not forbid pathlib, json or open. |
| I3: no silent failures | **BREACH** | Silent Docling fallback (AUD-003). VERIFIED stamp and dropped items (AUD-004, AUD-008). Always-PASS checks (AUD-005). Silent "thousands" (AUD-006). Bogus "found" target metric (AUD-007). `(5)` → None and `except: pass` (AUD-016, AUD-025). QoE `(x)` → 0.0 (AUD-021). Zombie job (AUD-035). `gates.yaml` errors swallowed (`eval/metrics.py:781`). |
| I4: every number has provenance | **BREACH** | Docling boxes mirrored (AUD-002). Every workbook link 404 (AUD-018). Fabricated defaults page 1 / full page / "unknown.pdf" (AUD-025, latent). PyMuPDF path has correct boxes (104/104, 954/954). |
| I5: numbers are numbers, derived cells are formulas | **PARTIAL** | **Holds:** Source_Inputs 97/98 numeric; Reconciliation 140/140 formulas; inputs not overwritten. **Breaches:** text values inside SUM ranges (`$(159)`, "—"); constant "PASS"/0/1 on the Checks sheet; Review sheet values and confidence as text; debt generator rates as text (AUD-005, AUD-008, AUD-036). |
| I6: no document content in logs | **BREACH** (AUD-012) | WARNING logs of labels and values (`dispatcher.py:206-211`, `coordinate_normalizer.py:194-199`) plus several DEBUG/INFO sites. Mostly pre-existing. |

**Broad `except` inventory (I3), most relevant:**
- `docling_parser.py:328` (fallback) and many `noqa: BLE001` cell-level catches.
- `extraction/models.py:157` (`except Exception: pass`).
- `router_engine.py:171-172` and `:357-358`.
- `edgar/client.py:363-364`.
- `eval/metrics.py:781` (`try/except/pass`).
- `generator.py:770` and `multi_year_generator.py:452`. These return `is_success=False` with `error_detail`, which is acceptable.

---

## 6. Test-suite quality assessment

**Why the tests are green while the app is broken:**
1. **The frontend has no DOM.** `vite.config.ts` uses `environment: 'node'` and components are tested with `renderToString`. Effects never run, so the PDF viewer, highlight overlay, keyboard flow and layout are untested. There is no Testing Library or Playwright. FN-062 required a Playwright test.
2. **Backend tests assert the defects:**
   - The Docling inversion: 3 parametrized tests fail when it is fixed (M3).
   - The 404 link URL (`test_generate_first.py:128`).
   - The `flat_idx` tests recompute the formula inline and never call production code (`test_coordinate_normalizer.py:227-270`).
   - `DummyRecord.record_id`, a field no real model has (`test_tie_out_checker.py:162-183`).
3. **Fixtures are idealized.**
   - The golden highlight test builds a synthetic PDF and a hand-made `parser_used="pymupdf"` item.
   - Phase 2 fixtures give the 8-K the 10-Q's period.
   - The HTML fixtures carry the year in each header.
   - The corpus tests count tag strings in fabricated data.
4. **The critical paths have no test coverage at all:**
   - Running a real Docling parse and checking highlight placement.
   - A `process_queued_job` run that ends in a workbook download (the VERIFIED-stamp path).
   - The Checks sheet actually evaluating to PASS or FAIL.
   - Units.
   - The QoE endpoint on real review items.
5. **Nothing tests behaviour against the acceptance criteria:**
   - No skipped or xfail tests, which is good.
   - No snapshot tests of empty output.
   - No LibreOffice recalculation.
   - No link checks.

**Mutation results.** Each mutation was applied, its tests run, then reverted with `git checkout`. `git status` afterwards shows only `?? docs/audit/`.

| # | Mutation (file) | Tests run | Result |
|---|---|---|---|
| M1 | Auto-accept threshold 0.95 → 0.85 (`extraction/confidence.py`) | test_confidence, test_flagger | KILLED (4 failed) |
| M2 | needs_review band → `locked` (`review/repository.py`) | tests/review, test_job_runner*, integration | KILLED (5 failed) |
| M3 | Remove Docling Y-inversion, i.e. the **correct fix** (`coordinate_normalizer.py`) | coordinate + golden + integration | KILLED (3 failed): **the tests enforce the bug** |
| M4 | Header always "VERIFIED" (`excel_export/generator.py`) | tests/excel_export | KILLED (1 failed) |
| M5 | PDF page never drawn (`ReviewPage.tsx`) | vitest (all) | **SURVIVED** (94/94) |
| M6 | Highlight y-mirrored (`ReviewPage.tsx`) | vitest (all) | **SURVIVED** (94/94) |
| M7 | Auto workbook gets no inputs (`job_runner.py`) | job runner + excel tests | KILLED (3 failed) |
| M8 | Checks footing status hard-coded PASS (`generator.py`) | excel_export + formula_engine | **SURVIVED** (70 passed) |
| M9 | EDGAR token bucket capacity 10 → 1000 (`rate_limiter.py`) | tests/ingestion | **SURVIVED** (120 passed) |
| M10 | QoE values all 0.0 (`drift/qoe_diff.py`) | tests/drift | **SURVIVED** (45 passed) |

5 of 10 survived, and one of the 5 kills (M3) shows the tests protecting a defect.

---

## 7. Findings

Ordered by severity. The same records are in `docs/audit/findings.json`.

### AUD-001 [P0] Review (and Audit Trail) PDF viewer intermittently fails with a pdf.js concurrent-render error (Symptom A)

- **Severity:** P0 · **Category:** viewer/runtime · **Tickets:** FN-003, FN-062
- **Verification:** VERIFIED
- **Evidence:**
  - Reproduced naturally, no interception: 4 of 20 review opens failed (dev amazon 2/5, dev goog @DPR 1.25 1/5, prod build amazon 1/5, prod goog 0/5). Viewer shows 'Page Rendering Error: Cannot use the same canvas during multiple render() operations...' and the canvas wrapper is display:none. scratchpad/scen_open.py; screens/review_dev_amazon_1280.png, review_prod_amazon_1280.png, review_dev_goog_dpr125_1280.png
  - Deterministic repro: hold /review/{id}/items until the PDF has loaded (CDP Fetch pause, CPU x6) gives the same error every time. screens/review_race_1280.png
  - frontend/src/components/review/ReviewPage.tsx:315-344: draw effect depends on [pdfDoc, selectedItem, currentPage], calls setCurrentPage inside itself, and on cleanup only sets a `cancelled` flag; the previous RenderTask is never cancelled. lib/pdf/renderer.ts:42-75 discards the RenderTask.
  - pdfjs-dist 4.10 guard: node_modules/pdfjs-dist/build/pdf.mjs:13118 (#canvasInUse) throws when a second render starts on the same canvas.
  - Race trigger: GET /review/{id}/pdf answers in 6-17 ms vs /items 10-83 ms (curl timings), so the PDF often renders page 1 before items arrive; items then set selectedItem/currentPage, starting a second render mid-flight.
  - Error is sticky: pageRenderError hides the canvas (ReviewPage.tsx:1583) and nothing retries.
  - Same pattern in components/audit/AuditTrailView.tsx:269-310; screens/audit_trail_1280.png shows the identical error.
  - Server side is fine: /review/{id}/pdf 200 application/pdf with correct CORS headers (curl -D -).
  - Latent since before Phase 0 (same effect at 202f154), but FN-003/FN-062 claimed the PDF pane fixed/redesigned and added no viewer test (mutation M5 survived).
- **Root cause:** Un-cancelled pdf.js render tasks on a shared canvas plus an effect that re-triggers itself; error state is terminal.
- **User impact:** Source PDF intermittently blank with a cryptic error on the product's core screen and in the Audit Trail; the reviewer cannot verify values.
- **Suggested fix:** Keep the RenderTask in a ref; in the effect cleanup call renderTask.cancel() and await its rejection before the next render (or serialize renders through a queue); derive target page without setState inside the effect; clear the error and retry on the next selection; apply the same to AuditTrailView; add a jsdom/Playwright test that loads the PDF before items.
- **Effort:** S · **Depends on:** none

### AUD-002 [P0] Every Docling-extracted highlight box is vertically mirrored; the FN-003 'Docling origin' P0 was never fixed

- **Severity:** P0 · **Category:** provenance/correctness · **Tickets:** FN-003, FN-023
- **Verification:** VERIFIED
- **Evidence:**
  - scratchpad/bbox_probe.py (does the item bbox contain the PyMuPDF location of its own value text?): Docling job 8716f887 hit 3 / miss 100 / not-found 2; PyMuPDF jobs 3906eb32 104/104, 9d00e013 104/104, a04a4f1e 954/954.
  - Example: 'Cash and cash equivalents' $23,466 stored bbox y=706-716 (0-1000 space); value actually at y=284-294 = 1000 - y.
  - Raw Docling cell box in 8716f887_docling.json: y0=239.36, y1=247.79 on an 842 pt page, i.e. already top-left origin; backend/app/extraction/coordinate_normalizer.py:74-90 inverts every 'docling' item unconditionally and ignores bbox.coord_origin.
  - UI: selected item highlight drawn at top=891px of a 1263px canvas instead of ~359px. screens/review_docling_mirrored_highlight_1280.png (highlight is off-screen at the bottom).
  - docs/AUDIT.md (FN-000) itself lists 'Docling Y-axis inversion: still open'; p0 commit 1dd6560 changed only the PyMuPDF flat_idx (docling_parser.py:646).
  - Tests enforce the bug: removing the inversion (mutation M3) fails 3 tests in tests/extraction/test_coordinate_normalizer.py. The FN-003 golden test (tests/extraction/test_golden_fixture_highlight.py) uses a synthetic PDF and a hand-built item with parser_used='pymupdf', so it never exercises Docling.
  - Hidden in the user's environment because their server falls back to PyMuPDF (AUD-003); fixing AUD-003 will expose this.
- **Root cause:** Coordinate normalizer assumes Docling table-cell boxes are bottom-left origin; in docling-core 2.x they are top-left (coord_origin field).
- **User impact:** Click-to-source highlights the wrong row on every Docling-parsed filing, which destroys trust (I4).
- **Suggested fix:** Branch on bbox.coord_origin (BOTTOMLEFT -> invert, TOPLEFT -> scale only); replace the parametrized inversion tests with a golden test that runs the real Docling parser on a committed small fixture and asserts the value's PyMuPDF text location falls inside the bbox.
- **Effort:** S · **Depends on:** AUD-003

### AUD-003 [P0] Over-flagging root cause: the server silently falls back from Docling to PyMuPDF, whose labels lose the period header and score 0.90 (Symptom D)

- **Severity:** P0 · **Category:** environment/I3 · **Tickets:** FN-003, FN-024
- **Verification:** VERIFIED (that the user's server ran without Docling is a HYPOTHESIS strongly supported by identical 27/77 counts; not observed directly)
- **Evidence:**
  - All 5 of the user's jobs (2026-09-09 to 2026-10-02) have summary.parser_used='pymupdf'; the GOOGL runs all show exactly 27 auto_accepted / 77 needs_review (backend/data/results/*_summary.json).
  - Same GOOGL PDF via scratchpad/parse_probe.py: system Python (C:\Program Files\Python311, which `uvicorn` on PATH resolves to: C:\Users\NIRAJ\AppData\Roaming\Python\Python311\Scripts\uvicorn.exe) -> 'Docling library is not installed' -> pymupdf, bands needs_review 77 / auto 27 (exact match). .venv Python -> docling, auto 104 / needs_review 1.
  - Fresh pipeline run in .venv (job 8716f887): 98 locked / 6 pending / 1 needs_review = 7/105 flagged, versus the user's 3906eb32: 34 locked / 64 needs_review / 6 pending = 70/104 flagged (67%).
  - Scorer arithmetic, backend/app/extraction/confidence.py:96-125: start 1.0, flat label without ' / ' -0.15 (missing_header_hierarchy), numeric +0.05 = 0.90 < 0.95 threshold (confidence.py:68). PyMuPDF labels are 'Cash and cash equivalents'; Docling labels are 'Cash and cash equivalents / As of December 31, 2024'. 75 of 104 items score exactly 0.90.
  - The +0.15 reconciliation bonus never applies: is_reconciliation_candidate=False for all 104 records (a 10-Q has no Adj. EBITDA bridge).
  - PyMuPDF path also drops the period: two values (23,466 Dec-24 and 23,264 Mar-25) carry the same label with no period, and both land in the workbook unlabeled.
  - Status derivation is unchanged since 202f154 (review/repository.py:521-535). The pre-phase run 9d00e013 showed 98 locked only because the old 'Generate Model (N)' button batch-confirmed everything (ReviewPage.test.tsx:208 confirm-batch then generate); FN-030/FN-062 removed that button, so the flag rate became visible.
  - Silent fallback: docling_parser.py:328-339 catches any Exception, logs one WARNING (no app logging configured) and continues; the only UI trace is an 'ENGINE: PYMUPDF' badge; /health does not report Docling.
- **Root cause:** Environment: server started outside .venv, so Docling import fails. Code: (a) the fallback is silent (I3), (b) the PyMuPDF parser does not carry column headers into labels, (c) the scorer penalizes flat labels by a fixed -0.15 that alone crosses the auto-accept threshold.
- **User impact:** About two-thirds of correct values are flagged; period columns are indistinguishable; a reviewer must clear 64+ items per filing.
- **Suggested fix:** Fail fast: refuse to start (or mark /health degraded and show a banner) when Docling is missing; record the fallback reason on the job and show it; add `make run` using the venv interpreter; give PyMuPDF labels their column header; make missing_header_hierarchy conditional on a known header row instead of a substring check.
- **Effort:** S · **Depends on:** none

### AUD-004 [P0] Auto-generated workbook is stamped VERIFIED while containing unreviewed values; the same job is VERIFIED or DRAFT depending on which path wrote it

- **Severity:** P0 · **Category:** excel/I3 · **Tickets:** FN-030
- **Verification:** VERIFIED (workbook and code by auditor; path replay by sub-agent)
- **Evidence:**
  - backend/data/models/3906eb32..._model.xlsx (openpyxl): Reconciliation!B1='VERIFIED'; Review!A2='Verified: All items confirmed'; 71 of its 98 Source_Inputs values are needs_review-band records; the 6 pending-taxonomy items are absent.
  - backend/app/formula_engine/reader.py:72-80 treats ClassifiedRecord.is_confirmed (taxonomy label matched) as 'value confirmed'; job_runner.py:198 calls read_formula_inputs with include_unreviewed=False, so matched-but-unreviewed items become 'confirmed' and the rest are dropped with only excluded_count += 1.
  - POST /models/{id}/generate (excel_export/router.py:110-116) uses review items with include_unreviewed=True and writes 'DRAFT: N items unverified' (a04a4f1e workbook has 171 yellow cells). Sub-agent replay: path (a) on 3906eb32 -> VERIFIED, path (b) -> 'DRAFT: 64 items unverified' (scratchpad/demo_single.py).
  - Queue primary action 'Excel (.xlsx)' (JobList.tsx:465-476) and the review dropdown 'Download .xlsx' (ReviewPage.tsx:772-781) serve whichever file was written last, i.e. the VERIFIED auto workbook until the user clicks Export.
- **Root cause:** Two generation paths with different inclusion rules; taxonomy confirmation conflated with human value review.
- **User impact:** Analyst downloads a workbook that certifies unreviewed extractions as VERIFIED (FN-030 AC 'never silently filled' fails).
- **Suggested fix:** Single inclusion rule driven by confidence_band + explicit human confirmation; job_runner uses the same review-item path as /generate; list every excluded item with its reason on the Review sheet; integration test through process_queued_job.
- **Effort:** M · **Depends on:** none

### AUD-005 [P0] Checks sheet always shows PASS; the FN-012 tie-out engine is not wired and can never demote items

- **Severity:** P0 · **Category:** excel/false-assurance · **Tickets:** FN-012, FN-067
- **Verification:** VERIFIED
- **Evidence:**
  - backend/app/excel_export/generator.py:653-663: footing row compares Reconciliation total with SUM(Source_Inputs) of the same leaves, which is identical by construction.
  - generator.py:665-679: 'Sign & Arithmetic' and 'Reporting Period' rows are literal 0/1 values and the string 'PASS' (confirmed in 3906eb32_model.xlsx Checks rows 5-6).
  - backend/app/formula_engine/tie_out_checker.py has no production importer (grep); its sign/period checks are stubs that always pass (:333-373), interest is never checked (:277-330), and apply_check_results_to_records matches a record_id field no model has (:419).
  - Sub-agent probe through the production generator: Net income 50,000 + tax 10,000 vs reported 99,999 produced Adjusted EBITDA 159,999 with PASS on all rows (scratchpad/probe_p1.py).
  - Mutation M8 (footing status hard-coded to PASS) survived tests/excel_export + tests/formula_engine (70 passed). No LibreOffice recalculation test exists; soffice is not installed.
- **Root cause:** Checks sheet written as decoration rather than generated from check results; engine left unwired.
- **User impact:** Every workbook certifies tie-outs as PASS regardless of content, including the nonsense bridge in AUD-007.
- **Suggested fix:** Generate Checks rows from run_tie_out_checks results with live formulas comparing components vs the extracted reported total; delete constant rows; wire demotion by node id into review status with a reason; add a recalculation test (formulas lib or soffice when available).
- **Effort:** M · **Depends on:** AUD-007

### AUD-006 [P0] Workbook header always says 'Amounts in thousands'; scale detection exists only as an unwired library

- **Severity:** P0 · **Category:** excel/units · **Tickets:** FN-013
- **Verification:** VERIFIED
- **Evidence:**
  - backend/app/excel_export/generator.py:434-436: format_workbook_units_header(UnitScale.THOUSANDS) unconditionally; both 2026-10-02 workbooks read 'Amounts in thousands' while the filings say 'in millions'.
  - extraction/scale_and_sign.py is imported only by generator.py (header string) and the unwired tie_out_checker.py; docling_parser.py:82-85,108-110 discards 'in millions' captions as noise.
  - scale_and_sign.py:232,248-254 defaults to THOUSANDS with no flag when no caption (sub-agent probe); the exemption regex (:77-80) also exempts 'Gross margin' and 'interest rate swaps'.
- **Root cause:** FN-013 delivered pure helpers but no pipeline integration; header hard-coded.
- **User impact:** Every workbook misstates units by 1000x for millions-denominated filings.
- **Suggested fix:** Capture caption/qualifier rows as table metadata, call detect_scale_from_caption, carry scale on records and nodes, write the header from it, and flag 'Units undetermined' instead of guessing; tighten the exemption regex.
- **Effort:** M · **Depends on:** none

### AUD-007 [P0] Filings with no non-GAAP reconciliation still produce an 'Adjusted EBITDA' that is the sum of balance-sheet and OCI lines

- **Severity:** P0 · **Category:** extraction/I3 · **Tickets:** FN-021, FN-024, FN-030
- **Verification:** VERIFIED
- **Evidence:**
  - 3906eb32_model.xlsx Reconciliation: rows 4-142 are Cash, Short-term investments, Comprehensive income... and row 143 'Adjusted EBITDA' sums them; header VERIFIED; Checks PASS.
  - job_runner.py:133 target_metric_found = pack_candidate_found or bool(docling_items) is True whenever anything was extracted; summary.json shows target_metric_found=True with filtered_non_reconciliation_count=104 (no candidates).
  - review/repository.py:511-517 shows every record when no candidate exists, so a 10-Q review lists the whole balance sheet (104 items; Amazon 954).
  - Sub-agent: the HTML extractor likewise accepts the cash-flow statement as a 'reconciliation' (score 0.55 >= 0.5) on Alphabet's real 10-Q, so FN-021's 'not found' status never fires.
- **Root cause:** No explicit 'target metric not found' outcome; fallback to all records feeds the formula tree; tree sums every leaf into the target.
- **User impact:** A plausible-looking but meaningless Adjusted EBITDA number is delivered for any filing that lacks a bridge.
- **Suggested fix:** When no reconciliation candidate exists, end the job with model_skip_reason='Adjusted EBITDA reconciliation not found in this filing' and do not build a bridge; review only shows candidate tables; exclude the reported total from summed components (tree.py:658-666).
- **Effort:** S · **Depends on:** none

### AUD-008 [P0] Pending-taxonomy and unparseable items are silently omitted from totals and the Review sheet; Phase 3 added a zero-fill for empty values

- **Severity:** P0 · **Category:** excel/I3-I5 · **Tickets:** FN-030
- **Verification:** VERIFIED (sub-agent; auditor re-checked 3906eb32 Source_Inputs!B90 = '$(159)' str, 93 int + 4 float + 1 str)
- **Evidence:**
  - formula_engine/reader.py:207-212 drops pending_taxonomy_confirmation items even with include_unreviewed=True: 6/104 (3906eb32) and 182/954 (a04a4f1e) missing from workbook and Review sheet (sub-agent, demo_single.py).
  - Values that do not parse are written as text (generator.py:383-386) and skipped by SUM: '$(159)' at 3906eb32 Source_Inputs!B90; 60 text values in a04a4f1e (28 x '—', ranges). excel_export/utils.py:33-36 only handles a leading '('.
  - reader.py:268,273,283 (new in ffb3bcf): node_val = str(raw_val or '0'), so an empty value becomes 0 (latent; no empty values in current data).
- **Root cause:** Inclusion and parsing failures are counted but never surfaced in the deliverable.
- **User impact:** DRAFT counts understate open items; totals silently exclude values (I3/I5).
- **Suggested fix:** Every non-included or non-numeric item gets a Review-sheet row with reason; parse '$(x)'; write blanks + flag instead of text or zero.
- **Effort:** S · **Depends on:** AUD-004

### AUD-009 [P0] Multi-period workbook collapses same-year quarters, keeps an arbitrary value per label and labels an arbitrary 4-column SUM as LTM

- **Severity:** P0 · **Category:** excel/multi-period · **Tickets:** FN-031, FN-013
- **Verification:** VERIFIED (code by auditor; data-loss demos by sub-agent)
- **Evidence:**
  - multi_year_generator.py:94-100 keys periods on JobRecord.period, which no production code sets (jobs.json: period null for all jobs), so it falls back to FY{filing_year}; two 10-Qs of one year collapse into one column and the earlier one is marked 'Restated, was X' (sub-agent scratchpad/demo_multi.py).
  - multi_year_generator.py:170-178 leaf_map[label] = leaf keeps only the last value per label: real AMZN data 772 leaves, 45 labels, 727 values hidden (sub-agent).
  - multi_year_generator.py:354-362 LTM = SUM of the last <=4 columns whatever they are (annual + quarters, blanks count as 0).
  - company_router.py:217,221 now passes include_unreviewed=True but the generator has no status styling, DRAFT header or Review sheet; no units header; no 52/53-week handling; LibreOffice check absent.
- **Root cause:** No structured period on records/jobs (depends on FN-013/FN-021 data that was never wired); dictionary keyed by label.
- **User impact:** Multi-period output can drop quarters, show wrong comparative values and a meaningless LTM.
- **Suggested fix:** Carry period_end/duration per record; key columns on fiscal period; build LTM only from 4 consecutive quarters else #N/A + reason; reuse FN-030 status styling and Review sheet.
- **Effort:** L · **Depends on:** AUD-006, AUD-016

### AUD-010 [P0] The 40-filing benchmark corpus is hand-typed and largely fictitious (wrong accessions/CIKs, plugged totals, copied 'second annotator')

- **Severity:** P0 · **Category:** eval/fabrication · **Tickets:** FN-010
- **Verification:** VERIFIED (code; live EDGAR checks by sub-agent)
- **Evidence:**
  - All labels are literals in eval/build_benchmark_corpus.py:19-950; second-annotator fields copy the primary label (:973-977, re-checked by auditor).
  - Both MSFT label files use Amazon's CIK prefix 0001018724 (eval/corpus/labels/0001018724-23-000012.json, -000014.json; re-checked).
  - Sub-agent live EDGAR check: only 2 of 40 accessions resolve to the claimed form; 15 resolve to unrelated filings (Form 4, SC 13G/A, SD, 144); 23 return 503 like a nonexistent accession (HYPOTHESIS strength for those 23).
  - Every filing foots exactly; every line has the same template locator 'table//tr'; all 115 lines are millions; no XBRL seeding code; eval/fetch_filings.py:60 uses the accession where the CIK belongs and caches a 165-byte 'MOCK SEC EDGAR FILING' on failure (eval/.cache/0001018724-23-000014_10-K.html, dated 2026-10-01).
- **Root cause:** Labels authored by the coding agent instead of derived from filings.
- **User impact:** Any accuracy figure computed on this corpus is meaningless; plan section 9 and DECISIONS.md present it as real.
- **Suggested fix:** Delete the fabricated labels; rebuild from real accessions via the submissions API, seed GAAP lines from companyfacts, human-label non-GAAP lines with real locators; validate accession/CIK consistency.
- **Effort:** L · **Depends on:** none

### AUD-011 [P0] I1 breach: financial figures are sent to the Groq LLM inside 'labels'

- **Severity:** P0 · **Category:** invariant/I1 · **Tickets:** FN-033, FN-044
- **Verification:** VERIFIED
- **Evidence:**
  - backend/data/results/a04a4f1e..._decision_log.jsonl: 178 of 677 classifier input payloads contain figures, e.g. 'CASH, CASH EQUIVALENTS, AND RESTRICTED CASH, END OF PERIOD / 69,893'; 3906eb32: 4 of 14 (share counts).
  - classification/dispatcher.py:109 builds ClassifierInputPayload(label=raw_label) with the raw extracted label; labels carry the header-cell value when header detection fails.
  - tests/test_architecture_boundaries.py checks only field NAMES of the payload model, not content.
- **Root cause:** Label construction appends header-row cell text that can be a number; no numeric scrub before dispatch. Likely pre-existing (HYPOTHESIS).
- **User impact:** Breaks the product's core trust promise and the data-egress statement in README (numbers leave the machine).
- **Suggested fix:** Strip numeric tokens from payloads before dispatch (and assert in the client); fix label construction; add a content-level I1 test on recorded payloads.
- **Effort:** S · **Depends on:** none

### AUD-012 [P0] I6 breach: document text and values are written to logs

- **Severity:** P0 · **Category:** invariant/I6 · **Tickets:** FN-045
- **Verification:** VERIFIED (code reading)
- **Evidence:**
  - classification/dispatcher.py:206-211 WARNING logs the raw label; extraction/coordinate_normalizer.py:194-199 WARNING logs item.value; DEBUG: coordinate_normalizer.py:81-88 (value), confidence.py:167-172 (label), formula_engine/reader.py:90-95 (label); extraction/shared_cache.py:204 INFO logs the label key (new in p2, unwired).
  - Most lines pre-date the phases (sub-agent: none introduced by ffb3bcf).
- **Root cause:** Diagnostic logging includes cell content.
- **User impact:** Filing content in server logs; rubric treats invariant breaches as P0 although impact is local today.
- **Suggested fix:** Log record indices / hashes only; add a log-redaction test.
- **Effort:** S · **Depends on:** none

### AUD-013 [P0] Debt card (shown on every review) presents wrong totals with a tautological 'TIE-OUT: PASS'

- **Severity:** P0 · **Category:** ui/wrong-numbers · **Tickets:** FN-064, FN-012
- **Verification:** VERIFIED
- **Evidence:**
  - GOOGL non_gaap job: 'TOTAL PRINCIPAL $21,769M' = 10,883 (Dec-24) + 10,886 (Mar-25), i.e. two balance-sheet dates of the same 'Long-term debt' line summed; badge 'TIE-OUT: PASS'. screens/review_1280.png
  - backend/app/footnote/extractor.py:224 total_debt = sum(valid_principals); frontend DebtScheduleCard.tsx:151-163 compares sum(tranches) with that same sum (missing principal counted as 0).
  - Amazon non_gaap job: debt.json has 75 'tranches' with total_debt 3,172,102 ($3.17T); duplicate tranche id debt-36df33cef318 causes React 'two children with the same key' warnings (dev console).
  - Card renders for non-capital-structure jobs and fires GET /footnote/{id}/lease -> 404 on every review open (console errors).
- **Root cause:** Debt extraction runs on whole-document records without period/table scoping; tie-out compares a total with itself.
- **User impact:** Prominent hero number is wrong by 2x or 1000x+ and certified as PASS.
- **Suggested fix:** Only show footnote cards for capital_structure jobs; scope tranches to the debt note and a single period; tie out against the balance-sheet debt total; dedupe ids; treat lease 404 as 'not extracted' state.
- **Effort:** M · **Depends on:** none

### AUD-014 [P1] Eval runner and CI gate are stubs; the gate passes an extractor that gets every value wrong

- **Severity:** P1 · **Category:** eval · **Tickets:** FN-011
- **Verification:** VERIFIED (sub-agent; auditor confirmed no .github and Makefile content)
- **Evidence:**
  - Sub-agent probe_gate2.py: 10 value_mismatch diffs -> value_exact_match 0.0, recall 1.0, precision 1.0, GATE PASSED (eval/metrics.py:683-687, 649-656 default empty denominators to 1.0).
  - make eval runs the old 5 fictional PDFs (run_benchmark.py:203,209), ignores --split, exits 0 on gate failure (Makefile:4 lacks --strict); cassette directory eval/cassettes does not exist (record_replay.py:23); calibration buckets hard-coded (metrics.py:714-731); cost a constant (run_benchmark.py:265).
  - test_gates.py:143-177 'broken extractor' test never runs an extractor. No CI exists. make is not installed on this machine.
- **Root cause:** Metrics and gate written to the shape of the plan without a real corpus.
- **User impact:** No trustworthy accuracy number; regressions in values cannot be caught.
- **Suggested fix:** TP = label and value match; mismatches count as FP+FN; empty denominators fail; gate value exact-match; load the FN-010 corpus by split; add --strict to make eval; real cassette.
- **Effort:** M · **Depends on:** AUD-010

### AUD-015 [P1] EDGAR/ticker ingestion is unreachable: Phase 2 modules are unwired and the only input is PDF upload (Symptom E)

- **Severity:** P1 · **Category:** ingestion/unwired · **Tickets:** FN-020, FN-021, FN-022, FN-024, FN-025
- **Verification:** VERIFIED
- **Evidence:**
  - No production importer for ingestion/router_engine.py, extraction/shared_cache.py; ingestion/edgar/* and extraction/html/* are imported only by those and exhibit_99 (grep).
  - main.py:64-75 registers no new routes; the frontend calls only /upload/jobs, /companies, /review/*, /models/*, /footnote/*, /audit-trail/*, /jobs/* (grep of frontend/src); EdgarCompanyResult/EdgarFiling types in types/job.ts are unused.
  - A pre-existing (2026-08-29) ingestion/edgar_client.py backs /upload/edgar/search, /upload/edgar/filings/{cik}, POST /upload/edgar, which downloads and validates a PDF; modern primary documents are .htm, so it likely fails (HYPOTHESIS, sub-agent).
  - The ⌘K palette only filters existing local companies (CommandPalette.tsx:67-72); with none, typing 'GOOGL' shows only 'Upload a filing'. screens/command_palette_GOOGL_1280.png
  - The new client itself works: sub-agent live get_filings('GOOGL') returned 10-Q 0001652044-26-000071 (2026-06-30) and 10-K 0001652044-26-000018 (2025-12-31).
  - DECISIONS.md:12 'EDGAR-first ingestion replaces PDF-only ingestion' is false.
- **Root cause:** Phase 2 was built as libraries plus tests; no API route, job type or UI was added.
- **User impact:** The headline Phase 2 capability is absent; FN-031 (ticker flow) and FN-032 (SEC deep links) have nothing to run on.
- **Suggested fix:** Add POST /ingest (ticker+period | accession | upload) backed by IngestionRouter; route /upload/* through it; delete edgar_client.py; add ticker search to the palette; persist HTML sources and serve them.
- **Effort:** L · **Depends on:** AUD-016

### AUD-016 [P1] Phase 2 code would produce wrong numbers if wired: period collapse, dropped negatives, period-blind diff, cache key collisions

- **Severity:** P1 · **Category:** ingestion/latent-correctness · **Tickets:** FN-021, FN-022, FN-024, FN-025
- **Verification:** VERIFIED (sub-agent probes on real SEC data; two items re-checked by auditor)
- **Evidence:**
  - html/table_parser.py:171-185: three-month, six-month and TTM columns collapse to one period label; on Alphabet's real EX-99.1, Q2-2025 (28,196) and 6M-2025 (62,736) net income are both '2025' (sub-agent).
  - parse_numeric_cell('(5)') and '(1)' return None (auditor re-ran: (None, '(5)')); split '(50' + ')' cells also dropped.
  - exhibit_99/differ.py:59-69 keys on label only: 1,000 vs 1,050 -> has_discrepancies=False (sub-agent).
  - router_engine.py:97-98,127-129 cache key = accession or filename (auditor re-read): two users uploading different '10-Q.pdf' get the first user's records; target_metric not in key.
  - shared_cache.py:249 keys corrections by label: one correction rewrites every cell with that label, for other users after promotion; user ids stored in the shared layer (:86,201).
  - Router picks the 8-K by filed month (router_engine.py:158) and drops the submissions 'items' field; accession path fabricates cik='0000000000' (:161-170).
- **Root cause:** Idealized fixtures (e.g. 8-K given the 10-Q's period) let defects pass tests.
- **User impact:** Latent today; would become P0 wrong numbers and a cross-user data leak once wired.
- **Suggested fix:** Structured period (start, end, duration) per cell; strip footnote markers only when trailing a number; key diffs and caches by (canonical locator, period); hash upload bytes into the cache key; select 8-Ks with Item 2.02.
- **Effort:** M · **Depends on:** none

### AUD-017 [P1] Design showcase ships to production behind a header button, and mock/design content is hard-coded into production screens (Symptom C)

- **Severity:** P1 · **Category:** ui/product · **Tickets:** FN-061, FN-063, FN-066
- **Verification:** VERIFIED
- **Evidence:**
  - AppShell.tsx:153-176 renders a '/design' button whenever onNavigate is passed; App.tsx passes it on every screen; App.tsx:37-44 and :251-264 route /design with no import.meta.env.DEV gate (zero uses of import.meta.env in src).
  - Production build contains the page: dist bundle has 'Design System' x2, 'Exit Design' x1 (scratchpad/dist/assets/index-*.js). screens/design_1280.png, design_1920.png
  - Pack cards show fixed 'OUTPUT PREVIEW' strings with dash values ('5.25% Senior Notes 2028', 'Term Loan B (SOFR+3%)', '= Total Debt $2.5B'): UploadZone.tsx:16-38. screens/home_1280.png
  - Dropzone claims 'Auto-detects company and fiscal period' but nothing detects either (JobRecord.period never set; company from manual input).
  - Header badge 'Local · Single-User' (AppShell.tsx:149) re-introduces the footer text FN-060 #7 removed.
  - 'WCAG AA Contrast Audit' tab shows hard-coded PASS badges with wrong ratios (DesignPreviewPage.tsx:566-603: claims 14.2/4.8/13.5/5.6:1; computed 17.6/5.4/15.9/6.6:1) and omits the failing pair (white on dark accent #7B93FF = 2.82:1).
  - Ticket IDs in user-facing text: 'Design System 1.0 (FN-061 & FN-066)', 'Brand & Markers (FN-066)', 'DataTable Shell (FN-061)'.
- **Root cause:** Design work merged into the product shell instead of a dev-only route; placeholder copy left in.
- **User impact:** Prototype signals to paying users; false claims about auto-detection and accessibility.
- **Suggested fix:** Gate the route and button on import.meta.env.DEV (and lazy-load so it is tree-shaken); replace pack previews with real thumbnails or remove them; remove the auto-detect claim until implemented; compute contrast in a test instead of hard-coding.
- **Effort:** S · **Depends on:** none

### AUD-018 [P1] Every workbook deep link returns 404; SEC URL builders are malformed; the HTML source viewer is a stub with an unsafe sandbox

- **Severity:** P1 · **Category:** provenance/links · **Tickets:** FN-032, FN-023
- **Verification:** VERIFIED
- **Evidence:**
  - excel_export/provenance.py:167-179 builds {base_url}/api/review/{job}/source#page=N; GET http://127.0.0.1:8000/api/review/3906eb32.../source -> 404 (auditor curl). 3906eb32_model.xlsx Source_Inputs!A2 hyperlink = that URL. base_url defaults to http://localhost:8000.
  - Before ffb3bcf, value cells linked to /models/{job}/provenance/Source_Inputs/Bn, a real route (sub-agent) -> regression.
  - SEC fallbacks omit the CIK: provenance.py:46 and html/extractor.py:91 forms returned 404 live; provenance.py:166 form 301s to a CIK-less path (sub-agent). No ':~:text=' fragments, no signed URLs, no nightly link check.
  - ReviewPage.tsx:1547-1556 iframe src /filings/{job}/html -> 404 (auditor curl); switches on source_file extension, not locator.type; sandbox='allow-same-origin allow-scripts' defeats the sandbox if ever served same-origin (HYPOTHESIS, latent security).
  - tests/excel_export/test_generate_first.py:128 asserts the 404 URL.
- **Root cause:** Links written to a route that was never built; HtmlLocator lacks CIK.
- **User impact:** 'Every number clickable back to its source' does not work in the deliverable.
- **Suggested fix:** Link to an existing route (e.g. /review/{job}/pdf#page=N or a frontend deep link) with a configurable public base URL; add cik to HtmlLocator and build /Archives/edgar/data/{cik}/{acc}/{doc}#:~:text=...; drop allow-same-origin; link-check test.
- **Effort:** S · **Depends on:** AUD-015

### AUD-019 [P1] Review screen layout: header (incl. Export to Excel) can be hidden under the sticky app bar; nested scroll areas; cards push the list below the fold (Symptom B)

- **Severity:** P1 · **Category:** ui/layout · **Tickets:** FN-062, FN-061
- **Verification:** VERIFIED
- **Evidence:**
  - .review-layout is 100vh (800px) inside AppShell's 48px sticky bar, so the document is 848px tall; when the window keeps its scroll from the queue, the sticky bar covers the review header (screens/review_1280.png: no title, no Export button). Same on Audit Trail (screens/audit_trail_1280.png, header cut).
  - Nested scrollables at 1280: review-sidebar__scroll-container and review-viewer__stage, plus the page and the taxonomy panel (max-height 180, ReviewPage.tsx:1162-1171). FN-062 requires no nested scrolling.
  - Debt, Lease and Concentration cards render above the item list (ReviewPage.tsx:1253-1268); first item card at y=893 in an 800px viewport.
  - List is not virtualized (no @tanstack/react-virtual in package.json; ReviewPage maps all items; Amazon job = 954 cards).
  - Default selection is items[0] (a LOCKED item) while the default tab is Flagged, so the highlighted item is not in the visible list (diag selectedItem=null).
  - '← ← Back to Queue': ArrowLeft icon plus a literal '←' in the label (ReviewPage.tsx:635-636).
- **Root cause:** Full-height layout nested in a shell with its own sticky header; FN-062 list/virtualization not implemented.
- **User impact:** Primary action can be invisible; reviewers scroll through unrelated cards; large filings are slow.
- **Suggested fix:** Use calc(100vh - shell header) or make the shell a grid with the review filling the remaining row; reset scroll on navigation; move footnote cards into a tab; virtualize; select the first item of the active tab.
- **Effort:** M · **Depends on:** none

### AUD-020 [P1] PDF navigation is broken: Next/Prev do nothing while an item is selected; zoom is a CSS scale that blurs and clips; no scroll-to-highlight

- **Severity:** P1 · **Category:** viewer/navigation · **Tickets:** FN-062, FN-003
- **Verification:** VERIFIED (overlay mis-sizing under zoom is HYPOTHESIS)
- **Evidence:**
  - After clicking 'Next page' the toolbar still reads 'Page 1 of 3' (scratchpad/out_review.json): the draw effect renders selectedItem.page whenever an item is selected (ReviewPage.tsx:319) and one is always selected.
  - Zoom = transform: scale() on the canvas wrapper (ReviewPage.tsx:1588); at 130% the canvas spans x=283..1443 while the sidebar ends at 440, so the left of the page is under the sidebar and unreachable; the canvas is not re-rendered (blurry). screens/review_zoom130_1280.png
  - 'Fit width' just resets to 1.0 (ReviewPage.tsx:1530); no page thumbnails.
  - canvasSize comes from getBoundingClientRect (ReviewPage.tsx:329) inside the scaled wrapper, so a re-render while zoomed sizes the overlay with the scaled size (FN-003 clientWidth issue reintroduced; HYPOTHESIS on exact offset).
  - Selecting an item does not scroll the PDF stage to the highlight: Docling item highlight at y=1099 in a 900px viewport stayed off-screen.
- **Root cause:** Page state derived from selection; zoom implemented as CSS transform instead of re-rendering at scale.
- **User impact:** Reviewer cannot browse the filing or zoom usefully; FN-003 AC (correct highlight at two zoom levels) unproven in the UI.
- **Suggested fix:** Separate viewedPage from selectedItem.page; re-render the canvas at PDF_RENDER_SCALE*zoom and size the overlay from canvas.width/dpr; implement fit-width from container width; scrollIntoView the highlight.
- **Effort:** M · **Depends on:** AUD-001

### AUD-021 [P1] QoE endpoint returns meaningless numbers and crashes for jobs with a company

- **Severity:** P1 · **Category:** qoe/correctness · **Tickets:** FN-034, FN-033
- **Verification:** VERIFIED
- **Evidence:**
  - GET /drift/jobs/3906eb32.../qoe (auditor): 104 rows incl. Total assets; total_addbacks 5,948,647.45; 'Other' share 0.9999; reported_ebitda None; company 'Company', period 'Current'.
  - '(4,800)' and other parenthesized negatives become 0.0 (drift/router.py:276-281; qoe_diff.py:66-73); negative add-backs clipped by max(0.0, ...) (qoe_diff.py:126,131).
  - drift/router.py:303 job_repo.list_jobs(company_id=...) -> TypeError (signature list_jobs(self), ingestion/repository.py:131): 500 whenever the job has a company (mypy reports it too). drift/router.py:279 references ReviewItem.extracted_value (no such field).
  - Recurring flag never fires: router passes no history (:322-326). Code thresholds 10% / 2-of-N vs DECISIONS '15%' / '3 of last 4'.
  - Mutation M10 (all QoE values = 0.0) survived tests/drift (45 passed).
- **Root cause:** Endpoint feeds every review item to the diff and parses values naively.
- **User impact:** Not reachable from the UI today, but any consumer of the API gets wrong numbers.
- **Suggested fix:** Restrict to bridge add-back rows; use the shared numeric parser; fix list_jobs filtering; pass history periods; tests on real review items.
- **Effort:** M · **Depends on:** AUD-007

### AUD-022 [P1] FN-034 deliverables missing: no QoE workbook sheet, no web panel, no drift-data migration; graph drift remains the live engine

- **Severity:** P1 · **Category:** feature-missing · **Tickets:** FN-034
- **Verification:** VERIFIED
- **Evidence:**
  - grep -ri 'qoe' frontend/src -> no hits; no QoE sheet in excel_export (grep); no migration code; drift.db tables still graph tables with 0 rows (sub-agent).
  - drift/graph.py swaps nx.DiGraph for a hand-rolled SimpleDiGraph; docstring still says 'NetworkX-backed'. DriftFlagCard.tsx is imported nowhere.
  - networkx import removed (DONE) but still installed via torch and now unpinned (requirements.txt diff in ffb3bcf).
- **Root cause:** Only the pure diff function was built.
- **User impact:** Quality-of-earnings insight promised by the product thesis is absent.
- **Suggested fix:** Persist QoE rows per (company, period); add a QoE sheet with formulas and a review/company panel; migrate or drop graph drift.
- **Effort:** L · **Depends on:** AUD-021, AUD-023

### AUD-023 [P1] FN-033 add-back standardization is essentially missing (no Reported vs Standardized EBITDA, no toggles, no LLM step, no versioning, no eval metric)

- **Severity:** P1 · **Category:** feature-missing · **Tickets:** FN-033, FN-011
- **Verification:** VERIFIED (sub-agent; DECISIONS text checked by auditor)
- **Evidence:**
  - grep 'standardized|toggle|reported' in backend/app/excel_export -> nothing (sub-agent).
  - classify_addback_category (classification/taxonomy.py:727-832) is a substring keyword match with 7 categories / ~50 keywords, used only by the QoE code; DECISIONS.md claims '10 categories / 80+ aliases'. False positives: 'Acquisition of property and equipment' -> M&A.
  - eval/metrics.py:693-699 'category_accuracy' compares normalized labels and ignores the corpus standard_category.
- **Root cause:** Ticket reduced to a keyword function.
- **User impact:** No standardized EBITDA view, the product's differentiator.
- **Suggested fix:** Category on classified records (alias then constrained LLM), versioned enum, Reported/Standardized blocks with 1/0 include column and SUMPRODUCT, eval metric from standard_category.
- **Effort:** L · **Depends on:** AUD-014

### AUD-024 [P1] FN-067 workbook preview is not wired anywhere and renders built-in sample data

- **Severity:** P1 · **Category:** feature-unwired · **Tickets:** FN-067
- **Verification:** VERIFIED
- **Evidence:**
  - WorkbookPreview is imported only by its own test (grep of frontend/src); 'Ready for modeling' string absent from the production bundle (tree-shaken).
  - WorkbookPreview.tsx:47 defaults rows to DEFAULT_SAMPLE_ROWS from preview/sampleData.ts; no API provides a grid spec, so the AC 'renders from the same grid spec used by the exporter' cannot hold.
- **Root cause:** Component built in isolation.
- **User impact:** No payoff/preview moment; checks summary would be sample data.
- **Suggested fix:** Expose the generator's grid spec via the API and render it before export; remove sample defaults.
- **Effort:** M · **Depends on:** AUD-005

### AUD-025 [P1] Provenance fields were relaxed with fabricated defaults (page 1, whole-page box, 'unknown.pdf') and a swallowed exception

- **Severity:** P1 · **Category:** provenance/I3-I4 · **Tickets:** FN-023
- **Verification:** VERIFIED (latent: current job data all has real provenance)
- **Evidence:**
  - review/models.py:43-48 page default 1, bbox default {0,0,1000,1000}, source_file ''; review/models.py:67 and formula_engine/models.py:68 substitute 'unknown.pdf'; extraction/models.py:127-135 same; extraction/models.py:157 'except Exception: pass' (auditor re-read).
  - Sub-agent fabricate.py: a ReviewItem with no provenance validates as PdfLocator(page=1, full page, 'unknown.pdf').
- **Root cause:** Fields made optional to accommodate HtmlLocator instead of validating per locator type.
- **User impact:** A record that lost provenance would load silently and highlight 'page 1, whole page' (I4/I3).
- **Suggested fix:** Require exactly one locator variant; keep legacy fields required for PDF; raise or mark extraction_error instead of defaulting.
- **Effort:** M · **Depends on:** none

### AUD-026 [P1] Taxonomy mapping puts balance-sheet totals under wrong canonical lines in the workbook

- **Severity:** P1 · **Category:** classification · **Tickets:** FN-033
- **Verification:** VERIFIED (whether this predates the phases is HYPOTHESIS; p3 changed classification/taxonomy.py)
- **Evidence:**
  - 3906eb32_model.xlsx Source_Inputs: 'Total cash, cash equivalents, and marketable securities' (95,657 / 95,328) is labeled 'Accrued Expenses and Other Current Liabilities (p. 1)'.
- **Root cause:** Alias / leaf matching too loose (not traced in detail).
- **User impact:** Wrong line names in the model even when values are right.
- **Suggested fix:** Add a labeled mapping test set from real filings; require statement-type agreement before accepting an alias match.
- **Effort:** M · **Depends on:** AUD-010

### AUD-027 [P1] The test suite cannot catch the reported failures (frontend tests have no DOM; backend tests enshrine defects)

- **Severity:** P1 · **Category:** tests · **Tickets:** FN-003, FN-012, FN-062, FN-011
- **Verification:** VERIFIED
- **Evidence:**
  - frontend/vite.config.ts: vitest environment 'node'; component tests use renderToString; no jsdom, Testing Library or Playwright in package.json. Mutations M5 (viewer never draws) and M6 (mirrored highlight) survived 94/94.
  - Backend tests assert wrong behavior: Docling inversion (test_coordinate_normalizer.py, M3), 404 deep-link URL (test_generate_first.py:128), tautological flat_idx tests that recompute the formula inline (test_coordinate_normalizer.py:227-270), DummyRecord.record_id (test_tie_out_checker.py:162-183).
  - Survivors: M8 Checks status hard-coded PASS, M9 EDGAR burst x100, M10 QoE values all zero (docs/audit report section 6).
  - No test drives process_queued_job through the review/export path that produced the VERIFIED workbook; FN-062's required Playwright test does not exist.
- **Root cause:** Tests written to pass the implementation rather than the acceptance criteria; no browser-level tests.
- **User impact:** Green CI-equivalent despite a broken app.
- **Suggested fix:** Add jsdom + Testing Library for components and a Playwright smoke (open review, PDF renders, highlight inside value box, export); golden tests on real fixtures; delete tautological tests.
- **Effort:** M · **Depends on:** none

### AUD-028 [P1] I2 weakened: formula tree output depends on a mutable taxonomy file read at import time

- **Severity:** P1 · **Category:** invariant/I2 · **Tickets:** FN-002
- **Verification:** VERIFIED (code); determinism difference not demonstrated at runtime
- **Evidence:**
  - classification/taxonomy.py:33-46 loads SEED_MASTER_TAXONOMY from backend/data/taxonomy.json at module import; review actions append to that file (review/repository.py:470 taxonomy_repo.add_entry).
  - formula_engine/tree.py:15,560 uses SEED_MASTER_TAXONOMY when no master is passed, so identical inputs can yield different trees across restarts.
  - Boundary test forbids requests/httpx/sqlite3 etc. but not pathlib/json/open (tests/test_architecture_boundaries.py).
  - Pre-existing (same code at 202f154).
- **Root cause:** Global seed taxonomy built from disk state.
- **User impact:** Reproducibility claims (NFR1/I2) are not guaranteed.
- **Suggested fix:** Pass the taxonomy explicitly into build_formula_tree; make the seed a pure constant; extend the boundary test.
- **Effort:** S · **Depends on:** none

### AUD-029 [P2] FN-060 visible-defect list: debt table regressed, fiscal label and duplicate detection still wrong

- **Severity:** P2 · **Category:** ui/FN-060 · **Tickets:** FN-060
- **Verification:** VERIFIED
- **Evidence:**
  - #2 REGRESSED: debt table header clipped at 'MATURI' and 'Long-term debt' wraps to three lines in the COUPON/RATE column at 1280px (screens/review_1280.png, review_zoom130_1280.png).
  - #5 not fixed: GOOGL Q1 10-Q shows 'FY2025' (screens/home_1280.png). lib/fiscal_period.ts parses the filename with a regex instead of the document period; Amazon shows bare 'Q2'.
  - #6 not fixed: dedupe is filename+size on the client (App.tsx:130-141); server accepted a byte-identical 5th copy (POST /upload/jobs, job 8716f887); queue shows GOOGL x3 + 'goog trial file.pdf' (same bytes). Client skip is reported as '1 file was rejected' (screens/home_staged_light_1280.png).
  - #7 partial: footer replaced by 'Footnote © 2026' but 'Local · Single-User' badge added to the header.
  - #1, #3, #4, #8 verified OK (see Verified-OK).
- **Root cause:** Fixes applied to symptoms (filename regex) rather than data; later redesign regressed the table.
- **User impact:** Prototype-looking defects remain.
- **Suggested fix:** Use DataTable truncation/tooltip with min widths; derive period from the document (cover page or XBRL dei); hash file contents server-side and block duplicates.
- **Effort:** S · **Depends on:** none

### AUD-030 [P2] FN-061 incomplete: missing primitives, fonts not self-hosted, hard-coded colors, dark-first, AA failures

- **Severity:** P2 · **Category:** design-system · **Tickets:** FN-061, FN-065
- **Verification:** VERIFIED
- **Evidence:**
  - components/ui has Badge, Button, Card, DataTable, Input, Progress, Select, Skeleton, StatusDot, Tabs, Tooltip; missing IconButton, Popover, DropdownMenu, Toast.
  - No @font-face or font files (grep); computed fonts fall back to Arial/system serif; document.fonts empty on home.
  - Hard-coded colors in new code: ReviewPage.tsx 15 occurrences (e.g. #f59e0b, #1e293b, #0f172a, #fff in the taxonomy panel), UploadZone.tsx 9, WorkbookPreview.tsx 6, JobList.tsx 5. No lint/grep check exists.
  - Default theme is dark (AppShell.tsx:29) though Appendix A is light-first; a manual theme toggle (FN-065, Phase 4) was added early.
  - AA: white on dark-theme accent #7B93FF = 2.82:1 (primary buttons, e.g. 'Lookup', 'Export to Excel' in dark); light-theme status text warn #B7791F = 3.43:1 and ok #1F8A5B = 4.09:1 on #FAF8F4 (computed).
  - /design shows only the active theme, not light and dark side by side.
- **Root cause:** Partial implementation; no automated token/contrast checks.
- **User impact:** Inconsistent visuals; accessibility below the plan's AA bar.
- **Suggested fix:** Add the missing primitives (or Radix), self-host fonts, add a stylelint/grep rule for raw colors, use dark text on the dark accent, darken warn/ok text tokens, default to light.
- **Effort:** M · **Depends on:** none

### AUD-031 [P2] FN-063 home/queue redesign partly fake: 'Request this' is local-only, stepper is not event-driven, metadata not auto-detected

- **Severity:** P2 · **Category:** ui/FN-063 · **Tickets:** FN-063
- **Verification:** VERIFIED
- **Evidence:**
  - 'Request this' only adds to local state (UploadZone.tsx:65-68); no backend call.
  - Stepper derives from coarse status (JobList.tsx:29-36): 'extracting' shows step 2 'Classifying'; 'Checks' is never current; no job events exist.
  - 'Assign to Company (Optional)' field still present (App.tsx:418-422; screens/home_1280.png); no company/period detection.
  - Actions are 'Excel (.xlsx)' + 'Review' + overflow, not a single primary 'Open workbook'.
  - Dropzone is still a full-width box with 'Browse files' (not a slim bar).
- **Root cause:** Visual redesign without the backend pieces it needs.
- **User impact:** Controls that appear to work but do nothing.
- **Suggested fix:** POST interest to the backend; emit stage events from job_runner; implement detection or remove the claim; consolidate actions.
- **Effort:** M · **Depends on:** AUD-017

### AUD-032 [P2] FN-062 partial: custom mouse-only resizer, no Playwright/Lighthouse, 'Accept all' missing, wrong success count, stale download

- **Severity:** P2 · **Category:** ui/FN-062 · **Tickets:** FN-062
- **Verification:** VERIFIED
- **Evidence:**
  - No react-resizable-panels; resizer is a div with onMouseDown only (ReviewPage.tsx:604-622, 1470-1474): not keyboard accessible.
  - Taxonomy panel offers 'Select All' + 'Batch Confirm Selected', not a bulk 'Accept all'; panel uses hard-coded dark colors in light theme.
  - After Export, banner says 'Model generated with {lockedCount} line items' (ReviewPage.tsx:543-546) though unreviewed items are now included.
  - No Playwright test, no Lighthouse run, no undo for keyboard actions.
- **Root cause:** Redesign implemented with hand-rolled pieces; AC tooling never added.
- **User impact:** Accessibility and correctness gaps on the core screen.
- **Suggested fix:** Use react-resizable-panels; add 'Accept all'; fix banner count; add the Playwright + axe tests the ticket specifies.
- **Effort:** M · **Depends on:** AUD-019, AUD-027

### AUD-033 [P2] Definition of done not met: mypy strict fails (20 errors), ruff fails, a non-strict backend/mypy.ini was added, and there is no CI

- **Severity:** P2 · **Category:** tooling/DoD · **Tickets:** FN-002, FN-011, FN-023
- **Verification:** VERIFIED
- **Evidence:**
  - `mypy backend/app` (root strict config): 20 errors in 7 files, incl. real bugs drift/router.py:279 (ReviewItem.extracted_value) and :303 (list_jobs(company_id=)).
  - backend/mypy.ini (added in 873f47a) is non-strict; `cd backend && mypy app` (as ARCHITECTURE.md instructs) uses it and still reports 19 errors.
  - `ruff check backend`: 9 errors; `ruff check eval`: 15 (incl. try/except/pass at eval/metrics.py:781); `ruff format --check backend`: 62 files would be reformatted.
  - No .github or other CI; import-linter not installed; the boundary test is the only enforcement; Makefile 'eval' lacks --strict.
  - Frontend: eslint 0 errors, tsc -b clean, vite build OK (warning: 695 kB main chunk).
- **Root cause:** Phases committed without running the declared gates.
- **User impact:** Type errors that are real runtime bugs shipped; no automated guard.
- **Suggested fix:** Delete backend/mypy.ini; fix the 20 errors; add a CI workflow running ruff, mypy --strict, pytest, eslint, tsc, vitest, build and make eval --strict.
- **Effort:** M · **Depends on:** none

### AUD-034 [P2] API base and link base URLs are hard-coded to localhost:8000

- **Severity:** P2 · **Category:** config · **Tickets:** FN-032, FN-061
- **Verification:** VERIFIED
- **Evidence:**
  - frontend/src/App.tsx:24 const API_BASE = 'http://localhost:8000'; defaults in CompanySelector.tsx:13, JobList.tsx:179, ModelViewer.tsx:32, CompanyMultiYearCard.tsx:13; 4 occurrences in the production bundle.
  - excel_export/provenance.py base_url default http://localhost:8000 written into every workbook hyperlink.
- **Root cause:** No environment configuration.
- **User impact:** Hosted deployment (DECISIONS: hosted SaaS) impossible without code edits; workbook links point at the user's own machine.
- **Suggested fix:** VITE_API_BASE + backend PUBLIC_BASE_URL settings.
- **Effort:** S · **Depends on:** none

### AUD-035 [P2] A job stuck in 'extracting' never recovers and makes the UI poll forever

- **Severity:** P2 · **Category:** jobs/I3 · **Tickets:** FN-063
- **Verification:** VERIFIED
- **Evidence:**
  - jobs.json: msft-10q.pdf (edcedfa2) status 'extracting' with no results; frontend polls /upload/jobs and /companies every 3 s while any job is extracting (App.tsx:106-125); observed continuous polling in the server log.
- **Root cause:** BackgroundTasks in-process; no startup recovery or timeout.
- **User impact:** Zombie row with an animated stepper; constant background traffic.
- **Suggested fix:** On startup mark orphaned 'extracting' jobs failed with a reason; add a timeout; stop polling after N minutes.
- **Effort:** S · **Depends on:** none

### AUD-036 [P2] Capital-structure workbook writes missing amounts as 0.0 and rates as text (pre-existing)

- **Severity:** P2 · **Category:** excel/I3-I5 · **Tickets:** FN-064
- **Verification:** VERIFIED (sub-agent code reading)
- **Evidence:**
  - debt_schedule_generator.py:188-190 missing principal -> 0.0; :323-327 missing lease amounts -> 0.0; :171-186 rates/spreads/years as text (sub-agent). No Review sheet, DRAFT header, Checks or units header.
- **Root cause:** Pack generator predates FN-030 conventions.
- **User impact:** Silent zeros in the debt workbook.
- **Suggested fix:** Blank + flag for missing values; numbers as numbers with number formats; reuse FN-030 sheet scaffolding.
- **Effort:** M · **Depends on:** AUD-004

### AUD-037 [P2] FN-023 incomplete: no migration script, no canonical serializer, no text-quote selector; downstream call sites not migrated

- **Severity:** P2 · **Category:** provenance/FN-023 · **Tickets:** FN-023
- **Verification:** VERIFIED (sub-agent)
- **Evidence:**
  - No migration script anywhere (grep 'migrat'); no canonical serializer; W3C export has XPath/Fragment but no TextQuoteSelector (sub-agent).
  - audit_trail/resolver.py:220 calls make_review_id without the locator; audit_report/compiler.py:294-303 dereferences an Optional selector (latent).
  - Frontend mirrors the union in types/review.ts but no component reads `locator`.
  - Verified OK: old jobs load (1,370 items) and PDF review IDs are unchanged vs 202f154.
- **Root cause:** Union added; surrounding migration work skipped.
- **User impact:** Latent until HTML sources exist.
- **Suggested fix:** canonical_locator_key(); one-shot migration; pass locator through audit trail/report; TextQuoteSelector.
- **Effort:** S · **Depends on:** AUD-025

### AUD-038 [P2] EDGAR client (unwired) bursts to 20 req/s, limiter is per instance, User-Agent contact is a placeholder, no ticker-change/amendment logic

- **Severity:** P2 · **Category:** ingestion/compliance · **Tickets:** FN-020
- **Verification:** VERIFIED (UA ownership is HYPOTHESIS)
- **Evidence:**
  - rate_limiter.py:21,29 capacity 10 starting full: 20 acquisitions in the first second; separate limiter per client (sub-agent). Mutation M9 (capacity 1000) survived tests/ingestion.
  - client.py:38-40 default UA 'Footnote Research analyst@footnoteresearch.com' copied from the old client (HYPOTHESIS: not a mailbox the user owns).
  - resolve_cik('FB') raises not found; only filings.recent is read; no amendment preference (sub-agent, live).
  - Two EDGAR clients with same-named exception classes (ingestion/edgar_client.py and ingestion/edgar/client.py).
- **Root cause:** Client written without a process-wide limiter or contact configuration.
- **User impact:** Risk of SEC blocking once wired.
- **Suggested fix:** Module-level limiter at <=10 req/s with small burst; require SEC_USER_AGENT config; delete the old client.
- **Effort:** S · **Depends on:** AUD-015

### AUD-039 [P3] FN-066 partial: favicon is still the Vite default; SourceChip absent from the debt card

- **Severity:** P3 · **Category:** brand · **Tickets:** FN-066
- **Verification:** VERIFIED
- **Evidence:**
  - frontend/public/favicon.svg unchanged since scaffold commit 8ee5b49 (purple Vite bolt).
  - SourceChip used only in ReviewPage.tsx and DesignPreviewPage.tsx; AC requires review list AND debt card.
- **Root cause:** Incomplete ticket.
- **User impact:** Minor branding gap.
- **Suggested fix:** Ship the footnote-marker favicon; add SourceChip to DataTable numeric cells with provenance.
- **Effort:** S · **Depends on:** none

### AUD-040 [P3] Docs and trackers contradict the code

- **Severity:** P3 · **Category:** docs · **Tickets:** FN-002, FN-000
- **Verification:** VERIFIED
- **Evidence:**
  - Plan section 8 lists FN-030..FN-067 as 'todo' while headings and section 9 say [DONE].
  - README still describes local-first, PDF-only upload, NetworkX, 'eval FROZEN, no corpus', narrative components and the 6-tab generator as an opt-in (README.md:5-8, 92, 212-229, 244).
  - docs/CONSTITUTION.md:48 says narrative endpoints exist; :60 says multi_statement_generator is retained.
  - ARCHITECTURE.md: tells you to run mypy from backend/ (non-strict config), eval via pytest test_runner.py, '480+ tests' (actual 566).
  - DECISIONS.md false claims: EDGAR-first replaces PDF-only; 10 categories/80+ aliases; sanitized HTML viewer with XPath highlight; 15% / 3-of-4 thresholds; unreviewed cells yellow on auto path.
  - docs/AUDIT.md (FN-000): test counts approximate ('~500', not run); lists POST /review/{id}/batch-accept, which does not exist (route is confirm-batch).
- **Root cause:** Docs written to the plan, not the code.
- **User impact:** Misleads the next developer and reviewers.
- **Suggested fix:** Regenerate README/ARCHITECTURE from this audit; correct DECISIONS; fix the tracker.
- **Effort:** S · **Depends on:** none

### AUD-041 [P3] FN-001 leftovers from the deleted 6-tab generator and narrative module

- **Severity:** P3 · **Category:** dead-code · **Tickets:** FN-001
- **Verification:** VERIFIED
- **Evidence:**
  - formula_engine/models.py:293 ComprehensiveModelTree and tree.py:17 import (6-tab artifact); excel_export/repository.py:43 still looks for '{job}_multi_statement.xlsx'; multi_year_generator.py:2 'DEPRECATED: Use multi_statement_generator.py instead'.
  - Orphan components: DriftFlagCard.tsx and ModelViewer.tsx imported nowhere; empty frontend/src/components/narrative directory on disk (untracked).
  - No dangling imports, routes or flags found: ENABLE_NARRATIVE and narrative routes removed; tag archive/pre-cleanup exists.
- **Root cause:** Deletion stopped at the obvious entry points.
- **User impact:** Confusing dead code.
- **Suggested fix:** Delete the leftovers.
- **Effort:** S · **Depends on:** none

### AUD-042 [P3] Test suite writes into the repository and the eval fetcher caches a fake filing

- **Severity:** P3 · **Category:** tests/hygiene · **Tickets:** FN-010
- **Verification:** VERIFIED
- **Evidence:**
  - test_fetch_filing_by_accession (backend/tests/eval/test_corpus_loader.py:277-287) ignores tmp_path and accepts mock output; eval/.cache/0001018724-23-000014_10-K.html is a 165-byte 'MOCK SEC EDGAR FILING' created 2026-10-01 (gitignored).
  - eval/fetch_filings.py:72-84 writes the mock on any error and later returns it as a real cache hit; --mock is store_true with default=True (:121).
- **Root cause:** Mock fallback in production code.
- **User impact:** Poisoned local cache; tests mutate the working tree.
- **Suggested fix:** Use tmp_path; remove the mock fallback; fix the URL.
- **Effort:** S · **Depends on:** AUD-010

### AUD-043 [P3] Process deviations: four phase-sized commits instead of per-ticket branches; Phase 4 work (FN-065) started early

- **Severity:** P3 · **Category:** process/scope · **Tickets:** FN-065, FN-000
- **Verification:** VERIFIED
- **Evidence:**
  - git log: 1dd6560, df0334f, 873f47a, ffb3bcf, all on main within ~8 hours (2026-10-01 15:48-23:46 IST); plan protocol requires fn-<id> branches and 'FN-<id>:' commit messages.
  - Dark theme as default plus a manual light/dark toggle (AppShell.tsx:24-41) is FN-065 scope (Phase 4). No other Phase 4/5 ticket started (no auth, Postgres, billing, LLM abstraction).
  - FN-000 required 'no source changes' but shares commit 1dd6560 with source changes.
- **Root cause:** Agent batched work per phase.
- **User impact:** Hard to review, bisect or revert individual tickets.
- **Suggested fix:** Fix batches as small per-ticket commits (see section 9).
- **Effort:** S · **Depends on:** none

### AUD-044 [P3] Dependency hygiene: networkx now an unpinned transitive dependency; unused prettier devDependency

- **Severity:** P3 · **Category:** dependencies · **Tickets:** FN-001, FN-034
- **Verification:** VERIFIED
- **Evidence:**
  - ffb3bcf removed 'networkx==3.6.1' from requirements.txt; torch still requires it (pip show torch), so it is installed unpinned.
  - prettier in package.json devDependencies with no config or script.
  - lucide-react added in 1dd6560 (used). No secrets in history (git log -p: 0 'gsk_' keys); .env is untracked.
- **Root cause:** Partial cleanup.
- **User impact:** Minor reproducibility risk.
- **Suggested fix:** Pin via a constraints/lock file; add a format script or drop prettier.
- **Effort:** S · **Depends on:** none

---

## 8. Verified-OK (checked and found correct; the fix phase should not touch these)

**Build and tests**
- Backend suite: 566 tests pass, with no skipped or xfail tests.
- Frontend: eslint, `tsc -b`, vitest and the production build all pass.

**FN-001 deletions**
- No dangling imports, routes or flags for narrative or the 6-tab generator.
- Tag `archive/pre-cleanup` exists.
- `cash_conversion` stays in the backend enum and shows as "Request this" in the UI.

**Repo hygiene**
- README links resolve.
- No secrets in git history (0 `gsk_` keys).
- `.env` is gitignored and untracked.
- CORS is limited to the `ALLOWED_ORIGINS` env list (default localhost:5173/5174).

**PDF serving and PyMuPDF highlights**
- `GET /review/{id}/pdf` returns the right bytes, content type and CORS headers.
- The pdf.js worker is bundled locally.
- PyMuPDF-path highlight boxes are correct: 104/104 and 954/954 value hits. That code path, including the FN-003 `flat_idx` change, is not the problem.

**Review status and IDs**
- Status derivation (`review/repository.py:521-535`) is unchanged since before the phases and behaves as designed. Over-flagging comes from the scorer's inputs (AUD-003).
- Review-item IDs are unchanged by FN-023: 0 mismatches vs `202f154` for 1,370 items (sub-agent).
- All existing job data loads under the new models.

**Locator and EDGAR**
- `Locator` is a real pydantic discriminated union and round-trips through JSON.
- `EdgarClient.get_filings("GOOGL")` returns the correct latest 10-Q (2026-06-30) and 10-K (2025-12-31) live, with correct `primary_url`.
- Ticker to CIK works, including share classes and BRK.B.
- CIK zero-padding works.
- The accession cache works.
- The circuit breaker behaves as documented (sub-agent).

**Workbook (generate path)**
- Source_Inputs values are written as numbers, apart from the unparsed text listed in AUD-008.
- Reconciliation derived cells are live formulas, and inputs are not overwritten.
- On the `/generate` path, needs_review cells are yellow with a comment and listed on the Review sheet.
- Manual-required cells are blank and red at generator level.
- The count gate is gone, and "Export to Excel" is never disabled.

**Pure modules and dependencies**
- `tie_out_checker.run_tie_out_checks` and `qoe_diff.diff_qoe_components` are pure and deterministic.
- No `import networkx` remains.

**Review UI**
- Stacked progress bar and counts are correct: "104 items, 34 verified, 70 need review".
- ●◐○ shape+colour status visuals are present.
- J/K keyboard navigation moves the selection.
- The details popover and split button exist.

**FN-060 items fixed**
- #1: no "?" glyphs; Lucide icons are used.
- #3: the company input is themed in both themes.
- #4: queue buttons don't wrap at 1280 or 1920.
- #8: the "Assign to Company" label uses the ink colour.

**Layout and accessibility**
- No horizontal page scroll at 1280 or 1920 on home, design or review.
- The debt maturity chart has a screen-reader text alternative.
- `prefers-reduced-motion` is honoured in `tokens.css:284`.

**Scale detection library**
- `detect_scale_from_caption` handles the standard "in thousands/millions[, except per share]" captions. The problem is that it isn't wired (AUD-006).

---

## 9. Recommended fix order

Each batch can be implemented and verified on its own. Every batch's checks should become automated tests.

| Batch | Goal | Findings | Verify by |
|---|---|---|---|
| 1. Quick, user-visible stabilisers | Unblock daily use | AUD-001 (render race), AUD-003 part 1 (fail fast or banner when Docling is missing; start from `.venv`), AUD-017 (gate `/design`, remove mock copy), AUD-007 (explicit "reconciliation not found"), AUD-035 (zombie jobs) | Re-run `scratchpad/scen_open.py` and `scen_race.py`: 0/20 failures. A job without Docling shows a reason. The production bundle has no "Design System". The GOOGL 10-Q produces "not found" instead of a bridge. |
| 2. Guard rails | Make later batches verifiable | AUD-033 (CI; delete `backend/mypy.ini`; fix the 20 mypy errors and ruff), AUD-027 (jsdom + Testing Library, Playwright smoke, real Docling golden fixture), AUD-034 (env-configured base URLs) | CI green. The new tests fail on the known bugs before their fixes, i.e. M3/M5/M6/M8 are killed. |
| 3. Provenance and viewer correctness | Every highlight and link lands on the number | AUD-002, AUD-020, AUD-019, AUD-018, AUD-025, AUD-037 | `scratchpad/bbox_probe.py` 100% on Docling and PyMuPDF jobs. Highlight inside the value box at zoom 1.0 and 1.5 in Playwright. Workbook link check returns 200. |
| 4. Extraction trust and invariants | Correct flag rate, no leakage | AUD-003 part 2 (PyMuPDF headers, scorer), AUD-011 (I1 scrub), AUD-012 (I6), AUD-028 (I2), AUD-026 (taxonomy mapping) | GOOGL flagged under 10% on both parsers. No digits in Groq payloads (test). Log-redaction test. |
| 5. Workbook honesty | The deliverable never overstates | AUD-004, AUD-005, AUD-006, AUD-008, AUD-013, AUD-036 | openpyxl assertions: DRAFT whenever an item is unverified; Checks FAIL on a non-footing fixture; units from the caption; every excluded item listed; debt total ties to the balance sheet. Recalculation via LibreOffice or the `formulas` library. |
| 6. Eval truth | A real accuracy number | AUD-010, AUD-014, AUD-042 | Corpus validator cross-checks accessions against EDGAR. `make eval --strict` fails when values are perturbed. |
| 7. EDGAR wiring (actually do Phase 2) | Ticker to workbook | AUD-016 first, then AUD-015, AUD-038 | End-to-end on 3 real filings (10-Q, 10-K, 8-K EX-99.1): correct periods, negatives, "not found" status, ≤10 req/s. |
| 8. Phase 3 features on real data | Multi-period, standardization, QoE, preview | AUD-009, AUD-023, AUD-021, AUD-022, AUD-024 | Fixtures with a restatement and a 52/53-week year; LTM over 4 consecutive quarters; toggles recompute; QoE on bridge rows only. |
| 9. UI and design-system polish | FN-060/061/062/063/066 leftovers | AUD-029, AUD-030, AUD-031, AUD-032, AUD-039 | Screenshot diff at 1280 and 1920 in both themes; axe zero serious violations. |
| 10. Docs and cleanup | Truthful docs | AUD-040, AUD-041, AUD-043, AUD-044 | README, ARCHITECTURE and DECISIONS reviewed against this audit; tracker updated. |

---

## 10. Open questions for the user (decisions only you can make)

1. **How do you start the backend?** If it's `uvicorn app.main:app` without activating `.venv`, that explains symptom D. When Docling is missing, should the app refuse to start, or run on PyMuPDF with a visible "degraded" banner?
2. **Filings without an Adjusted EBITDA reconciliation** (e.g. GOOGL 10-Q): should the job end with "not found", or still produce a GAAP-statement extract? If an extract, in what form? It must not be labelled Adjusted EBITDA.
3. **The fabricated benchmark corpus:** delete it now, or keep it quarantined as synthetic test data? Who labels the real corpus, and how much effort do you want to spend on it?
4. **Phase 2:**
   - Wire the new EDGAR client and router.
   - Retire `edgar_client.py` and the PDF-only `POST /upload/edgar`, which is a breaking change to that route.
   - Is a ticker flow the next priority, ahead of Phase 3 polish?
5. **Auto-generated workbook at job completion:** keep it (always DRAFT, same inclusion rules as Export), or generate only on explicit export?
6. **Footnote cards (debt/lease/concentration):** show only for `capital_structure` jobs?
7. **Theme and design route:**
   - Default to light per Appendix A, or keep dark?
   - Keep the early FN-065 theme toggle?
   - Should `/design` be dev-only, or removed from the build entirely?
8. **Process:** fix forward from this audit in the batches above, or redo Phases 0-3 ticket by ticket on `fn-<id>` branches as the plan's protocol requires?
9. **Hosting assumptions:** what public base URL should workbook deep links use (hosted app vs localhost)? Do PDF links need signed URLs now, or only after FN-040/041?
