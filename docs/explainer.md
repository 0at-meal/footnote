# Footnote — Comprehensive Explainer

> **Purpose:** This document is the authoritative onboarding reference for Footnote.
> It covers the project's original intent, all entities and schemas, the complete API surface,
> and the high-level data and compute flow architecture.
> Written from a complete recursive audit of every file in the repository as of 2026-09-02.

---

## 1. Original Intent

Footnote is a **financial filing intelligence tool** for investment bankers and buy-side analysts.

The core value proposition: upload a 10-K or 10-Q PDF → automatically extract the non-GAAP reconciliation table (e.g., *Adjusted EBITDA bridge*) → classify each line item's label using an LLM strictly as a *classifier* (never as a numeric generator) → build a deterministic, provenance-tagged Excel workbook where every derived value is a real Excel formula pointing back to an extracted source cell → provide a human review UI to confirm or flag items → enable a full audit trail linking any generated cell to its exact PDF page and bounding box.

**The nine planned features (from `docs/plan.md`):**

| Feature | Purpose |
|---|---|
| F1 | Multi-file PDF upload & job queueing |
| F2 | Layout-aware extraction (Docling + PyMuPDF) |
| F3 | LLM classification & taxonomy normalization |
| F4 | Deterministic Excel model generation with provenance |
| F5 | Extraction review UI (PDF.js side-by-side) |
| F6 | Audit trail source-chain lookup |
| F7 | Cross-year drift detection (metric redefinition tracking) |
| F8 | Downloadable compliance audit report (PDF) |
| F9 | Evaluation/benchmark harness *(deferred)* |

**Locked design decisions (Constitution + plan.md):**
- Single-user, single-session — no auth, no multi-tenancy
- Extraction runs locally (Docling needs >=2GB RAM; not hosted)
- LLM: Groq API, `openai/gpt-oss-120b`. Classifier output is **label + confidence only** — structurally cannot carry a number
- Excel generation: xlsxwriter, fresh workbook only (never patch existing)
- Graph persistence: NetworkX + SQLite
- Phase-1/2 target metric: **Adjusted EBITDA**

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Backend framework | FastAPI (Python) |
| PDF layout parsing | Docling 2.119 |
| PDF coordinate utility | PyMuPDF 1.28 |
| LLM (classification only) | Groq API (`openai/gpt-oss-120b`) |
| Formula engine | Custom Python (pure functions, deterministic) |
| Excel generation | xlsxwriter 3.2.9 |
| Graph/state persistence | NetworkX 3.6 + SQLite/JSON |
| Frontend framework | React 19 + TypeScript |
| PDF rendering (frontend) | PDF.js (pdfjs-dist 4.10) |
| Audit report export | ReportLab 5.0 + WeasyPrint 69 |
| Type checking | mypy 2.3 (--strict on all non-LLM modules) |
| Linting | ruff 0.16.2, eslint 10 |
| Testing | pytest 9.1, vitest 4.1 |
| Build | Vite 8.2 |

---

## 3. Repository Structure

