# Footnote Enhancements: Agent Execution Plan

Audience: a coding agent with full read/write access to this repository.
Scope: make Footnote credible and tempting to bankers and analysts at ~$100/month, covering product, accuracy, SaaS readiness and design.

---

## 0. Agent protocol (read first)

1. **This plan was written without reading the source.** It is based on the README, `docs/plan.md`, `docs/spec.md` and three UI screenshots. Every statement about current code is a hypothesis. Before editing, verify it. Items marked **VERIFY** are the riskiest.
2. **If an assumption is false, stop and adapt.** Write a short note under "Blockers and deviations" in section 9, then propose the smallest change that still meets the ticket's acceptance criteria. Do not guess silently.
3. **One ticket per branch**: `fn-<id>-<slug>`. Commit messages start with `FN-<id>:`. Keep PRs small and reviewable.
4. **Definition of done (every ticket):** acceptance criteria met; ruff, mypy (strict) and pytest pass; frontend lint, typecheck and vitest pass; new behavior has tests; the ticket status row in section 8 is updated; any irreversible decision is added to `DECISIONS.md`.
5. **Respect the invariants in section 2.** If a ticket seems to require breaking one, stop and record it.
6. **Do not expand scope.** Each ticket lists "Out of scope". Anything else you notice goes to the backlog list in section 9.
7. **Prefer deleting code to adding flags.** Where a ticket says remove, remove. Git history is the archive.
8. **Never commit filings, API keys or `.env` files.** The benchmark corpus stores accession numbers and labels, not documents.

---

## 1. Product thesis (one paragraph)

Analysts pay for time saved and trust. The wedge is **company-reported non-GAAP bridges** (Adjusted EBITDA and similar reconciliations), which data vendors standardize away and XBRL does not tag. Value comes from five things: (1) pulling the bridge straight from EDGAR, hours after earnings; (2) tie-out checks that prove the numbers foot; (3) every number clickable back to its source; (4) multi-period output with add-back categories and quality-of-earnings insight; (5) a review experience fast enough that clearing exceptions takes minutes.

**Non-goals for now:** narrative/MD&A analysis, a general financial-statement model generator, SOC 2, team features, mobile.

---

## 2. Invariants (must not break)

- **I1.** The classifier and any LLM never read or write numeric values. Classification outputs are constrained to taxonomy labels. Enforce structurally: result types contain no numeric field.
- **I2.** The formula engine is a pure function. Same inputs produce the same outputs, with no I/O, no randomness, and explicit ordering instead of unordered iteration.
- **I3.** No silent failures. Every skipped, failed or ambiguous item carries an explicit reason (`model_skip_reason` or equivalent) visible to the user.
- **I4.** Every extracted number has provenance (locator to its exact source). After FN-023 this is a `Locator` union; before it, the current page and bbox fields.
- **I5.** Excel numbers are written as numbers. Derived cells are live formulas. Inputs are never overwritten by calculated values.
- **I6.** Document content never appears in logs or telemetry.

---

## 3. Execution order

```
Phase 0  FN-000 -> FN-001 -> FN-002 -> FN-003, FN-060
Phase 1  FN-010 -> FN-011 ; FN-012, FN-013 ; FN-061 (+ FN-066)
Phase 2  FN-023 -> FN-021 -> FN-022 ; FN-020 ; FN-024 ; FN-025
Phase 3  FN-030 + FN-062 ; FN-063 ; FN-064 ; FN-031 ; FN-032 ; FN-033 -> FN-034 ; FN-067
Phase 4  FN-040 -> FN-041 -> FN-042 ; FN-043 ; FN-044 ; FN-045 ; FN-065
Phase 5  FN-050 ; FN-051 ; FN-052 ; FN-053 ; FN-068 ; FN-054 ; FN-055
```

Hard dependencies:
- FN-023 before FN-021.
- FN-013 before FN-031.
- FN-061 before FN-062, FN-063, FN-064, FN-067.
- FN-012 before FN-067.
- FN-040 and FN-041 before FN-043, FN-050 and FN-051.
- FN-011 gates FN-033 and FN-054 (accuracy must be measurable first).

Sizes: S <= 2 days, M <= 1 week, L <= 2 weeks.

---

# Phase 0: Audit, cut, stabilize

## FN-000: Audit the repo against this plan (S)

**Why:** this plan makes claims about code the author never saw.
**Do:**
1. Produce `docs/AUDIT.md` with: module map (backend and frontend), entry points, how jobs are stored (SQLite/JSON/disk), where the classifier is called, where the formula engine and Excel export live, and which routes the frontend calls.
2. For each **VERIFY** item in this document, record true / false / partly, with file paths.
3. List actual test counts, CI status and open P0 bugs from `docs/plan.md`.
4. Confirm the frontend stack (React? Vite? routing, state, styling approach) because design tickets depend on it.
5. Confirm whether `narrative/`, the 6-tab generator, `cash_conversion` and NetworkX drift exist and where they are used.
**Accept:** AUDIT.md committed; every VERIFY item resolved; no source changes.
**Out of scope:** fixing anything.

