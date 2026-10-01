# Engineering Workbook — Feature 7: Cross-Year Drift Detection

**Module:** Drift Detection (`backend/app/drift/`)
**Phase:** 4 — Extensibility & Compliance Output
**Satisfies:** FR9 (partially — see open items)
**Status:** Completed
**Author:** Antigravity Engineering

---

## 1. Purpose

Feature 7 provides cross-year definitional consistency tracking: comparing how a company's non-GAAP reconciliation bridge components change year-over-year. The core output is a `DriftSummary` for each company, enumerating added, removed, and relabeled items between consecutive fiscal years.

---

## 2. Scope of Change

### Backend — `backend/app/drift/`

| File | Responsibility |
|---|---|
| `models.py` | `DriftEdge`, `DriftChangeType`, `DriftSummary`, `DriftGraph`, `DriftBaseline` |
| `detector.py` | `detect_drift(baseline_items, current_items)` — pure function; normalized label comparison |
| `service.py` | `DriftService` — auto-resolves company and filing_year from `JobRecord`; builds cumulative drift graph |
| `repository.py` | `DriftRepository` — persists `DriftGraph` to `data/drift/{company_id}.json` |
| `router.py` | `GET /drift/{company_id}` — returns full drift graph; `POST /drift/{company_id}/baseline` |

---

## 3. Key Data Models

```python
class DriftChangeType(str, Enum):
    added = "added"
    removed = "removed"
    relabeled = "relabeled"     # from_label + to_label populated
    split = "split"
    merged = "merged"

class DriftEdge(BaseModel):
    year_from: int
    year_to: int
    item_normalized_label: str
    change_type: DriftChangeType
    from_label: str | None = None   # for relabeled edges
    to_label: str | None = None     # for relabeled edges
    value_delta: float | None = None  # numeric difference if both years have value
    notes: str | None = None

class DriftSummary(BaseModel):
    company_id: str
    year_from: int
    year_to: int
    edges: list[DriftEdge]
    new_items: list[str]
    removed_items: list[str]
    relabeled_items: list[tuple[str, str]]
```

---

## 4. Key Design Decisions

### Pure Detector
`detect_drift(baseline_items, current_items)` is a pure function (`baseline: list[str], current: list[str]`) using normalized labels (lowercase, stripped punctuation, canonical taxonomy). No I/O, no state.

### Economic vs. Cosmetic Distinction (see `business_alignment.md` Step J)
`DriftChangeType.relabeled` is currently triggered on any label text change between years. **A future improvement** (Step J) will distinguish economic substance changes from cosmetic renames (e.g., "SBC" → "Share-Based Compensation" = cosmetic; "SBC" → "Impairment" = economic). Ticket: `issues_charter.md` Step 20 analogue in `business_alignment.md`.

### Company-Resolved Drift
`DriftService` calls `CompanyRepository.get(company_id)` and uses `JobRecord.filing_year` (set by user at upload) to order the comparison. No manual year specification needed in the drift API call.

---

## 5. Integration with Multi-Year Model

The multi-year workbook generator (`excel_export/multi_year_generator.py`) calls the drift service during generation to annotate changed line items with an asterisk and a cell comment: `"Changed from FY{year}: {from_label}"`.

---

## 6. Known Open Issues

See `docs/business_alignment.md` Step J:
- Relabeled change type does not yet distinguish cosmetic vs. economic substance changes. Currently all label changes are tagged `relabeled` regardless of semantic equivalence.

---

## 7. Test Suite

| File | Coverage |
|---|---|
| `tests/drift/test_detector.py` | Added/removed/relabeled detection; normalization; determinism |
| `tests/drift/test_service.py` | Company resolution, filing_year ordering, multi-year graph accumulation |
| `tests/drift/test_repository.py` | Persistence, read-after-write, missing company 404 |