```
footnote/
├── backend/
│   ├── app/
│   │   ├── main.py                    <- FastAPI app entry point, router registry
│   │   ├── job_runner.py              <- Background pipeline orchestrator (app-root tier)
│   │   ├── ingestion/                 <- Feature 1: upload, validation, job persistence
│   │   ├── extraction/                <- Feature 2: Docling + PyMuPDF parsing
│   │   ├── classification/            <- Feature 3: Groq LLM classifier
│   │   ├── formula_engine/            <- Feature 4: Deterministic formula tree
│   │   ├── excel_export/              <- Feature 4: xlsxwriter workbook generation
│   │   │   ├── generator.py           <- [DEPRECATED] 2-tab generator
│   │   │   ├── multi_year_generator.py <- [DEPRECATED] multi-year 1-sheet generator
│   │   │   └── multi_statement_generator.py <- 6-tab generator (CURRENT DEFAULT, 1,260 lines)
│   │   ├── review/                    <- Feature 5: Review UI state
│   │   ├── audit_trail/               <- Feature 6: Source-chain resolution
│   │   ├── drift/                     <- Feature 7: Cross-year drift detection
│   │   ├── audit_report/              <- Feature 8: Compliance PDF generation (ISOLATION VIOLATION)
│   │   ├── footnote/                  <- Step E (NEW - not in original 8-feature spec)
│   │   └── narrative/                 <- Step G (NEW - not in original spec)
│   ├── data/                          <- Runtime persistence (JSON + SQLite + PDFs + models)
│   └── tests/
├── frontend/
│   └── src/
│       ├── App.tsx                    <- SPA root, state-machine navigation
│       ├── types/
│       └── components/
│           ├── review/ReviewPage.tsx  <- Side-by-side PDF + items review (53KB, 1,400+ lines)
│           ├── audit/AuditTrailView.tsx
│           ├── footnote/
│           └── narrative/             <- (empty - no components yet)
├── eval/                              <- Feature 9 benchmark harness (DEFERRED - no corpus)
└── docs/
    ├── CONSTITUTION.md                <- Fixed project rulebook
    ├── plan.md                        <- Feature spec & phased delivery
    ├── business_alignment.md          <- Business diagnosis + Steps A-K roadmap
    ├── issues_charter.md              <- 34 open bugs across 20 steps
    └── adr/                           <- 4 architectural decision records
```

---

## 4. All Entities and Schemas

### 4.1 Ingestion Layer

**`JobRecord`** (`backend/app/ingestion/models.py`)
```python
class JobRecord(BaseModel):
    job_id: str                    # UUIDv4 (system-generated)
    filename: str                  # Original filename (UTF-8, frozen)
    file_size_bytes: int
    status: JobStatus              # queued | extracting | done | failed
    target_metric: str             # "Adjusted EBITDA" | "EBITDA" | "Net Income" | "Free Cash Flow"
    submitted_at: str              # ISO 8601 UTC
    model_ready: bool = False
    model_skip_reason: str | None
    filing_year: int | None
    company_id: str | None
    session_id: str | None
```

**`CompanyRecord`**
```python
class CompanyRecord(BaseModel):
    company_id: str        # UUIDv4
    name: str
    ticker: str | None
    created_at: str        # ISO 8601 UTC
    job_ids: list[str]
```

**`EdgarFiling`**
```python
class EdgarFiling(BaseModel):
    accession_number: str
    form_type: str             # "10-K", "10-Q"
    filing_date: str
    report_date: str | None
    primary_document: str
    description: str | None
    filing_year: int | None
```

### 4.2 Extraction Layer

**`DoclingItem`** (intermediate)
```python
class DoclingItem(BaseModel):
    value: str
    label: str                  # Hierarchical label path
    page: int                   # 1-indexed
    bbox: DoclingBbox           # Docling-native coordinates
    source_file: str
    table_name: str | None
    is_error: bool = False
    is_reconciliation_candidate: bool = False
    parser_used: Literal["docling", "pymupdf"] = "docling"
    footnote_type: str | None
```

**`ExtractedRecord`** (frozen 5-field canonical schema)
```python
class ExtractedRecord(BaseModel):
    value: str                  # FROZEN - raw extracted text
    label: str                  # FROZEN - structural label path
    page: int                   # FROZEN - 1-indexed page
    bbox: dict[str, float]      # FROZEN - W3C 0-1000 space: {x0, y0, x1, y1}
    source_file: str            # FROZEN - original filename
    is_reconciliation_candidate: bool = False
    footnote_type: str | None
```

**`ScoredRecord`**
```python
class ScoredRecord(BaseModel):
    record: ExtractedRecord
    confidence_score: float         # [0.0, 1.0]
    confidence_band: ConfidenceBand # auto_accepted | needs_review | manual_required
    flags: list[str]
    table_name: str | None
    status: Literal["ok", "extraction_error"] = "ok"
    is_reconciliation_candidate: bool = False
    footnote_type: str | None
```