## FN-001: Delete dead and misleading features (S)

**Why:** dead code taxes every refactor, and some of it is user-visible.
**Investigate:** `narrative/`, `ENABLE_NARRATIVE`, the multi-statement ("6 Tabs") generator and its UI button ("Approve & Generate Complete Financial Model (6 Tabs)" appears in the review header, so it IS wired), the `cash_conversion` pack ("Valuation & Cash Conversion, Coming soon" card on the home screen).
**Do:**
1. Tag `archive/pre-cleanup` before deleting.
2. Remove `narrative/`, its routes, flag and frontend components.
3. Remove the 6-tab generator, its route and its button. The multi-year generator remains the multi-period path. If anything else depends on it, record it in section 9 and keep that part.
4. Keep the `cash_conversion` enum value in the backend; remove it from selectable UI (FN-063 re-adds it as a "Request this" card).
5. Prune dependencies no longer imported.
**Accept:** no dead imports; app starts; full test suite green; review header has no 6-tab button.
**Out of scope:** replacing the removed button (FN-030/FN-062 provide the single export action).

## FN-002: Collapse governance docs (S)

**Do:**
1. Move `docs/` (except README-linked essentials) to `docs/_archive/`.
2. Write `ARCHITECTURE.md` (max two pages): pipeline, module boundaries, invariants I1-I6, how to run tests and eval.
3. Create `DECISIONS.md`: one line per decision, with date, starting with: hosted SaaS replaces local-first; EDGAR-first ingestion; Groq free tier is not a production dependency.
4. Enforce the module dependency rules with import-linter (or an equivalent test): classifier must not import formula engine internals; formula engine must not do I/O.
5. Remove the "must have an ADR" language from contributor docs; ADRs are only for irreversible choices.
**Accept:** README links resolve; import-linter runs in CI; no duplicated FR/NFR tables remain.

## FN-003: Fix PDF-path P0 bugs only (M)

**Why:** PDF remains the fallback path; wrong highlights destroy trust.
**Investigate (VERIFY):** the P0 list in `docs/plan.md`: PyMuPDF bbox flat index off-by-one (`flat_idx = row_idx * num_cols + col_idx`), Docling bottom-left origin not inverted, canvas scale vs `PDF_RENDER_SCALE` mismatch, `clientWidth` vs `getBoundingClientRect()`, auto-lock over-locking, `is_target_metric_candidate_item()` too loose.
**Do:** fix those and nothing else. Add golden-fixture tests (known PDF, known cell, asserted bbox in page and canvas space).
**Accept:** highlight lands on the correct cell on a fixture 10-Q at two zoom levels; regression tests pass. Timebox: 1 week.
**Out of scope:** review UX redesign (FN-062), new parsers.

## FN-060: Fix visibly broken UI details (S)

**Why:** the screenshots show defects that signal "prototype" to a paying user.
**Do:**
1. **Literal `?` characters** in the review status line ("? IS: Review needed", "? CF: Ready"). Find the source (likely a missing glyph or a bad string) and replace with proper status dots (temporary until FN-062).
2. **Truncated debt table** in the Note 8 card (header clipped at "Sen…"; "Long-term debt" wraps into three lines). Make the table horizontally scroll or fit, stop wrapping headers, and truncate long cells with a tooltip.
3. **White text input** ("Select existing or type new name...") on the dark page. Style it with the theme.
4. **Queue action buttons**: labels wrap ("Excel (.xlsx)", "Audit PDF"). Stop wrapping and use consistent heights.
5. **Fiscal period label**: a Q1 10-Q is shown as "FY2025". Derive "Q1 FY25" from the document's period (VERIFY where it is computed).
6. **Duplicate queue rows**: the same file appears twice. Detect by content hash and warn or block.
7. Replace footer text "MVP · Single-user · Local extraction" with nothing (or product name and year).
8. Low-contrast label "Assign to Company (Optional)": raise contrast to WCAG AA.
**Accept:** each item has a before/after screenshot in the PR; no layout shift at 1280-1920px widths.
**Out of scope:** the full redesign.

---

# Phase 1: Prove accuracy and lay the design foundation

## FN-010: Labeled benchmark corpus (L)

**Why:** with no accuracy number, no analyst will trust the tool.
**Do:**
1. Create `eval/corpus/` with JSON labels keyed by accession number; a fetch script downloads filings on demand to a gitignored cache. No filings in git.
2. Target ~40 filings (dev 30, locked test 10) across software, retail, healthcare services, energy, telecom, industrials. Include both the 8-K EX-99.1 and the 10-Q/10-K for the same period where possible.
3. Label schema per reconciliation line: label, value, period, scale, sign, locator, standard category, plus the reported total.
4. Use XBRL facts to auto-seed GAAP lines (net income, tax, interest, D&A); humans verify.
5. Include adversarial cases: tables spanning pages, parentheses negatives, restated periods, footnote markers, scanned exhibits, Adjusted net income.
6. Double-label ~20% and record agreement.
**Accept:** corpus loads via a typed loader with a schema validator; README in `eval/` explains labeling rules.
**Out of scope:** the runner (FN-011).

