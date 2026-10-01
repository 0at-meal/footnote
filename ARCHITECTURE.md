# Footnote Architecture

Footnote extracts company-reported non-GAAP reconciliation bridges (Adjusted EBITDA, Free Cash Flow, etc.) from SEC filings and compiles them into formula-native Excel workbooks where every number traces back to its exact source coordinates.

---

## 1. Pipeline Flow

The primary workflow (`non_gaap_bridge`) executes in discrete stages:

```
[PDF / EDGAR Source]
        │
        ▼
 1. Ingestion (`app/ingestion`)
    • Validate file format, compute content hash, record JobRecord in data store
        │
        ▼
 2. Layout-Aware Extraction (`app/extraction`)
    • Docling parses document structure and tables
    • PyMuPDF normalizes cell bounding boxes (0–1000 W3C Web Annotation space)
    • Bounded to reconciliation candidate tables
    • Outputs 5-field ExtractedRecord: {value, label, page, bbox, source_file}
        │
        ▼
 3. Classification & Normalization (`app/classification`)
    • Level 1: Deterministic alias matching against Master Financial Taxonomy (60–80 items)
    • Level 2: LLM classifier (Groq) for genuine unknowns only (labels only, zero numeric input/output)
    • Assigns ConfidenceBand: auto_accepted (>=0.95), needs_review (0.65–0.95), manual_required (<0.65)
        │
        ▼
 4. Human Trust Layer (`app/review`, frontend)
    • Auto-accepted items pre-locked
    • Flagged/uncertain items surfaced in side-by-side review UI with PDF highlight
    • Review actions: confirm, edit label, flag
        │
        ▼
 5. Deterministic Formula Engine (`app/formula_engine`)
    • Pure mathematical AST tree construction (`build_formula_tree`)
    • Zero I/O, zero wall-clock, zero randomness
        │
        ▼
 6. Excel Model Generation (`app/excel_export`)
    • Fresh `.xlsx` generation using xlsxwriter (IB convention: blue hardcode, black formula)
    • Source_Inputs tab + Reconciliation tab with live formulas
    • Provenance embedded via cell comments and W3C Web Annotation records
        │
        ▼
 7. Audit & Compliance (`app/audit_trail`, `app/audit_report`, `app/drift`)
    • Interactive cell-to-source PDF coordinate lookup
    • Downloadable compliance PDF audit report
    • Cross-year metric definition drift detection
```

---

## 2. Module Boundaries & Dependency Rules

Module boundaries are load-bearing isolation constraints:

```
main
 ├── ingestion ──► extraction ──► classification ──► formula_engine ──► excel_export
 │       │              │               │                    │                │
 │       ▼              ▼               ▼                    │                ▼
 │    review ◄──────────┴───────────────┘                    │           audit_trail
 │       │                                                   │                │
 │       ▼                                                   │                ▼
 │     drift                                                 └─────────► audit_report
 └────────────────────────────────────────────────────────────────────────────┘
```

**Boundary Rules:**
1. `classification/` (LLM client and dispatcher) is isolated from downstream modules.
2. `formula_engine/` functions are pure: no I/O, no network, no clock, no random, no global mutable state.
3. `extraction/` produces frozen 5-field `ExtractedRecord` schemas; it does not know about formula trees or Excel sheets.
4. `excel_export/` creates workbooks from scratch via xlsxwriter; it never modifies existing files.

---

## 3. Core Invariants

- **I1. Zero-Numeric Classifier:** The classifier and any LLM never read or write numeric values. Classification outputs are strictly constrained to taxonomy labels. Structural result types contain no numeric fields.
- **I2. Pure Formula Engine:** The formula engine is a pure mathematical function. Identical inputs always produce identical formula trees and outputs, with no I/O, no randomness, and deterministic sorting.
- **I3. No Silent Failures:** Every skipped, failed, or ambiguous item carries an explicit reason (`model_skip_reason` or equivalent error detail) visible to the user. Errors are never swallowed to keep pipelines artificially green.
- **I4. Complete Provenance:** Every extracted number carries an exact locator to its source (`page`, `bbox`, `source_file`, transitioning to discriminated union `Locator` after FN-023).
- **I5. Native Formulas & Numeric Types:** Excel numbers are written as IEEE numbers, never text strings. Derived cells contain live Excel formulas (`SUM`, arithmetic). Input numbers are never overwritten by calculated values.
- **I6. Zero Content Egress:** Raw document content never appears in telemetry, external tracking, or unauthorized third-party services.

---

## 4. Testing, Linting & Evaluation

### Backend
```bash
cd backend

# Run pytest test suite (480+ tests)
pytest

# Type checking (mypy strict mode)
mypy app

# Code linting & formatting (ruff)
ruff check .
ruff format --check .
```

### Frontend
```bash
cd frontend

# Run unit & component tests (vitest)
npm test

# Type checking & production build
npm run build

# ESLint
npm run lint
```

### Evaluation Harness
```bash
# Evaluation runner (dev corpus)
python -m pytest backend/tests/eval/test_runner.py
```
