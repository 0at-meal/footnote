# Engineering Workbook — Feature 5: Extraction Review UI

**Module:** Review Pipeline (`backend/app/review/`) + Frontend (`frontend/src/components/review/`)
**Phase:** 3 — Human Trust Layer
**Satisfies:** FR7
**Status:** Completed
**Author:** Antigravity Engineering

---

## 1. Purpose

Feature 5 is the human-in-the-loop review interface. It presents extracted and classified items to the analyst in a side-by-side layout: the source PDF rendered via PDF.js on one side, and the extracted reconciliation bridge items on the other — each item highlighted to its source bounding box.

---

## 2. Scope of Change

### Backend — `backend/app/review/`

| File | Responsibility |
|---|---|
| `models.py` | `ReviewItem`, `ReviewStatus` enum, `ReviewItemsResponse` |
| `repository.py` | `ReviewRepository` — converts classified records to review items; pre-locks `auto_accepted + taxonomy_matched`; filters to reconciliation candidates only |
| `router.py` | `GET /review/{job_id}/items`, `POST /review/{job_id}/confirm/{item_id}`, `POST /review/{job_id}/confirm-batch` |

### Frontend — `frontend/src/components/review/`

| File | Responsibility |
|---|---|
| `ReviewPage.tsx` | Main review component: two-tab layout (Flagged / All Reconciliation), PDF.js viewer, item list, bounding-box overlay |
| `ReviewPage.css` | Styles: split-screen layout, tab bars, status badges, bbox highlight overlay |
| `ReviewPage.test.tsx` | Component tests: tab defaults, filter behaviour, button visibility |

---

## 3. Key Design Decisions

### Review Queue Scoping
- Only `is_reconciliation_candidate == True` items enter the review queue.
- Items with `confidence_band == auto_accepted` AND `taxonomy_status == matched` are pre-locked on creation — they never appear in the Flagged tab.
- Default tab: **Flagged** (items with status in `{needs_review, manual_required, pending_taxonomy_confirmation, extraction_error, flagged}`).
- Second tab: **All Reconciliation Items** (all candidates, including locked).

### `isFlagged` Predicate (Fixed per `issues_charter.md` Ticket 3.4)
```ts
const isFlagged = (item: ReviewItem) =>
  item.status === 'needs_review' ||
  item.status === 'manual_required' ||
  item.status === 'extraction_error' ||
  item.status === 'pending_taxonomy_confirmation' ||
  item.status === 'flagged'
```
The raw `confidence_score < 0.95` condition was removed — status-based only.

### 1-Click Batch Approval
`POST /review/{job_id}/confirm-batch` (no body) locks all target candidates with status not `extraction_error` in one request. Frontend button: **"Approve All & Generate Model"**.

### PDF Rendering
- PDF.js renders source pages at `PDF_RENDER_SCALE = 1.5` (shared constant from `frontend/src/lib/pdf/renderer.ts`).
- Canvas dimensions read via `getBoundingClientRect()` (not `clientWidth`) for accurate 1:1 bbox mapping.

---

## 4. Known Open Issues

See `docs/issues_charter.md`:
- **Step 1 (Ticket 1.1–1.4):** Bbox highlights may be at wrong positions (Y-inversion bug, PyMuPDF cell index bug). Not yet fixed.
- **Step 9 (Ticket 9.1):** Empty Flagged tab does not show "Generate Model" button inline. Pending.
- **Step 17 (Ticket 17.1):** No pulsing progress indicator on Extracting status badge. Pending.
- **Step 18 (Ticket 18.1):** `alert()` on confirmation error not yet replaced with inline error state. Pending.
- **Step 19 (Tickets 19.1–19.2):** Target metric mismatch not surfaced to analyst. Pending.

---

## 5. ReviewItem Status Lifecycle

```
pending (initial)
    │
    ├── auto_accepted    → (pre-locked if taxonomy_matched) → locked
    ├── needs_review     → analyst confirms → locked
    ├── manual_required  → analyst enters value → locked
    ├── pending_taxonomy_confirmation → analyst confirms taxonomy → locked
    └── extraction_error  → analyst overrides → locked
```

`locked` items cannot be altered by any code path without an explicit user unlock action (CONSTITUTION §6.6).

---

## 6. Test Suite

| File | Coverage |
|---|---|
| `tests/review/test_repository.py` | Pre-lock on auto-accepted+matched; reconciliation-only filtering; content-based ID generation |
| `tests/review/test_router.py` | Confirm single item, confirm-batch, 404 on missing job |
| `frontend/src/components/review/ReviewPage.test.tsx` | Flagged tab default, tab switching, Approve All button visibility |