## FN-011: Eval runner with CI regression gate (M)

**Do:**
1. Compute: line-item recall and precision, value exact-match, sign accuracy, scale accuracy, total tie-out rate, locator accuracy, and category accuracy once FN-033 exists.
2. Report auto-accepted and flagged items separately; report confidence calibration (accuracy per confidence bucket).
3. Record and replay LLM responses so PR runs are deterministic and free; nightly runs go live.
4. Thresholds in `eval/gates.yaml` (start: >=98% exact-match on auto-accepted values, >=90% recall). Fail PRs on regression beyond tolerance.
5. Emit markdown and JSON reports; track cost and latency per filing.
**Accept:** `make eval` produces a report from the dev split; CI runs it and fails on a deliberately broken extractor in a test.
**Out of scope:** the full F9 spec.

## FN-012: Tie-out check engine and Checks sheet (M)

**Do:**
1. Implement as a pure function (I2): inputs are the extracted batch; outputs are `CheckResult(status, expected, actual, delta, tolerance, cell_refs)`.
2. Checks: add-backs sum to reported adjusted total; net income matches income statement; D&A matches cash flow; tax and interest tie; sign and period consistency.
3. Tolerance depends on scale; configurable.
4. Write a Checks sheet into the workbook using live formulas (I5).
5. A failed check lowers affected items' status to needs-review with a reason (I3).
**Accept:** unit tests for each check with pass, fail and ambiguous cases; Excel formulas evaluate correctly (verify by recalculating in LibreOffice headless in tests).

## FN-013: Unit scale and sign normalization (S)

**Do:**
1. Detect scale from captions ("in thousands, except per share"), iXBRL `scale` (once FN-021 exists) and magnitude cross-checks.
2. Detect sign from parentheses, "Less:", "add/(deduct)" and iXBRL `sign`.
3. Store as-reported and normalized values; exempt per-share and percent rows.
4. State units in the workbook header. Ambiguity creates a flag, never a guess (I3).
**Accept:** fixtures from FN-010 hard cases pass; unit tests for thousands vs millions and mixed-scale tables.

## FN-061: Design tokens, type system and app shell (M)

**Why:** every other design ticket builds on this. Current UI uses purple, blue, green, teal and orange for categories; there is no depth, scale or primary action.
**Do:**
1. Implement the tokens in Appendix A as CSS variables, wired into the existing styling system (Tailwind config if present, otherwise CSS modules or global CSS). **VERIFY** the stack in FN-000. If there is no component library, adopt Radix primitives (shadcn/ui pattern); do not rewrite working components wholesale.
2. Self-host variable fonts (display serif, UI sans, mono). Provide `font-variant-numeric: tabular-nums` utility for all figures.
3. Build primitives: Button (primary, secondary, ghost, danger), IconButton, Input, Select, Badge, StatusDot, Tooltip, Popover, DropdownMenu, Tabs, Progress, Skeleton, Toast, Card, DataTable shell.
4. Build the app shell: slim left rail or top bar, content region with max width, route-aware breadcrumbs. Replace the bordered centered column.
5. Add a `/design` route (dev only) rendering every primitive in light and dark for review.
6. Adopt one icon family at a single stroke weight; remove emoji icons.
**Accept:** `/design` route covers all primitives; no hard-coded colors outside tokens in new code (lint rule or grep check); AA contrast verified for text and controls in the light theme.
**Out of scope:** redesigning individual screens.

## FN-066: Footnote-marker brand system (S)

**Why:** the product is named after a typographic device; make it the signature.
**Do:**
1. Wordmark: lowercase `footnote` with a superscript marker; favicon and app icon.
2. `SourceChip` component: a small superscript-style chip shown next to any number that has provenance; hover previews the source snippet; click opens the source viewer (PDF page or EDGAR link, wired for real in FN-032).
3. Motion spec: 150-200 ms ease-out, spring only for panel transitions; respect `prefers-reduced-motion`.
4. Empty-state illustrations built from the same marker motif (no stock art).
**Accept:** SourceChip appears in at least the review list and the debt card; documented in `/design`.

---

# Phase 2: EDGAR-native ingestion

## FN-023: `Locator` union schema (S)

**Why:** a fixed `page` + `bbox` provenance model cannot describe HTML sources. Blocks FN-021.
**VERIFY:** where the five-field record (`value, label, page, bbox, source_file`) is defined and frozen.
**Do:**
1. Define `Locator = PdfLocator(page, bbox, source_file) | HtmlLocator(accession, document, element_path, char_range, url)` as a pydantic discriminated union.
2. Migrate existing records (PDF to `PdfLocator`) with a backward-compatible reader and a migration script. Let mypy strict enumerate call sites (audit trail, review, audit report, excel export, review IDs).
3. Define a canonical serialization so content-hash review IDs stay stable.
4. Map to W3C annotation selectors (fragment, XPath, text-quote) in the provenance export.
5. Frontend: mirror the union in types; viewer chooses PDF.js or an HTML source renderer.
6. Record ADR in `DECISIONS.md`.
**Accept:** all existing tests pass unchanged in behavior; round-trip tests for both variants; old job data loads.

