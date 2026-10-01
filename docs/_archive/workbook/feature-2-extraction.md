# Engineering Workbook — Feature 2: Layout-Aware Extraction

**Module:** Extraction Pipeline (`backend/app/extraction/`)
**Phase:** 1 — Ingestion & Foundation
**Satisfies:** FR2
**Status:** Completed & Audited
**Author:** Antigravity Engineering

---

## 1. Purpose

Feature 2 is the PDF intelligence layer. After Feature 1 accepts and persists a job's PDF to disk, Feature 2 runs a two-parser hybrid extraction pipeline:

1. **Docling** for structural layout parsing (table cells, multi-level headers, footnote markers) using JSON export mode (`row_span`/`col_span`).
2. **PyMuPDF** for bounding-box resolution — mapping each identified value to its exact pixel/coordinate rectangle on a specific page.

Every extracted value is assembled into a `{value, label, page, bbox, source_file}` Pydantic record with a 3-tier confidence score. Items below the auto-accept threshold (`< 0.95`) are flagged, not guessed.

---

## 2. Scope of Change

### Backend — `backend/app/extraction/`

| File | Responsibility |
|---|---|
| `models.py` | `DoclingItem`, `ExtractedRecord`, `ScoredRecord`, `ExtractionSummary`, `NormalizedItem` |
| `docling_parser.py` | Docling structural parse + PyMuPDF fallback (`_parse_pdf_with_pymupdf`); `_is_reconciliation_table()` for reconciliation candidate detection; `_is_noise_cell()` for pre-filtering |
| `assembler.py` | Assembles `DoclingItem` → `ExtractedRecord`; propagates `is_reconciliation_candidate` |
| `coordinate_normalizer.py` | Translates raw PDF coordinates to normalized 0–1000 viewport space; Y-axis inversion for Docling bottom-left origin |
| `confidence.py` | 3-tier confidence scoring; reconciliation table bonus (+0.15); numeric value bonus (+0.05); table-consistency second pass |
| `flagger.py` | Creates `ExtractionSummary` with `parser_used`, `target_metric_found`, confidence-band distribution |

### Key Data Models

```python
class ExtractedRecord(BaseModel):
    value: str                         # raw text exactly as in document (frozen)
    label: str                         # row header / label (frozen)
    page: int                          # 1-indexed page number (frozen)
    bbox: dict                         # {x0, y0, x1, y1} normalized 0–1000 (frozen)
    source_file: str                   # original filename (frozen)
    table_name: str | None = None      # parent table title
    is_reconciliation_candidate: bool = False
    parser_used: Literal["docling", "pymupdf"] = "docling"

class ScoredRecord(ExtractedRecord):
    confidence_score: float            # 0.0–1.0
    confidence_band: ConfidenceBand    # auto_accepted / needs_review / manual_required
    confidence_flags: list[str]        # diagnostic flag list
```

### Confidence Bands

| Band | Threshold | Behaviour |
|---|---|---|
| `auto_accepted` | ≥ 0.95 | Included in draft model without review |
| `needs_review` | 0.65–0.95 | Surfaced in analyst review queue |
| `manual_required` | < 0.65 | Requires analyst manual entry |

---

## 3. Reconciliation Candidate Detection

The `_is_reconciliation_table(table_title, target_metric)` pure function returns `True` if the table title contains (case-insensitive): the target metric name, `"non-gaap"`, `"reconciliation"`, `"adjusted"`, `"non gaap"`, or `"bridge"`. This flag is propagated through the entire extraction pipeline and used to:
- Gate Groq classifier dispatch (only candidates dispatched)
- Gate review queue population (only candidates surface to analyst)
- Apply the +0.15 confidence scoring bonus

---

## 4. PyMuPDF Fallback

When Docling is unavailable or fails, `_parse_pdf_with_pymupdf()` runs as a fallback. Key notes:
- Sets `parser_used = "pymupdf"` on every item produced
- Uses 0-based flat indexing: `flat_idx = (row_idx - 1) * len(row) + (col_idx - 1)`
- Does **not** use Y-axis inversion (PyMuPDF uses top-left origin, matching canvas space)
- Surfaced to the analyst via a dismissible amber warning banner in the Review UI

---

## 5. Known Open Issues

See `docs/issues_charter.md` Steps 1, 5, 6 for tracked bugs in the extraction layer:
- **Step 1 (Tickets 1.1–1.4):** Y-axis inversion not yet applied; PyMuPDF fallback per-cell bbox indexing fix not yet merged.
- **Step 5 (Tickets 5.1–5.2):** `parser_used` field exists on models but `ExtractionSummary` exposure to frontend pending.
- **Step 6 (Tickets 6.1–6.2):** Numeric value bonus and table-consistency second pass not yet implemented.

---

## 6. Test Suite

| File | Coverage |
|---|---|
| `tests/extraction/test_docling_parser.py` | Parser: table detection, noise suppression, reconciliation candidate tagging |
| `tests/extraction/test_assembler.py` | Field propagation, frozen schema preservation |
| `tests/extraction/test_coordinate_normalizer.py` | Coordinate normalization, Y-inversion paths |
| `tests/extraction/test_confidence.py` | Score computation, band classification, bonus signals |