**`ExtractionSummary`**
```python
class ExtractionSummary(BaseModel):
    total_items: int
    auto_accepted_count: int
    needs_review_count: int
    manual_required_count: int
    extraction_error_count: int
    image_only_page_count: int
    flagged_count: int
    flagged_percentage: float
    passed_threshold: bool          # True if < 15% items outside auto-accept
    filtered_non_reconciliation_count: int
    parser_used: Literal["docling", "pymupdf", "mixed"]
```

### 4.3 Classification Layer

**`ClassifierInputPayload`** (what goes to Groq - no numerics, no bbox, no filename)
```python
class ClassifierInputPayload(BaseModel):
    label: str
    structural_context: str | None
    company_name: str | None
    sic_code: str | None
```

**`ClassifierRawResponse`**
```python
class ClassifierRawResponse(BaseModel):
    label: str
    confidence: float  # [0.0, 1.0]
```

**`TaxonomyItem`**
```python
class TaxonomyItem(BaseModel):
    canonical_name: str
    statement_type: StatementType  # income_statement | balance_sheet | cash_flow | non_gaap_bridge | kpi
    display_order: int
    is_debit: bool
    aliases: list[str]
```

**`ClassifiedRecord`**
```python
class ClassifiedRecord(BaseModel):
    record: ScoredRecord
    normalized_label: str | None
    statement_type: StatementType | None
    taxonomy_status: TaxonomyStatus  # matched | fuzzy_matched | pending_taxonomy_confirmation
    classifier_confidence: float | None
    is_confirmed: bool
    is_target_metric_candidate: bool
```

**`DecisionLogEntry`** (audit proof of numeric-free AI)
```python
class DecisionLogEntry(BaseModel):
    job_id: str
    record_index: int
    timestamp: str
    input_payload: ClassifierInputPayload
    raw_response: ClassifierRawResponse | None
    taxonomy_status: TaxonomyStatus
    resulting_state: str           # "confirmed" | "pending_confirmation" | "classification_error"
    error_detail: str | None
```

### 4.4 Formula Engine Layer

**`FormulaInputNode`**
```python
class FormulaInputNode(BaseModel):
    node_id: str
    normalized_label: str
    value: str
    label: str
    page: int
    bbox: dict[str, float]
    source_file: str
    record_index: int
    is_hardcode: bool = False
    statement_type: StatementType | None
```

**`FormulaNode`**
```python
class FormulaNode(BaseModel):
    node_id: str
    label: str
    node_type: FormulaNodeType  # leaf | aggregate | calculated_root | cross_reference | blank_cell
    operator: str               # "+" | "-" | "root"
    formula_expression: str | None
    source_node: FormulaInputNode | None
    children: list["FormulaNode"]
    statement_type: StatementType | None
    cross_reference_sheet: str | None
    cross_reference_target: str | None
```

**`ComprehensiveModelTree`**
```python
class ComprehensiveModelTree(BaseModel):
    statement_trees: list[StatementTree]  # one per StatementType
    is_valid: bool
    error_message: str | None
```

### 4.5 Excel Export Layer

**`W3CAnnotationRecord`** (provenance record per generated cell)
```python
class W3CAnnotationRecord(BaseModel):
    context: Literal["http://www.w3.org/ns/anno.jsonld"]
    id: str                        # Canonical URN
    type: Literal["Annotation"]
    job_id: str
    sheet_name: str
    cell_coord: str                # A1 notation
    node_id: str
    is_formula: bool
    body: W3CBody                  # {value, label, original_label}
    target: W3CTarget              # {source_file, page, bbox selector}
```