## FN-020: EDGAR client (M)

**Do:**
1. Implement ticker to CIK, filings list (submissions API), and document and exhibit fetch. Return typed `FilingRef(cik, accession, form, period, filed_at, primary_url, exhibits)`.
2. Send a descriptive User-Agent with contact details; token-bucket rate limit (verify current SEC fair-access guidance, historically ~10 requests/s); retries with backoff; circuit breaker.
3. Cache by accession (immutable). Handle 10-K/A and 10-Q/A, share classes, ticker changes, CIK zero-padding. Foreign filers return an explicit unsupported error (I3).
4. Recorded-fixture contract tests; one nightly live smoke test.
**Accept:** `get_filings("GOOGL")` returns the latest 10-Q and 10-K with correct periods in tests; rate limiter proven by a unit test.

## FN-021: iXBRL/HTML table extractor (L), depends on FN-023

**Do:**
1. Parse iXBRL facts (concept, context period, scale, sign) for GAAP lines and cross-checks.
2. Parse HTML tables for untagged non-GAAP reconciliations: colspan/rowspan, parentheses, split currency cells, footnote markers, multi-column periods (assign a period to each cell).
3. Port reconciliation-table detection heuristics (keywords plus structure) to HTML and benchmark them in FN-011.
4. Emit the existing `ExtractedRecord` with `HtmlLocator` so downstream code is untouched.
5. Stream-parse large documents; target a few seconds per 10-K.
6. If no reconciliation table is found, return an explicit "not found" status (I3).
**Accept:** on the dev corpus, recall and exact-match on HTML sources meet or exceed the PDF baseline from FN-011; throughput recorded.

## FN-022: 8-K EX-99.1 earnings release support (M)

**Do:** discover Item 2.02 and EX-99.1 exhibits from the filing index; extract quarterly and YTD reconciliations; tag forward-looking (guidance) reconciliations separately; route PDF/image exhibits to the fallback; when the 10-Q arrives, diff its bridge vs the release and flag differences; dedupe by "latest filed wins" while keeping both sources in provenance.
**Accept:** corpus filings with both sources produce a consistent canonical bridge plus a diff report.

## FN-024: Ingestion router (M)

**Do:**
1. One entry point accepting ticker+period, accession or uploaded file. Route: EDGAR HTML/iXBRL, then EX-99.1, then PDF fallback.
2. Extend `parser_used` with an `ixbrl_html` value; keep existing PDF and mixed banners.
3. Every failed route sets an explicit reason (I3).
4. Stamp extractor, classifier and taxonomy versions on results.
5. Idempotent by (accession, pack, versions); per-user concurrency limits.
**Accept:** decision-table unit tests; same input twice returns the cached result.

## FN-025: Shared extraction cache with per-user overlay (M)

**Do:**
1. Cache key: (accession, document, pack, extractor_version, taxonomy_version). Shared base layer plus a private per-user corrections overlay; merge precedence: user over verified over machine.
2. A correction becomes shared only after staff review or agreement from N independent users.
3. Never share overlays or viewing history; log minimally.
4. Version bump triggers lazy recompute; keep old results for audit; record `supersedes` for amended filings.
**Accept:** unit tests for merge precedence and invalidation; no per-user data in the shared layer (test).

---

# Phase 3: The product analysts want

## FN-030: Non-blocking generate-first workflow (M)

**Do:**
1. Generate the workbook immediately from all items: auto-accepted normal; uncertain cells yellow with a comment; manual-required left empty and red (I3).
2. Add a Review sheet listing each flagged cell with reason, confidence and source link.
3. Add a workbook status header ("DRAFT: N items unverified" or "VERIFIED").
4. Keep lock semantics for confirmed items. Remove the "Generate Model (N)" count gate from the review header; replace with a single "Export to Excel" action (UI is built in FN-062).
**Accept:** workbook generates with zero reviewed items; flagged cells are present, empty or flagged, never silently filled; tests cover each status.

## FN-062: Review screen redesign (L), depends FN-061, FN-003; pairs with FN-030

**Why:** this screen sells the product. In the screenshot it has a 3-line debug header (UUID, engine pill), two competing CTAs, nested scroll boxes, a narrow list, and a PDF where every cell is highlighted.
**Do:**
1. **Header:** move job UUID and engine into a details popover; one primary split button "Export to Excel" with a dropdown for audit trail and audit PDF.
2. **Progress:** replace the status text row with a stacked bar (verified / needs review / manual) and counts (e.g. "104 items, 53 verified, 51 need review").
3. **List:** one virtualized list (TanStack Virtual) with tabs All / Flagged / by statement; remove the nested scroll boxes; the Pending Taxonomy Confirmations panel becomes a collapsible section with a bulk "Accept all" and inline label editing.
4. **Keyboard flow:** `J/K` next/previous, `Y` accept, `E` edit, `Esc` cancel, `?` shortcut sheet. Selecting an item scrolls the PDF to it and animates a highlight sweep.
5. **PDF pane:** highlight only the selected item (and hover state); highlighter-yellow with multiply blending; toolbar with zoom, fit-width, page thumbnails; PDF background stays white with a soft shadow on the warm canvas.
6. **Layout:** resizable split pane (`react-resizable-panels`), width persisted.
7. **Status visuals:** use shape plus color: filled dot verified, half dot needs review, hollow dot manual.
8. Use `SourceChip` (FN-066) beside values.
**Accept:** a reviewer can clear 20 flagged items using only the keyboard; no nested scrolling; Playwright test covers select, accept, edit, undo; Lighthouse accessibility >= 95 on this screen.
**Out of scope:** HTML source viewer (comes with FN-032).

