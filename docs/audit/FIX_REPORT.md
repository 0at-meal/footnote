# Fix report: audit findings, batches 1-3

Branch `fix/audit-phases-0-3` (from `audit/phases-0-3` @ a0b2a14). Tags: `fix-batch-1`, `fix-batch-2`, `fix-batch-3`.
Every status below links to evidence (commands run and their output) in [FIX_PROGRESS.md](FIX_PROGRESS.md). Nothing is marked FIXED without a test that failed before the fix, passed after it, and failed again when only the fix was reverted (P0/P1).

## Summary

| Severity | In batches 1-3 | FIXED | PARTIAL | BLOCKED | Not in scope this run |
|---|---|---|---|---|---|
| P0 | AUD-001, 002, 003 (part 1), 007 | 3 (001, 002, 007) | 1 (003: part 2 is batch 4) | 0 | 9 |
| P1 | AUD-017, 018, 019, 020, 025, 027 | 5 (017, 018, 019, 020, 025) | 1 (027) | 0 | 9 |
| P2 | AUD-033, 034, 035, 037 | 4 | 0 | 0 | 6 |
| P3 | none | 0 | 0 | 0 | 6 |

Also fixed: an eval-metric defect that the AUD-002 fix exposed (accuracy could exceed 100%), commit a7ae48d.

Gates at the batch 3 checkpoint:

- **Backend:** ruff `All checks passed!`; mypy `--strict` (root `mypy.ini`) `no issues found in 96 source files`; pytest `605 passed`.
- **Frontend:** eslint clean; `tsc -b` and e2e `tsc` clean; vitest `31 files / 126 tests`; build OK; `verify:bundle` OK; Playwright `10 passed`.
- **CI:** the workflow is written but has not been run on GitHub from here.

## Per finding

| Finding | Sev | Status | Evidence (FIX_PROGRESS.md) | Notes / risks |
|---|---|---|---|---|
| AUD-001 pdf.js render race | P0 | FIXED | AUD-001: jsdom race tests red→green→red; Playwright 0/20 natural, 0/20 forced (pre-fix 10/20 forced failures) | Re-checked at every later checkpoint (0/20, 0/20). |
| AUD-003 part 1 Docling fallback (D1) | P0 | PARTIAL | AUD-003: server refuses to start without Docling; `ALLOW_PYMUPDF_FALLBACK=1` → degraded /health, banner, job stamp; venv launcher | Part 2 (PyMuPDF header quality, scorer) is batch 4. |
| AUD-007 no reconciliation → not_found (D2) | P0 | FIXED | AUD-007: synthetic Docling + PyMuPDF pipeline tests; GOOGL 10-Q copy ends `not_found` under both parsers | |
| AUD-002 mirrored Docling highlights | P0 | FIXED | AUD-002: real-Docling golden test (synthetic PDF) red→green→red; real filings: GOOGL Docling 103/103, PyMuPDF 104/104; Amazon Docling 475/475, PyMuPDF 954/954 (audit baseline: 3 hit / 100 miss) | Golden fixture from a public filing BLOCKED (needs `SEC_USER_AGENT`). |
| AUD-017 design showcase in production (D7) | P1 | FIXED | AUD-017: production-surface tests; bundle check | |
| AUD-020 viewer navigation / zoom | P1 | FIXED | AUD-020: unit 4 red→green; Playwright highlights inside value box at 100% and 150% for both parsers, Next/Prev draw other pages, zoomed page reachable | Page thumbnails not added. |
| AUD-019 review layout | P1 | FIXED | AUD-019: unit 6 red→green→red; Playwright page scrolled by 48px before, 0 after; list above the fold; virtualized list | Virtualization proven by mounted-card count, not a browser timing on a 954-item job. Footnote cards are in a tab; gating them to capital_structure jobs (D6) is AUD-013, batch 5. |
| AUD-018 workbook links | P1 | FIXED | AUD-018: every local link in generated non_gaap_bridge and capital_structure workbooks returns 200 (was 404); CIK-qualified sec.gov URLs; HTML viewer stub removed | Live sec.gov 200 check BLOCKED (`SEC_USER_AGENT`); URLs are shape-checked. |
| AUD-025 fabricated provenance defaults | P1 | FIXED | AUD-025: 13 tests red (7)→green→red; copy of user data loads 1,370 review + 1,370 extracted records with 0 errors, before and after | |
| AUD-027 test infrastructure | P1 | PARTIAL | AUD-027: jsdom/Testing Library, Playwright smoke + race + highlight + layout specs, mutations tool | Public-filing Docling golden fixture BLOCKED (`SEC_USER_AGENT`); Lighthouse/axe are batch 9. |
| AUD-033 DoD tooling | P2 | FIXED | AUD-033: mypy 20 → 0, ruff 24 → 0, CI workflow | CI not executed here; expected red steps: `eval --strict` (batch 6) and 6 taxonomy tests that need a versioned seed taxonomy. |
| AUD-034 base URLs | P2 | FIXED | AUD-034: `VITE_API_BASE`, `PUBLIC_BASE_URL` tests red→green→red | |
| AUD-035 zombie jobs | P2 | FIXED | AUD-035: interrupted/timed-out jobs fail with a reason; polling cap | |
| AUD-037 FN-023 follow-through | P2 | FIXED | AUD-037: canonical locator key; locator + TextQuoteSelector in provenance; audit trail matches HTML leaves; report guard; migration tool (dry run default) verified on a copy (1,248 records, IDs unchanged) | Migration **not** run on `backend/data`: user decision. |
| eval accuracy > 100% (exposed by AUD-002) | n/a | FIXED | AUD-018 section: red `input_value=200.0` → green → red; cause proven by re-applying the mirrored-box defect | Corpus itself is still fabricated (AUD-010, batch 6). |