**`WorkbookGenerationResult`**
```python
class WorkbookGenerationResult(BaseModel):
    job_id: str
    file_path: str
    target_metric: str
    sheet_names: list[str]
    total_cells_generated: int
    formula_cells_count: int
    source_cells_count: int
    cell_references: list[CellReference]
    provenance_records: list[W3CAnnotationRecord]
    warnings: list[str]
    is_success: bool
    error_detail: str | None
```

### 4.6 Review Layer

**`ReviewItem`**
```python
class ReviewItem(BaseModel):
    id: str                        # Currently: {job_id}_{idx} - fragile (see fixes.md)
    value: str
    label: str
    page: int
    bbox: dict[str, float]
    source_file: str
    confidence_band: ConfidenceBand
    confidence_score: float
    normalized_label: str | None
    taxonomy_status: str | None
    statement_type: StatementType | None
    status: ReviewStatus           # auto_accepted | needs_review | manual_required | extraction_error | pending_taxonomy_confirmation | flagged | locked
    flags: list[str]
    is_target_metric_candidate: bool
    table_name: str | None
    error_detail: str | None
```

### 4.7 Drift Layer

**`MetricDefinitionNode`** (graph node)
```python
class MetricDefinitionNode(BaseModel):
    node_id: str
    entity: str
    target_metric: str
    filing_year: int
    component_labels: list[str]  # Sorted normalized labels
    created_at: str
```

**`DriftFlag`**
```python
class DriftFlag(BaseModel):
    flag_id: str
    job_id: str
    entity: str
    target_metric: str
    filing_year: int
    added_labels: list[str]
    removed_labels: list[str]
    relabeled_components: list[RelabeledComponent]
    prior_node_id: str
    created_at: str
```

### 4.8 Footnote Module (New - Outside Original Spec)

**`DebtTranche`**, **`DebtSchedule`**, **`LeaseCommitmentYear`**, **`LeaseSchedule`**, **`CustomerConcentration`**, **`ConcentrationSummary`** — all in `backend/app/footnote/models.py`. Track debt instruments, ASC 842 lease waterfalls, and revenue concentration disclosures. Not wired into the automated extraction pipeline.

### 4.9 Narrative Module (New - Outside Original Spec)

**`NarrativeSection`**, **`NarrativeDiff`**, **`RiskFactorRedline`** — in `backend/app/narrative/models.py`. Track MD&A and risk factor text diffs. Not wired into the automated pipeline.

### 4.10 Audit Report Layer

**`CompiledAuditDataset`** — aggregates `ReportMetadata`, `ReconciliationSummaryItem[]`, `ProvenanceMatrixItem[]`, `ManualOverrideItem[]`, `ClassifierAuditSummary`, `DriftAuditSummary`. Rendered to PDF by `audit_report/renderer.py`.

---

## 5. Complete API Endpoints

### 5.1 Upload / Ingestion (`/upload`)

| Method | Path | Description |
|---|---|---|
| POST | `/upload/validate` | Validate PDF files (no persistence) |
| POST | `/upload/jobs` | Submit PDFs, create jobs, trigger pipeline |
| POST | `/upload/jobs/async` | Same, returns 202 |
| GET | `/upload/jobs` | List all persisted jobs |
| GET | `/upload/edgar/search?q=` | Search companies on SEC EDGAR |
| GET | `/upload/edgar/filings/{cik}` | List SEC filings for a CIK |
| POST | `/upload/edgar` | Ingest a SEC filing directly from EDGAR |

### 5.2 Companies (`/companies`)

| Method | Path | Description |
|---|---|---|
| POST | `/companies` | Create a company |
| GET | `/companies` | List all companies with jobs |
| GET | `/companies/{company_id}` | Get company with full job list |
| POST | `/companies/{company_id}/jobs/{job_id}` | Assign job to company |
| POST | `/companies/{company_id}/multi-year-model` | Generate multi-year xlsx (uses deprecated generator) |
| GET | `/companies/{company_id}/multi-year-model/download` | Download multi-year xlsx |
| POST | `/companies/{company_id}/full-model` | Generate 6-tab comprehensive model |
| GET | `/companies/{company_id}/full-model/download` | Download 6-tab model |