## FN-063: Home and queue redesign (M), depends FN-061

**Do:**
1. **Hero:** "What do you want to build?" Pack cards show a thumbnail of the real output; selected state is a filled ring plus check. The "Coming soon" card becomes "Request this" (records interest to the backend).
2. **Entry:** add a ⌘K command palette and ticker search. Until FN-020 lands it lists existing companies and "upload a filing". Upload becomes a slim drop bar that expands with a spotlight on drag-over. Remove the large empty dropzone and the "PDF only · Max 100 MB" boilerplate.
3. **Split the queue**: staging (files about to submit) vs results (history). Remove the "Submit for extraction" button sitting under completed rows.
4. **Status:** replace "MODEL READY" pills with a stepper (Parsing, Classifying, Checks, Ready) driven by real job events.
5. **Actions:** one primary "Open workbook"; Review, Audit Trail, Audit PDF go in an overflow menu.
6. **Metadata:** auto-detect company and period from the filing; delete the "Assign to Company (Optional)" field (keep an edit affordance); drop file size.
7. Empty states with a clear action.
**Accept:** component tests; the upload to ready flow works with keyboard only; no layout wrapping at 1280px.

## FN-064: Debt card and DataTable component (M), depends FN-061

**Do:**
1. Reusable `DataTable`: sticky header, right-aligned tabular numerals, negatives in parentheses, units in header, truncation with tooltip, column resize, optional row selection.
2. Note 8 card: Total Principal as a hero number; maturity ladder chart (simple bar chart by year, accessible labels); table via `DataTable`; "Confirm Debt Schedule" as the card's primary action; icon in place of the emoji.
3. Tie-out badge ("tranches sum to total: pass/fail") once FN-012 supports it.
**Accept:** no text clipping at 1280px; snapshot test; chart has a text alternative.

## FN-031: Multi-period workbook default (M), depends FN-013

**Do:** periods as columns (8Q or 5Y plus an LTM formula column), line items as rows aligned by normalized label and taxonomy; latest filing wins for restated periods with a comment ("restated, was X"); handle non-calendar and 52/53-week years; missing periods shown as explicit gaps with reasons (I3), never zeros; build on the existing multi-year generator and trigger it from the ticker flow.
**Accept:** fixtures with a restatement and a fiscal-year mismatch produce correct columns and comments; LTM formula verified by LibreOffice recalculation in tests.

## FN-032: Deep links and source viewer (M)

**Do:**
1. Replace bbox coordinate comments with human-readable text ("10-Q Q2 FY26 · p.34 · Adjusted EBITDA reconciliation") and a hyperlink on the Source_Inputs label cell (`write_url`); values stay plain numbers (I5). Reversing the earlier no-hyperlink decision is justified because the product is hosted; note it in `DECISIONS.md`.
2. HTML sources link to the public sec.gov document with a text fragment; PDF sources link to the hosted viewer; private overlay sources use short-lived signed URLs.
3. Build the HTML source renderer for the review screen (iframe or sanitized render with element highlight).
**Accept:** nightly job HEAD-checks sample link targets; a workbook opened with openpyxl shows working hyperlinks.

## FN-033: Add-back standardization (M), gated by FN-011

**Do:** extend the taxonomy with standard categories (SBC, restructuring, impairment, M&A/integration, litigation, FX, other); alias match first, LLM for unknowns constrained to categories (I1); version the taxonomy; workbook shows Reported and Standardized Adjusted EBITDA with 1/0 include toggles (live formulas); flag "Other" above a threshold; add category accuracy to FN-011.
**Accept:** category accuracy reported in eval; toggles recompute in LibreOffice.

## FN-034: Quality-of-earnings panel and component diff (M), depends FN-033

**Do:** replace the graph-based drift with rows of (company, period, component, category, label, value) and a pure diff function; metrics: add-backs as a share of reported adjusted EBITDA, trend, category mix, "recurring non-recurring" flag (same category in >= N of last M periods); cosmetic relabel auto-detected by category and value continuity; keep the user's `mark-relabeled` action; migrate existing drift data; remove NetworkX; output a QoE sheet (formulas) plus a web panel.
**Accept:** labeled definition changes in the corpus are detected; no networkx import remains.

## FN-067: Workbook preview and payoff moment (M), depends FN-012, FN-030, FN-061

**Do:** before export, show a read-only preview of the workbook grid (first sheet) with the check summary ("5/5 checks passed") and flagged cells highlighted; "Export to Excel" sits beside it; a short celebratory (but restrained) transition when generation completes.
**Accept:** preview renders from the same grid spec used by the exporter (no divergence); keyboard accessible.