## Mutation scoreboard (tools/verify/mutations.py --e2e)

Run at the batch 3 checkpoint. Each mutation was reverted by the tool; `tracked changes after run: (none)`.

| Id | Mutation | Result | Killed by | Note |
|---|---|---|---|---|
| M1 | Auto-accept threshold 0.95 → 0.85 | KILLED | test_confidence, test_flagger | |
| M2 | needs_review items silently locked | KILLED | test_job_runner, job_runner_integration | |
| M3 | Invert every Docling box regardless of origin (AUD-002 defect; redefined) | KILLED | test_coordinate_normalizer, test_docling_golden_bbox | The audit's M3 (remove the inversion) is now the fix itself, so it was redefined to re-introduce the defect. |
| M4 | Workbook header always VERIFIED | KILLED | tests/excel_export | |
| M5 | Review PDF page never drawn | KILLED | vitest | |
| M6 | Review highlight vertically mirrored | KILLED | review-smoke + review-highlight (Playwright) | Unit tests alone do not catch it; the browser tests do. |
| M7 | Auto workbook path receives no inputs | KILLED | job_runner_integration, excel_export | |
| M8 | Checks sheet footing hard-coded PASS | SURVIVED | none | Fix is batch 5 (AUD-005). |
| M9 | EDGAR token bucket capacity 10 → 1000 | SURVIVED | none | Fix is batch 7 (AUD-016). |
| M10 | QoE value parser returns 0.0 | SURVIVED | none | Fix is batch 8 (AUD-022). |

Score: 7 of 10 killed. The 3 survivors belong to later batches.

## Blocked items

- **`SEC_USER_AGENT` is not set.** Blocked until it is:
  - the Docling golden fixture cut from a public filing (AUD-002 / AUD-027);
  - a live 200 check of sec.gov workbook links (AUD-018);
  - everything in batches 6-7 that touches EDGAR.

## What is needed from you

1. **Set `SEC_USER_AGENT="Your Name your@email"`** in your environment or `.env`. This unblocks the items above and batches 6-7.
2. **Seed taxonomy:**
   - `backend/data/taxonomy.json` is gitignored, so 6 taxonomy tests pass only on this machine (the test conftest copies the local file).
   - Decide whether a curated seed taxonomy, with no filing text in it, may be committed, e.g. under `backend/app/classification/`.
3. **Optional locator migration:** to give your 3 pre-FN-023 jobs stored locators, run
   `.venv/Scripts/python.exe tools/migrate_locators.py --data-dir backend/data` (dry run), then add `--apply`.
   It backs up every changed file and verifies that IDs are unchanged.
4. **Run CI once on GitHub** (push the branch) to confirm the workflow. Two red steps are expected until batches 4-6.

## Risks and discoveries (details in FIX_PROGRESS.md, "Out-of-scope discoveries")

- **HIGH, not fixed (batch 5): Debt_Tranches value cells hold a URL string instead of the number (I5).**
  - `write_url(..., string=None)` overwrites `write_number` in `debt_schedule_generator.py`.
  - Confirmed with an xlsxwriter probe.
- **Router engine invents a placeholder filing** (`cik="0000000000"`, fixed `filed_at`) for accession lookups. Not wired yet (batch 7).
- **Some older tests hand-type real filer identifiers.** One is part of the Verified-OK round-trip test and is left untouched.
- **The `flat_idx` PyMuPDF branch is dead code** (batch 10 cleanup).
- **A tautological ReviewPage filter test remains.** Its behaviour is now covered by `ReviewPage.layout.test.tsx`.
- **Environment:** local Playwright uses the installed Chrome, because the bundled-browser download failed here. CI installs the bundled browser.