### 5.3 Classification (`/classification`)

| Method | Path | Description |
|---|---|---|
| GET | `/classification/{job_id}/decision-log` | Get classifier decision log (audit proof) |

### 5.4 Models / Excel Export (`/models`)

| Method | Path | Description |
|---|---|---|
| POST | `/models/{job_id}/generate` | Generate .xlsx from confirmed review items |
| GET | `/models/{job_id}/download` | Download generated .xlsx |
| GET | `/models/{job_id}/provenance` | All W3C annotation records |
| GET | `/models/{job_id}/provenance/{sheet}/{cell}` | Single cell provenance |

### 5.5 Review (`/review`)

| Method | Path | Description |
|---|---|---|
| GET | `/review/{job_id}/pdf` | Stream source PDF |
| GET | `/review/{job_id}/items` | List all extracted items with review status |
| PATCH | `/review/{job_id}/items/{item_id}/edit` | Edit value or label |
| POST | `/review/{job_id}/items/{item_id}/confirm` | Confirm and lock item |
| POST | `/review/{job_id}/items/{item_id}/flag` | Flag/unflag item |
| POST | `/review/{job_id}/items/{item_id}/unlock` | Unlock a locked item |
| POST | `/review/{job_id}/confirm-batch` | Batch confirm/lock items |
| POST | `/review/{job_id}/bulk-confirm-taxonomy` | Bulk map items to taxonomy |

### 5.6 Audit Trail (`/audit-trail`)

| Method | Path | Description |
|---|---|---|
| GET | `/audit-trail/{job_id}/cell/{sheet}/{coord}` | Resolve source chain by cell |
| GET | `/audit-trail/{job_id}/record?provenance_id=` | Resolve by W3C annotation ID |
| GET | `/audit-trail/{job_id}/provenance/{id:path}` | Resolve by path-based annotation ID |

### 5.7 Drift Detection (`/drift`)

| Method | Path | Description |
|---|---|---|
| POST | `/drift/jobs/{job_id}/evaluate` | Run drift evaluation |
| GET | `/drift/jobs/{job_id}/flags` | Get drift flags |
| GET | `/drift/flags/{job_id}` | Get drift flags (alias) |
| GET | `/drift/history/{entity}/{metric}` | Get historical metric evolution |
| GET | `/drift/graph` | Export full drift graph |
| POST | `/drift/{job_id}/mark-relabeled` | Confirm cosmetic relabeling |
| POST | `/drift/jobs/{job_id}/mark-relabeled` | Same (duplicate route) |

### 5.8 Audit Report (`/api/jobs` and `/jobs`)

| Method | Path | Description |
|---|---|---|
| GET | `/api/jobs/{job_id}/audit-report` | Download compliance PDF |
| GET | `/jobs/{job_id}/audit-report` | Same (alias) |
| GET | `/api/jobs/{job_id}/audit-report/status` | Check report availability |
| GET | `/jobs/{job_id}/audit-report/status` | Same (alias) |

### 5.9 Footnote (`/footnote`)

| Method | Path | Description |
|---|---|---|
| GET | `/footnote/{job_id}/available` | List available footnote categories |
| GET | `/footnote/{job_id}/debt` | Get debt schedule |
| POST | `/footnote/{job_id}/debt/confirm` | Confirm debt tranches |
| GET | `/footnote/{job_id}/lease` | Get ASC 842 lease schedule |
| POST | `/footnote/{job_id}/lease/confirm` | Confirm lease waterfall |
| GET | `/footnote/{job_id}/concentration` | Get customer/supplier concentration |
| POST | `/footnote/{job_id}/concentration/confirm` | Confirm concentration data |

### 5.10 Narrative (`/narrative`)