---

# Phase 4: SaaS readiness

## FN-040: Authentication (M)
Use a managed provider; email magic link plus Google and Microsoft sign-in; httpOnly secure cookies, CSRF, JWT verification as a dependency on every route; basic roles; production CORS origin; per-user and per-IP rate limits; account deletion and data export. **Accept:** unauthenticated requests rejected in tests; ownership tests (FN-041) pass.

## FN-041: Postgres and multi-tenant model (M)
Tables: users, orgs, filings, extraction_records, corrections, jobs, workbooks, components, usage_events, subscriptions. Alembic migrations; object storage for PDFs and workbooks; row ownership enforced in the data layer with cross-tenant leakage tests; deterministic ordering; job state machine (queued, running, done, failed, needs_review) with reasons; import tool for local data. **Accept:** cross-tenant read attempts fail in tests.

## FN-042: Hosted queue and autoscaled workers (M)
Separate queues (html, pdf, llm); PDF worker scales to zero (fallback only); timeouts, retries, idempotency by accession; dead-letter queue; job progress via SSE or polling (powers FN-063 stepper); per-user concurrency caps; containerize; staging environment; CI/CD; cost per job recorded. **SLO:** p95 < 60 s cached, < 3 min fresh. **Accept:** load test at earnings-season volume meets the SLO.

## FN-043: Billing and metering (M)
Stripe Checkout, portal, webhooks; meter on workbook generated (not views); free trial (e.g. 3 workbooks); entitlements middleware with clear over-limit messaging; `org_id` designed in; churn-reason capture. **Accept:** webhook tests; margin per workbook computed from FN-011/FN-042 cost data.

## FN-044: LLM provider abstraction (S)
`Classifier.classify(label, context) -> ClassificationResult(label, confidence, rationale)` with no numeric field (I1); adapters for a paid hosted model, a fallback and local Ollama; choose the model via the FN-011 classification benchmark; structured-output enforcement; budget caps; decision logging (input, label, confidence, model id, prompt version); one batched call per filing; global label cache. **Accept:** swapping providers requires config only; eval compares candidates.

## FN-045: Security and privacy baseline (M)
Encryption in transit and at rest; secrets manager; default retention with user deletion; no-training policy plus vendor zero-retention; error tracking with scrubbing and log-redaction tests (I6); sandboxed parsing of untrusted PDFs with resource limits and scanning; audit log; dependency scanning; privacy page, DPA template and sub-processor list. **Accept:** redaction tests pass; sandbox limits tested with a hostile PDF fixture.

## FN-065: Dark theme, accessibility and visual regression (M), depends FN-061
Ship dark tokens (Appendix A) as a proper second theme with system preference and a manual toggle; WCAG AA across both themes; full keyboard paths and visible focus rings; `prefers-reduced-motion`; Playwright visual regression for home, queue, review and debt card in both themes. **Accept:** axe-core reports zero serious violations on the four screens; visual snapshots in CI.

---

# Phase 5: Pull and pilot

## FN-050: Watchlist and alerts (M)
Per-user watchlist; detect new filings (poll submissions within rate limits; prioritize Item 2.02 and 10-Q/K); pipeline detection, extraction (shared cache), email with headline metrics and flagged count; dedupe; digest option; preferences and unsubscribe; load-test earnings spikes. **Accept:** end-to-end test with fixtures; unsubscribe works.

## FN-051: Warm cache for a coverage universe (M)
Backfill the S&P 500 (eight quarters), throttled to SEC limits; label output "auto-extracted, not yet verified"; coverage report; failed filings become a work queue; "ready" badge in ticker autocomplete; cost cap from FN-011 metrics. **Accept:** coverage report generated; backfill resumable.

## FN-052: Onboarding and activation (S)
First-run suggests a popular ticker; workbook in under 60 seconds; three-step tooltip tour (Checks sheet, flagged cells, source links); funnel instrumentation (signup, ticker, generated, downloaded, source clicked); error messages say what to do (from reasons); downloadable sample workbook; day-1 and day-3 emails. **Accept:** funnel events visible in analytics.

## FN-053: Pilot (M, non-code)
Recruit ~10 analysts (research, credit, PE/LevFin); 60 days free for feedback and permission to use anonymized corrections; instrument time-to-workbook, correction rate, flagged rate, repeat usage; run a willingness-to-pay test at week 4; predeclare kill criteria (e.g. < 40% weekly return or < 3 of 10 willing to pay); feed every failure into the corpus; pick the next pack from evidence; publish ToS with a not-investment-advice disclaimer.

## FN-068: Marketing site and hero demo (L), depends FN-061, FN-066
Landing page: hero demo showing a number in a filing flowing into a cell with its footnote chip (real component, scripted data); sample workbook download; pricing; benchmark results page ("X% exact-match on N bridges" from FN-011); trust section (data handling, no training on uploads). Performance budget: LCP < 2.0 s. **Accept:** Lighthouse performance >= 90 and accessibility >= 95.

