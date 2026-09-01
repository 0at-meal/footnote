# Engineering Workbook — Feature 6: Audit Trail Lookup

**Module:** Audit Trail (`backend/app/audit_trail/`) + Frontend (`frontend/src/components/audit/`)
**Phase:** 3 — Human Trust Layer
**Satisfies:** FR8
**Status:** Completed
**Author:** Antigravity Engineering

---

## 1. Purpose

Feature 6 enables source-chain resolution: a user selects a cell in the generated workbook (by sheet name + cell coordinate) and receives the full chain of documents, pages, and bounding boxes that contributed to that cell's value. Every source-chain component carries its review/verification status.

---

## 2. Scope of Change

### Backend — `backend/app/audit_trail/`

| File | Responsibility |
|---|---|
| `models.py` | `SourceChainComponent`, `SourceChain`, `ProvenanceRecord`, `AuditTrailLookupRequest` |
| `resolver.py` | `resolve_source_chain(job_id, sheet_name, cell_ref)` — looks up W3C Annotation records, resolves to review items via content-hash ID matching |
| `router.py` | `POST /audit/{job_id}/lookup` — accepts `{sheet_name, cell_ref}`, returns `SourceChain` |

### Frontend — `frontend/src/components/audit/`

| File | Responsibility |
|---|---|
| `AuditTrailView.tsx` | Main audit component: sheet selector (derived from provenance records), cell reference input, source chain display, PDF viewer with bbox highlight |

---

## 3. Key Design Decisions

### Content-Based Review Item ID Matching (per `issues_charter.md` Ticket 12.1)
The resolver looks up review items by content-based hash (source_file + page + bbox) rather than sequential index. This prevents audit trail cross-references from breaking when classification is re-run or record order changes:

```python
def _make_review_id(job_id: str, source_file: str, page: int, bbox: dict) -> str:
    key = f"{job_id}:{source_file}:{page}:{bbox.get('x0',0):.0f}:{bbox.get('y0',0):.0f}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
```

### Dynamic Sheet Selector (per `issues_charter.md` Ticket 8.1)
Sheet options are derived from the loaded provenance records:
```ts
const availableSheets = [...new Set(provenanceRecords.map(r => r.sheet_name))].sort()
```
Not hardcoded to `["Reconciliation", "Source_Inputs"]`.

### Empty State (per `issues_charter.md` Step 4)
When no provenance records exist (model not yet generated), the view shows:
1. A numbered 4-step checklist guiding the user to the Review tab.
2. A "Go to Review Tab →" button.
3. A "↻ Refresh" button to re-poll provenance without page reload.

### Audit PDF Download Gate
The "Export Audit PDF" button is gated on `job.model_ready`. When `model_ready == false`, the button renders as disabled with a tooltip: *"Generate a model first: go to Review and click 'Approve & Generate'"*.

---

## 4. Known Open Issues

See `docs/issues_charter.md`:
- **Step 8 (Ticket 8.1):** Dynamic sheet derivation may not yet be implemented — verify against current codebase.
- **Step 2 (Tickets 2.1–2.4):** Audit PDF download gating and status polling may be partially complete.

---

## 5. Source Chain Resolution Flow

```
POST /audit/{job_id}/lookup
  { sheet_name: "Reconciliation", cell_ref: "C5" }
        │
        ▼
ModelRepository.get_provenance_records(job_id)
  → find W3CAnnotationRecord for Reconciliation!C5
        │
        ▼
Extract source references from annotation (source_file, page, bbox)
        │
        ▼
Build content-hash → look up matching ReviewItem
        │
        ▼
Return SourceChain {
  cell_ref: "C5",
  formula: "=Source_Inputs!F5",
  components: [
    { source_file: "AAPL_2024.pdf", page: 47, bbox: {...},
      label: "Stock-Based Compensation",
      normalized_label: "Stock-Based Compensation",
      value: "3,421",
      review_status: "locked",
      confirmed_at: "2026-08-12T..." }
  ]
}
```

---

## 6. Test Suite

| File | Coverage |
|---|---|
| `tests/audit_trail/test_resolver.py` | Source chain resolution, content-hash ID matching, missing cell handling |
| `tests/audit_trail/test_router.py` | Lookup endpoint, 404 on missing job/model |