| Method | Path | Description |
|---|---|---|
| GET | `/narrative/{job_id}/sections` | Get extracted MD&A sections |
| POST | `/narrative/{company_id}/diff` | Compute word-diff between two filings |
| POST | `/narrative/{company_id}/risk-redline` | Compute risk factor redline |

### 5.11 System

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check (data dir + SQLite) |
| GET | `/` | Root status |

---

## 6. High-Level Architecture: Data Flow & Compute Flow

### 6.1 Automated Pipeline (triggered by POST /upload/jobs)

```
User uploads PDF(s)
    |
    v
POST /upload/jobs
    |  ingestion/router.py
    |  -> validate_pdf_bytes()           [ingestion/validation.py]
    |  -> JobRepository.save_job()       [data/jobs.json]
    |  -> CompanyRepository (if company_name given)
    |  -> BackgroundTasks.add_task(process_queued_job)
    |
    v
job_runner.process_queued_job()         [app-root tier]
    |
    +- Stage 1 (Docling): parse_pdf()
    |      docling_parser.py -> DoclingItem[]
    |      Falls back to _parse_pdf_with_pymupdf() if Docling fails
    |
    +- Stage 2 (PyMuPDF): normalize_coordinates()
    |      coordinate_normalizer.py -> NormalizedItem[]
    |      Converts Docling bbox (bottom-left) -> 0-1000 normalized space
    |
    +- Stage 3 (Assembler): assemble_records()
    |      assembler.py -> ExtractedRecord[] (frozen 5-field schema)
    |
    +- Stage 4 (Confidence): score_records()
    |      confidence.py -> ScoredRecord[]
    |      auto_accepted >=0.95, needs_review 0.65-0.95, manual_required <0.65
    |
    +- Stage 5 (Summary): create_extraction_summary()
    |      flagger.py -> ExtractionSummary (15% threshold check)
    |
    +- Stage 6 (Classification):
    |      Filter to is_reconciliation_candidate==True
    |      -> pre_classify_records()     [deterministic alias matching]
    |      -> dispatch_records_to_classifier()  [Groq API - labels only]
    |      -> normalize_records()        [taxonomy matching + fuzzy match]
    |
    +- Stage 7 (Formula Engine):
    |      read_formula_inputs() -> FormulaInputBatch
    |      -> build_comprehensive_model_tree() -> ComprehensiveModelTree
    |
    +- Stage 8 (Excel Export):
           generate_multi_statement_workbook()   <- 6-tab generator (1,260 lines)
           Outputs: data/models/{job_id}_multi_statement.xlsx
    |
    v
repo.update_job_status(done, model_ready=True/False)
```

### 6.2 Human-in-the-Loop Review Flow

```
GET /review/{job_id}/items
    -> ReviewRepository._from_classified_records()
    -> Maps ClassifiedRecord -> ReviewItem
    -> auto_accepted + taxonomy matched items -> status=locked (pre-locked)

Analyst actions:
    PATCH .../edit     -> update value/label
    POST  .../confirm  -> transition to locked
    POST  .../flag     -> mark for attention
    POST  .../confirm-batch -> bulk lock target candidates

POST /models/{job_id}/generate
    -> Reads locked ReviewItems
    -> read_formula_inputs_from_review()
    -> build_comprehensive_model_tree()
    -> generate_multi_statement_workbook()
```

### 6.3 Audit Trail Flow

```
GET /audit-trail/{job_id}/cell/{sheet}/{coord}
    -> AuditTrailResolver.resolve_by_cell()
    -> Looks up W3CAnnotationRecord from provenance.json
    -> Resolves source components from ReviewItems + ExtractionRecords
    -> Returns SourceChainResponse with page, bbox, review_status per component
```

### 6.4 Drift Detection Flow

```
POST /drift/jobs/{job_id}/evaluate
    -> evaluate_job_drift()
    -> Gets locked ReviewItems
    -> Extracts normalized_labels from confirmed items
    -> Loads HistoricalDriftGraph from SQLite
    -> Compares labels against prior-year MetricDefinitionNode
    -> Creates DriftFlag if discrepancy detected
    -> Persists updated graph + drift flags
```