## FN-054: Harden capital structure pack (L), gated by FN-011 and FN-053
Separate corpus of 20-30 debt footnotes; schema for revolver commitment vs drawn, unamortized costs, current portion; tie-outs (maturity schedule sums to total debt; tranche carrying amounts reconcile to the balance sheet); lease checks; use iXBRL debt tags as cross-checks; link to the bridge for leverage stats; GA only after passing its accuracy gate, otherwise labeled beta.

## FN-055: Excel add-in (L, post-pilot)
Refactor the formula engine to emit a neutral grid spec with two renderers (xlsxwriter, Office.js); task pane inserts the bridge into the active workbook; same SSO; Refresh action; named ranges. Verify the current Office add-in distribution process and bank IT constraints before committing. Proceed only if pilot users report pasting outputs into their own models.

---

# 8. Status tracker

| ID | Title | Phase | Size | Depends | Status |
|---|---|---|---|---|---|
| FN-000 | Audit | 0 | S | none | done |
| FN-001 | Delete dead features | 0 | S | 000 | done |
| FN-002 | Collapse docs | 0 | S | 000 | done |
| FN-003 | PDF P0 bugs | 0 | M | 000 | done |
| FN-060 | Fix visible UI defects | 0 | S | 000 | done |
| FN-010 | Benchmark corpus | 1 | L | 003 | done |
| FN-011 | Eval runner and CI gate | 1 | M | 010 | done |
| FN-012 | Tie-out checks | 1 | M | 001 | done |
| FN-013 | Scale and sign | 1 | S | 010 | done |
| FN-061 | Tokens, type, shell | 1 | M | 060 | done |
| FN-066 | Brand and SourceChip | 1 | S | 061 | done |
| FN-023 | Locator union | 2 | S | 003 | done |
| FN-020 | EDGAR client | 2 | M | 002 | done |
| FN-021 | iXBRL/HTML extractor | 2 | L | 023, 020 | done |
| FN-022 | EX-99.1 support | 2 | M | 021 | done |
| FN-024 | Ingestion router | 2 | M | 021 | done |
| FN-025 | Shared cache | 2 | M | 024 | done |
| FN-030 | Generate-first workflow | 3 | M | 012 | todo |
| FN-062 | Review redesign | 3 | L | 061, 003, 030 | todo |
| FN-063 | Home and queue redesign | 3 | M | 061 | todo |
| FN-064 | Debt card and DataTable | 3 | M | 061 | todo |
| FN-031 | Multi-period workbook | 3 | M | 013 | todo |
| FN-032 | Deep links and viewer | 3 | M | 021, 023 | todo |
| FN-033 | Add-back standardization | 3 | M | 011 | todo |
| FN-034 | QoE panel and diff | 3 | M | 033 | todo |
| FN-067 | Workbook preview | 3 | M | 012, 030, 061 | todo |
| FN-040 | Auth | 4 | M | none | todo |
| FN-041 | Postgres multi-tenant | 4 | M | 040 | todo |
| FN-042 | Queue and workers | 4 | M | 041 | todo |
| FN-043 | Billing | 4 | M | 041 | todo |
| FN-044 | LLM abstraction | 4 | S | 011 | todo |
| FN-045 | Security baseline | 4 | M | 041 | todo |
| FN-065 | Dark theme, a11y, visual regression | 4 | M | 061 | todo |
| FN-050 | Watchlist and alerts | 5 | M | 041, 025 | todo |
| FN-051 | Warm cache | 5 | M | 041, 025 | todo |
| FN-052 | Onboarding | 5 | S | 063 | todo |
| FN-053 | Pilot | 5 | M | 043 | todo |
| FN-068 | Marketing site | 5 | L | 061, 066 | todo |
| FN-054 | Capital structure hardening | 5 | L | 011, 053 | todo |
| FN-055 | Excel add-in | 5 | L | 053 | todo |

---

# 9. Blockers, deviations and backlog (agent writes here)

