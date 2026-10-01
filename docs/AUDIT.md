# Footnote — Codebase Audit (FN-000)

> **Generated:** 2026-10-01
> **Purpose:** Verify every assumption in `docs/footnote-enhancements.md` against actual source code.

---

## 1. Module Map

### Backend (`backend/app/`)

| Module | Path | Purpose |
|---|---|---|
| **main** | `app/main.py` | FastAPI entry point. Router registration, CORS, health check. |
| **job_runner** | `app/job_runner.py` | Pipeline orchestrator — runs extraction → classification → model generation. |
| **model_compilation_service** | `app/model_compilation_service.py` | Cross-layer provenance compilation for audit/export. |
| **ingestion/** | `app/ingestion/` | PDF upload (`router.py`), file validation (`validation.py`), job persistence (`repository.py`), EDGAR client stub (`edgar_client.py`), company CRUD (`company_repository.py`, `company_router.py`). |
| **extraction/** | `app/extraction/` | Docling parsing (`docling_parser.py`), PyMuPDF coordinate normalization (`coordinate_normalizer.py`), confidence scoring (`confidence.py`), record assembly (`assembler.py`), flagging (`flagger.py`). |
| **classification/** | `app/classification/` | Master taxonomy (`taxonomy.py`), deterministic alias matching + Groq LLM dispatcher (`dispatcher.py`), Groq client (`client.py`), decision logging (`decision_log.py`), normalizer (`normalizer.py`). |
| **formula_engine/** | `app/formula_engine/` | Pure-function formula tree construction (`tree.py`), reader (`reader.py`), models (`models.py`). No I/O, no randomness. |
| **excel_export/** | `app/excel_export/` | `bridge_generator.py` (2-tab), `debt_schedule_generator.py`, `multi_statement_generator.py` (6-tab), `multi_year_generator.py`, provenance (`provenance.py`), utilities (`utils.py`). |
| **review/** | `app/review/` | Review state management, confirm/flag/edit actions, PDF streaming. |
| **audit_trail/** | `app/audit_trail/` | Source-chain resolver mapping cells → PDF page + bbox. |
| **audit_report/** | `app/audit_report/` | PDF audit report compilation (ReportLab + WeasyPrint). |
| **drift/** | `app/drift/` | Cross-year metric drift detection using NetworkX DiGraph (`graph.py`) + SQLite persistence (`storage.py`). |
| **footnote/** | `app/footnote/` | Debt schedule and lease schedule extraction for capital_structure pack. |
| **narrative/** | `app/narrative/` | MD&A diffing and risk factor redlining. Deferred — NOT wired to pipeline but routes are active when `ENABLE_NARRATIVE=true` (default). |

### Frontend (`frontend/src/`)

| Component | Path | Purpose |
|---|---|---|
| **App** | `App.tsx` | Root. Conditional rendering (no router library). State: `useState`/`useEffect`. |
| **UploadZone** | `components/UploadZone.tsx` | Drag-and-drop upload, workflow pack selection cards. |
| **JobList** | `components/JobList.tsx` | Staged files + persisted jobs queue table. |
| **SubmitBar** | `components/SubmitBar.tsx` | "Submit for extraction" action bar. |
| **ReviewPage** | `components/review/ReviewPage.tsx` | Side-by-side PDF + review list. Contains 6-tab button and status chips. |
| **AuditTrailView** | `components/audit/AuditTrailView.tsx` | Audit trail cell-to-source viewer. |
| **DebtScheduleCard** | `components/DebtScheduleCard.tsx` | Note 8 debt table card. |
| **LeaseScheduleCard** | `components/footnote/LeaseScheduleCard.tsx` | ASC 842 lease waterfall card. |
| **ConcentrationCard** | `components/footnote/ConcentrationCard.tsx` | Customer/revenue concentration card. |
| **CompanySelector** | `components/CompanySelector.tsx` | "Assign to Company (Optional)" input. |
| **CompanyMultiYearCard** | `components/CompanyMultiYearCard.tsx` | Multi-year model generation card. |
| **DriftFlagCard** | `components/drift/DriftFlagCard.tsx` | Drift detection display card. |
| **NarrativeDiffView** | `components/narrative/NarrativeDiffView.tsx` | MD&A diff viewer (narrative, deferred). |
| **RiskRedlineView** | `components/narrative/RiskRedlineView.tsx` | Risk factor redline viewer (narrative, deferred). |
| **ModelViewer** | `components/ModelViewer.tsx` | Model data viewer. |
| **ErrorBoundary** | `components/ErrorBoundary.tsx` | React error boundary. |

---

## 2. Entry Points

- **Backend:** `uvicorn app.main:app --reload` (from `backend/`)
- **Frontend:** `npm run dev` → Vite dev server at `localhost:5173`

---

## 3. Job Storage

Jobs are persisted as **JSON on disk**:
- **Job metadata:** `backend/data/jobs.json` — JSON array of `JobRecord` objects. Read-modify-write with a threading `RLock`. Atomic writes via tempfile + `os.replace`.
- **PDF files:** `backend/data/uploads/<job_id>.pdf` — keyed by UUID, never by filename.
- **Extraction data:** Stored as JSON files alongside jobs in `backend/data/`.
- **Drift data:** SQLite database at `backend/data/drift.db`.
- No external database (Postgres, Redis, etc.). Single-user, file-based persistence.

---

## 4. Classifier Call Chain

1. `job_runner.py` calls `classification/dispatcher.py`
2. Dispatcher runs **Level 1:** deterministic alias matching against `classification/taxonomy.py` (60–80 item Master Financial Taxonomy)
3. Unmatched items go to **Level 2:** `classification/client.py` → Groq API (`openai/gpt-oss-120b`)
4. Results logged via `classification/decision_log.py`
5. Classifier returns labels only — never numeric values (invariant I1 is structurally enforced)

---

## 5. Formula Engine and Excel Export

- **Formula engine:** `app/formula_engine/tree.py` — pure functions, builds formula AST from classified records.
- **Excel export:** `app/excel_export/bridge_generator.py` (primary 2-tab output), `debt_schedule_generator.py`, `multi_year_generator.py`.
- **6-tab generator:** `app/excel_export/multi_statement_generator.py` — 1229 lines. Frozen as beta per ADR-003 but still importable and wired.
- **Excel library:** xlsxwriter 3.2.9 (creates new workbooks only — no editing existing files).

---

## 6. Frontend Stack

| Aspect | Value |
|---|---|
| Framework | React 19.2 + TypeScript 6.0 |
| Build | Vite 8.2 |
| Router | **None** — conditional rendering in `App.tsx` via state flags (`activeReviewJobId`, `activeAuditJobId`) |
| State management | React hooks only (`useState`, `useEffect`). No Redux, Zustand, etc. |
| Styling | **Custom CSS** with CSS variables/tokens (`tokens.css`, component `.css` files) + inline styles. **No Tailwind**. No CSS-in-JS. |
| Component library | **None**. No MUI, Chakra, Radix, or shadcn/ui. |
| Icons | `lucide-react` for SVG icons + raw emoji characters (🏛️, ✨, ✅, ⓘ). |
| PDF rendering | `pdfjs-dist` 4.10 with `PDF_RENDER_SCALE = 1.5` |
| Testing | Vitest 4.1, 18 test files |

---

## 7. Routes the Frontend Calls

| Method | Path | Source |
|---|---|---|
| GET | `/upload/jobs` | `App.tsx` (polling) |
| POST | `/upload/jobs` | `App.tsx` (submit) |
| GET | `/companies` | `CompanySelector.tsx` |
| GET | `/models/{job_id}/download` | `JobList.tsx` |
| GET | `/review/{job_id}/items` | `ReviewPage.tsx` |
| POST | `/review/{job_id}/batch-accept` | `ReviewPage.tsx` |
| GET/POST | Various audit, drift, footnote routes | Other components |

---

## 8. Test Counts and CI Status

- **Backend tests:** 82 test files, ~500 test cases (pytest collection count).
- **Frontend tests:** 18 test files (vitest).
- **CI:** **No CI pipeline exists.** No `.github/workflows/`, `.gitlab-ci.yml`, or similar. Plan.md notes GitHub Actions as "deferred — Phase 5 frozen".
- **mypy config:** `mypy.ini` present, strict mode configured.
- **Lint:** ruff 0.16 (backend), eslint 10 (frontend).

---

## 9. VERIFY Item Resolution

### VERIFY 1: Frontend stack and styling system; whether a component library exists.
**TRUE (mostly).** React 19 + TypeScript + Vite 8. Styling is **custom CSS with CSS variables** (defined in `tokens.css`). **No Tailwind.** **No component library** (no MUI, Radix, shadcn/ui, or Chakra). The plan's suggestion to "adopt Radix primitives (shadcn/ui pattern)" in FN-061 is viable since nothing needs to be replaced — it would be additive.

### VERIFY 2: Where fiscal period labels are computed (the Q1 10-Q shows "FY2025").
**TRUE — labels are naive.** Fiscal period is computed in:
- `CompanyMultiYearCard.tsx`: uses `j.filing_year ? 'FY${j.filing_year}' : 'FY(${j.filename})'`
- `JobRecord.filing_year` is a user-supplied integer (optional). There is **no form type detection** (10-Q vs 10-K) and **no quarter derivation**. A Q1 10-Q filed in 2025 will show as "FY2025" because only the year is stored.

### VERIFY 3: Where `?` glyphs in the review status row originate.
**PARTLY TRUE.** The `?` characters the plan references come from `JobList.tsx` line 57: `<span>ⓘ</span>` (U+24D8 circled information source). This Unicode character renders as `?` on systems/fonts that lack it. The review page status chips (`ReviewPage.tsx` lines 774–789) use **Lucide SVG icons** (`AlertCircle`, `CheckCircle2`) which render fine. The `?` problem is specifically in the **queue table**, not the review header.

### VERIFY 4: Whether the 6-tab generator has any dependents besides the review button.
**FALSE — it has more connections.** The 6-tab generator (`multi_statement_generator.py`) is:
- Imported by `excel_export/router.py` (has a dedicated route)
- Referenced by `ReviewPage.tsx` button at lines 597–602 and 821–835 ("Approve & Generate Complete Financial Model (6 Tabs)")
- Has its own test file (`test_multi_statement_generator.py`)
- Imports from `formula_engine/models.py` (`ComprehensiveModelTree`)
- Used in `model_compilation_service.py` context

Before removing: need to verify the router endpoint can be safely removed and that `ComprehensiveModelTree` isn't needed elsewhere.

### VERIFY 5: Where drift data is stored and whether NetworkX is used outside drift.
**TRUE.** Drift data is stored in **SQLite** (`backend/data/drift.db`) via `drift/storage.py`. NetworkX is used **only** in `drift/graph.py` (HistoricalDriftGraph). No other module imports NetworkX. The `requirements.txt` lists `networkx==3.6.1`.

### VERIFY 6: How jobs and corrections are persisted today.
**TRUE.** Jobs are persisted as a JSON array in `backend/data/jobs.json` via `ingestion/repository.py`. Corrections (review edits, confirmations, flags) are persisted through `review/repository.py` using JSON files on disk. Drift state persists to SQLite. All single-user, no database.

### VERIFY 7: The five-field record definition and every place it is serialized.
**TRUE.** `ExtractedRecord` is defined in `extraction/models.py` (lines 104–132) with fields: `value` (str), `label` (str), `page` (int), `bbox` (dict[str, float]), `source_file` (str). Plus metadata fields `is_reconciliation_candidate` and `footnote_type`. It is serialized in:
- `extraction/repository.py` (disk persistence)
- `extraction/assembler.py` (construction)
- `classification/models.py` (wrapped in `ClassifiedRecord`)
- `review/models.py` (wrapped in `ReviewItem`)
- `audit_trail/models.py` (`SourceComponent` with the same fields)
- `excel_export/provenance.py` (W3C annotation)
- `formula_engine/reader.py` (input)
- `audit_report/compiler.py` (report generation)

### VERIFY 8: Whether CI exists.
**FALSE — no CI exists.** No `.github/`, `.gitlab-ci.yml`, or any CI configuration. Plan.md explicitly says "GitHub Actions (deferred — Phase 5 frozen)."

### VERIFY 9: Current test counts, lint and mypy status.
- **Backend tests:** 82 files, ~500 test cases.
- **Frontend tests:** 18 files.
- **Lint (ruff):** Config in `ruff.toml` (target Python 3.10, line-length 88).
- **Lint (eslint):** Config in `eslint.config.js` for frontend.
- **mypy:** `mypy.ini` configured for strict mode.
- Status: Tests and lint configs exist but **have not been verified to pass** as part of this audit (FN-000 scope is no source changes).

### VERIFY 10: Which P0 bugs listed in `docs/plan.md` are already fixed.
**PARTLY FIXED.** Per `docs/plan.md`:
- ✅ `isFlagged` predicate fix — "done in code"
- ✅ `db_ok` logic inversion — "fixed at `7a256125`"
- ❌ PyMuPDF bbox 1-based index bug — **still open** (coordinate_normalizer.py uses `flat_idx = row_idx * num_cols + col_idx`, needs verification)
- ❌ Docling Y-axis inversion — **still open**
- ❌ PDF render scale mismatch — **still open** (frontend `PDF_RENDER_SCALE = 1.5` vs backend)
- ❌ Canvas `clientWidth` bug — **still open**
- ❌ Auto-lock auto_accepted+matched — needs verification
- ❌ `is_target_metric_candidate_item()` tightening — **still open**
- ❌ `audit_report/compiler.py` isolation violation — needs verification

---

## 10. Feature Existence Checks

### `narrative/` module
**EXISTS** at `backend/app/narrative/`. Contains `differ.py`, `extractor.py`, `models.py`, `repository.py`, `router.py`. Routes are conditionally registered in `main.py` when `ENABLE_NARRATIVE=true` (default). **Not wired to the main extraction pipeline** — it operates independently via its own API endpoints. Frontend has `NarrativeDiffView.tsx` and `RiskRedlineView.tsx` components.

### `ENABLE_NARRATIVE` flag
**EXISTS** in `main.py` line 74: `ENABLE_NARRATIVE = os.getenv("ENABLE_NARRATIVE", "true").lower() in ("true", "1")`. Defaults to `true`.

### 6-tab generator
**EXISTS** at `backend/app/excel_export/multi_statement_generator.py` (1229 lines). Frozen per ADR-003 but still fully wired: has its own API route and the ReviewPage.tsx has TWO "Approve & Generate Complete Financial Model (6 Tabs)" buttons (header button at line ~597 and empty-state button at line ~825).

### `cash_conversion` pack
**EXISTS as enum value** in `ingestion/models.py` line 13: `WorkflowPack = Literal["non_gaap_bridge", "capital_structure", "cash_conversion"]`. In the frontend, `UploadZone.tsx` renders it as a **disabled card** with "Coming Soon" badge. Selecting it is blocked by `disabled: true`. Backend `job_runner.py` returns a skip reason for this pack.

### NetworkX usage
**EXISTS only in `drift/graph.py`**. `HistoricalDriftGraph` class wraps `nx.DiGraph`. Used for append-only cross-year metric definition tracking. Drift data persists to SQLite via `drift/storage.py`. No other module uses NetworkX.

---

## 11. Emoji Icons in Frontend

| Character | Unicode | File | Context |
|---|---|---|---|
| 🏛️ | U+1F3DB | `UploadZone.tsx:24` | Capital Structure pack icon |
| ⓘ | U+24D8 | `JobList.tsx:57` | "Awaiting Review" info hint (renders as `?` on some systems) |

Other icons use `lucide-react` SVG components (proper cross-platform rendering).

---

## 12. Summary for Phase 0 Tickets

| Ticket | Key Findings |
|---|---|
| **FN-001** (Delete dead features) | `narrative/` exists with routes + 2 frontend components. 6-tab generator exists at 1229 LOC with 2 UI buttons. `cash_conversion` is disabled in UI but enum value exists. |
| **FN-002** (Collapse docs) | 15+ docs files exist. `docs/archive/` and `docs/_archive/` both exist. No import-linter configured. |
| **FN-003** (PDF P0 bugs) | 4 open P0 bugs in coordinate handling + 2 in review queue + 1 isolation violation. |
| **FN-060** (Fix visible UI) | `?` glyph is `ⓘ` in `JobList.tsx`. Footer text at `App.tsx:328`. Company selector at `CompanySelector.tsx`. Fiscal period is year-only. No duplicate detection. |