### 6.5 Data Persistence Model

All data is file-based JSON + SQLite. No external database.

```
backend/data/
+-- jobs.json
+-- companies.json
+-- uploads/{job_id}.pdf
+-- results/
|   +-- {job_id}_docling_items.json
|   +-- {job_id}_normalized_items.json
|   +-- {job_id}_extracted_records.json
|   +-- {job_id}_scored_records.json
|   +-- {job_id}_summary.json
|   +-- {job_id}_classified_records.json
|   +-- {job_id}_decision_log.json
|   +-- {job_id}_generation_result.json
|   +-- {job_id}_provenance.json
|   +-- {job_id}_review.json
|   +-- drift_flags_{job_id}.json
+-- models/
|   +-- {job_id}_multi_statement.xlsx
|   +-- {job_id}_multi_year.xlsx
|   +-- {company_id}_multi_year.xlsx
+-- drift.db                           <- SQLite drift graph
```

---

## 7. Frontend Architecture

The React frontend is a **single-page, state-machine-driven application** with no client-side router. Navigation is pure React state:

- `activeReviewJobId !== null` -> render `ReviewPage`
- `activeAuditJobId !== null` -> render `AuditTrailView`
- Otherwise -> render main upload/job list view

**Auto-polling:** Every 3 seconds when jobs are in `queued` or `extracting` status.

**ReviewPage.tsx** (53KB, 1,400+ lines): Side-by-side PDF viewer (PDF.js) and extracted item cards. Tabs: "Flagged" (default) and "All Reconciliation Items."

---

## 8. Confidence Scoring System

| Signal | Delta |
|---|---|
| Base score | +0.50 |
| Label contains `/` (hierarchical path) | +0.20 |
| Value is well-formed numeric | +0.10 |
| `table_name` matches target metric keywords | +0.10 |
| `is_reconciliation_candidate == True` | +0.10 |
| ADR-001 reconciliation bonus | +0.15 |
| `missing_header_hierarchy` (flat label) | -0.15 |
| `low_confidence_value` (non-numeric) | -0.20 |

**Routing bands:**
- >=0.95 -> `auto_accepted`
- 0.65-0.95 -> `needs_review`
- <0.65 -> `manual_required`

---

## 9. Classification Architecture

**Two-level classification (job_runner.py Stage 6):**

1. **Deterministic pre-classification**: exact + normalized string matching against taxonomy aliases. No LLM call.
2. **Groq LLM dispatch**: Only unmatched records. Payload = label + optional context only. Response = label + confidence only. Structurally cannot carry a number.
3. **Taxonomy normalization**: exact match, then fuzzy token-set-ratio (>=0.85). Unmatched -> `pending_taxonomy_confirmation`.

**Isolation guarantee**: `classification/client.py` and `classification/dispatcher.py` are never imported by formula_engine, excel_export, or downstream modules.

---

## 10. Excel Output Architecture

**Current default**: `multi_statement_generator.py` -> 6-tab workbook:

| Tab | Contents |
|---|---|
| `Executive_Summary` | KPIs + cross-sheet links |
| `Income_Statement` | Revenue -> Net Income DAG |
| `EBITDA_Bridge` | Cross-sheet EBIT -> Adjusted EBITDA |
| `Cash_Flow` | Operating CF, CapEx, FCFF |
| `Balance_Sheet` | Assets, Liabilities, Equity |
| `Audit_Trail` | Cell-level provenance log |

**Also available (deprecated but still active in code):**
- `generator.py`: 2-tab (Source_Inputs + Reconciliation) — imported by `audit_report/compiler.py`
- `multi_year_generator.py`: 1-sheet multi-year — called by `company_router.py POST /companies/{id}/multi-year-model`