_Blockers and deviations:_
- **FN-001 (6-tab retirement)**: In addition to `multi_statement_generator.py` and the ReviewPage button, the `/{company_id}/full-model` endpoint in `company_router.py` and the 6-tab button in `CompanyMultiYearCard.tsx` were removed as they were entry points to the deleted 6-tab generator. The `/{company_id}/multi-year-model` route and multi-year generator remain the sole multi-period output path.
- **FN-003 (PyMuPDF flat_idx)**: In `docling_parser.py`, `table.cells` contains all table cells including row 0 (headers). Corrected flat index calculation from `(row_idx - 1) * num_cols + (col_idx - 1)` to `row_idx * num_cols + col_idx` to prevent 1-row and 1-column cell highlight offsets.
- **FN-010 (Corpus & Manifest)**: 40 accession-keyed filing labels created across 6 sectors (30 dev, 10 test, 20% double-labeled with 100% agreement, 6 paired 8-K/10-K). On-demand EDGAR fetcher caches strictly to gitignored `eval/.cache/` (0 binaries committed).
- **FN-011 (Gates & Determinism)**: `eval/gates.yaml` regression gate suite implemented with `RecordReplayClassifierClient` cassette record/replay for deterministic offline CI runs. Strict gate violations return non-zero exit code.
- **FN-012 (Checks Sheet)**: Pure function tie-out checker implemented across all 5 checks with live formula generation in Excel `Checks` worksheet. Provenance records remain strictly mapped to model cells to maintain 1:1 locator invariant.
- **FN-013 (Scale & Sign)**: Pure functions normalize caption scale, handle accounting parentheses, exempt per-share/ratio metrics, and write explicit units headers to generated workbooks.
- **FN-061 & FN-066 (Design & Brand)**: Full Appendix A tokens in CSS variables (light paper & ink default + low-glare dark workstation), tabular figures utility, primitive UI suite, slim layout with breadcrumbs and theme switcher, dev-only `/design` preview route, brand wordmark, `SourceChip` citation popover with PDF jump, and 3 actionable empty states.
- **FN-023 (Locator Union)**: Pydantic discriminated union `Locator = PdfLocator | HtmlLocator` implemented with two-way backward compatibility for `page`/`bbox`/`source_file`. Content-hash review ID stability preserved (legacy 16-hex for PDF, deterministic element-path for HTML). Provenance export maps to W3C XPath and fragment selectors.
- **FN-020 (EDGAR Client)**: SEC Submissions API client implemented with ticker-to-CIK padding, token-bucket rate limiting (<= 10 req/s), circuit breaker, immutable accession disk caching, and explicit `ForeignFilerUnsupportedError` rejection on Forms 20-F, 40-F, 6-K per Invariant I3.
- **FN-021 (iXBRL / HTML Extractor)**: Dual extractor for inline XBRL facts and HTML table structures (colspan/rowspan grid reconstruction, parentheses, periods, XPath). Emits `ExtractedRecord` with `HtmlLocator` and explicit `not_found` failure reasons per Invariant I3.
- **FN-022 (8-K EX-99.1 Earnings Release)**: Item 2.02 discovery, quarterly/YTD table extraction, guidance/outlook tagging, bridge diffing vs subsequent 10-Q, and 'latest filed wins' deduplication preserving dual provenance.
- **FN-024 (Ingestion Router)**: Unified cascade router (EDGAR HTML/iXBRL -> 8-K EX-99.1 -> PDF fallback) with explicit failure reasons, `ixbrl_html`/`mixed` parser tagging, version stamping, and per-user concurrency limits.
- **FN-025 (Shared Cache)**: Multi-layer cache with merge precedence `user > verified > machine`, consensus promotion (N=3), audit preservation on version bump, and verified zero per-user data in shared layers.

_Out-of-scope discoveries:_ (none)

---

# Appendix A: Design tokens (starting values; tune visually in FN-061)

**Direction:** light-first "paper and ink", dark as a designed second theme. A warm off-white canvas lets the filing (a white document) be the hero. One interaction accent; yellow reserved for source highlights; green, amber and red only as small status signals.

| Token | Light | Dark |
|---|---|---|
| `--bg` canvas | `#FAF8F4` | `#0E0F12` |
| `--surface` | `#FFFFFF` | `#16181D` |
| `--surface-2` | `#F3F0EA` | `#1D2026` |
| `--ink` text | `#14120F` | `#ECEAE5` |
| `--ink-muted` | `#6B665E` | `#9A978F` |
| `--border` | `rgba(20,18,15,.10)` | `rgba(255,255,255,.08)` |
| `--accent` interaction | `#2B4BEE` | `#7B93FF` |
| `--highlight` source | `#FFE680` (multiply) | `#FFD84D` at 35% |
| `--ok` / `--warn` / `--danger` | `#1F8A5B` / `#B7791F` / `#C2410C` | `#4CC38A` / `#E0A33C` / `#F0714A` |

- **Type:** display serif for hero moments only (Newsreader or Instrument Serif); UI sans (Inter or Geist); mono (JetBrains Mono) for IDs. Scale (px): 12, 13, 14, 16, 20, 24, 32, 48. All figures tabular; numbers right-aligned.
- **Space and shape:** 4px grid; radii 6 / 10 / 14; hairline 1px borders; two-layer soft shadows (`0 1px 2px` plus `0 8px 24px` at low alpha).
- **Motion:** 150 ms (hover), 200 ms (state), 280 ms spring (panels); no looping animation except progress indicators.
- **Accessibility:** AA minimum (4.5:1 text, 3:1 UI); never use color alone for status; focus ring 2px accent with 2px offset.

# Appendix B: VERIFY list (resolve in FN-000)

1. Frontend stack and styling system; whether a component library exists.
2. Where fiscal period labels are computed (the Q1 10-Q shows "FY2025").
3. Where `?` glyphs in the review status row originate.
4. Whether the 6-tab generator has any dependents besides the review button.
5. Where drift data is stored and whether NetworkX is used outside drift.
6. How jobs and corrections are persisted today.
7. The five-field record definition and every place it is serialized.
8. Whether CI exists (the plan lists GitHub Actions as deferred).
9. Current test counts, lint and mypy status.
10. Which P0 bugs listed in `docs/plan.md` are already fixed.
