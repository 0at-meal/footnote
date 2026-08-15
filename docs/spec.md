# spec.md — Feature 5: Extraction Review UI

**Satisfies:** FR7  
**Phase:** 3 — Human Trust Layer  
**Depends on:** Feature 1 (job record with `job_id` and persisted PDF path); Feature 2 (extraction records with `page`, `bbox`, `source_file`, `confidence_band`, `status`); Feature 3 (`pending_taxonomy_confirmation` records surfaced here for human resolution)  
**Status:** Draft

---

## What This Feature Does

1. **PDF page rendering.** For the extraction record under review, the UI renders the corresponding source PDF page in the browser using PDF.js. The page displayed is determined by the record's `page` field (1-indexed). The PDF binary is served by the FastAPI backend via an API endpoint; the frontend does not access the filesystem directly (CONSTITUTION §3.7). The rendered page must be the exact page from which the item was extracted — not page 1 by default, not the nearest available page.

2. **Extracted item display with bounding-box highlights.** The review UI presents all extracted items for a job alongside the rendered PDF page. Each item is visually highlighted on the PDF canvas at the position corresponding to its `bbox` field. The `bbox` coordinates (W3C Web Annotation–style, normalized 0–1000) are mapped to the rendered canvas coordinates at display time. Every item in the list has exactly one visible bounding-box highlight on the relevant PDF page; selecting an item in the list scrolls the PDF view to that item's page and focuses its highlight. Every extracted item in the job — across all confidence bands and statuses, including `needs_review`, `manual_required`, and `extraction_error` — is reachable from this UI.

3. **Per-item confirm / edit / flag actions.** Each extracted item in the review UI exposes three distinct actions:
   - **Confirm**: marks the item as human-verified. This is a human-only action — no code path may trigger a confirmation without an explicit user gesture (CONSTITUTION §6.6). Confirming a `pending_taxonomy_confirmation` item also resolves its taxonomy state (in coordination with Feature 3's confirmation flow). Confirming an `auto_accepted` item promotes it to explicitly human-verified status.
   - **Edit**: allows the user to correct the item's displayed `value` or `label` field before or instead of confirming. An edit does not automatically confirm — the user must still explicitly confirm after editing. Editing does not alter the original `bbox`, `page`, or `source_file` fields.
   - **Flag**: marks the item as requiring further attention without confirming it. A flagged item remains modifiable. Flagging and confirming are mutually exclusive states — an item cannot be both confirmed and flagged simultaneously.

4. **Confirmed item lock.** Once a user confirms an item, that item transitions to `locked` status. A locked item cannot be altered by any automated pipeline step — no extraction rerun, reclassification, or formula regeneration may silently modify a locked item's `value`, `label`, `normalized_label`, `confidence_band`, or `status` (CONSTITUTION §6.6). The only permitted path back to a modifiable state is an explicit user unlock action in the review UI. The locked state is persisted; a backend restart does not reset it.

---

## What This Feature Does NOT Do

- **Does not run extraction, classification, or formula generation.** This feature is a read-and-act interface over records produced by Features 1–4. It does not trigger any pipeline stage.
- **Does not implement the audit trail source-chain lookup.** Tracing a generated workbook cell back to its source PDF page is Feature 6. This feature operates on raw extraction records, not on workbook cells.
- **Does not render the generated `.xlsx` workbook.** The review UI shows extracted items from the source PDF. It does not display the Excel model.
- **Does not auto-confirm any item.** No item transitions to confirmed status without a user gesture. Items classified `auto_accepted` by Feature 2 are not pre-confirmed — they are presented in the review UI as candidates for human confirmation (CONSTITUTION §6.6).
- **Does not auto-resolve `pending_taxonomy_confirmation` items.** These items are surfaced for the user's explicit decision; they are never silently resolved.
- **Does not perform OCR or re-parse the PDF.** The PDF is rendered for visual reference only. The displayed `value` and `label` fields are what Feature 2 extracted; this UI does not re-extract from the rendered image.
- **Does not modify `bbox`, `page`, or `source_file` fields.** These provenance fields are frozen as extracted by Feature 2. Only `value` and `label` are user-editable in this UI.
- **Does not support multi-user concurrent review.** MVP is single-user, single-session by design (CONSTITUTION §6.10).
- **Does not generate or export any artifact.** The audit report export is Feature 8. This feature writes state changes (confirm/edit/flag/lock) to the backend store only.
- **Does not display the decision log from Feature 3.** The classifier decision log is a separate audit artifact; it is not part of the review UI's item display.

---

## Acceptance Criteria

1. **Every extracted item is reachable from the review UI.** Given a completed job with N extraction records (any combination of `auto_accepted`, `needs_review`, `manual_required`, `extraction_error`, `pending_taxonomy_confirmation`), all N records are listed and individually selectable in the review UI. No item is hidden, filtered out by default, or inaccessible based on its confidence band or status.

2. **Rendered page matches the item's `page` field.** Selecting an item in the review list renders the PDF page number equal to that item's `page` value (1-indexed). Selecting a different item whose `page` differs causes the PDF view to navigate to that item's page. The rendered page is never hardcoded to page 1.

3. **Bounding-box highlight is positioned correctly.** For an item with `bbox: {x0, y0, x1, y1}` (0–1000 normalized), the highlight drawn on the PDF canvas covers the region proportionally equivalent to those coordinates on the rendered page. The mapping is: `canvas_x = (bbox.x / 1000) × canvas_width` and equivalent for y. A highlight that is visibly offset from the actual text location by more than 5% of page width/height is a test failure.

4. **All three actions — confirm, edit, flag — are present and functional per item.** For any item in any non-locked status, the confirm, edit, and flag controls are visible and operable. Triggering confirm transitions the item to `locked`. Triggering edit opens the item's `value` and `label` fields for modification without confirming. Triggering flag transitions the item to `flagged` without confirming. These are the only state transitions available from the UI on non-locked items.

5. **A confirmed item is immediately locked and cannot be silently modified.** After a user confirms an item, its status is `locked` in the backend store. Any subsequent automated pipeline call (e.g., re-extraction, reclassification) that would otherwise update this record must be rejected for the locked item specifically. The rejection must be logged. The item's fields remain byte-identical to their state at the moment of confirmation.

6. **Unlock is an explicit, separate user action.** A locked item cannot return to a modifiable state by any means other than the user explicitly triggering an unlock action in the review UI. A backend restart, a new extraction run, or any other system event must not reset a locked item to unlocked. After unlocking, the item's fields are editable again and its status transitions out of `locked`.

7. **Confirm and flag are mutually exclusive.** No item can carry both `confirmed/locked` and `flagged` status simultaneously. Confirming a flagged item clears the flag and sets the item to `locked`. Flagging a locked item is not permitted — the flag action is not available on locked items.

8. **Editing does not auto-confirm.** After a user edits an item's `value` or `label` and saves the edit, the item's status remains in its pre-edit state (e.g., `needs_review`, `flagged`). A separate confirm action is required to lock it. An edited-but-unconfirmed item is not treated as confirmed by any downstream feature.

9. **`bbox`, `page`, and `source_file` fields are not user-editable.** The review UI does not expose controls to modify these three fields. Their displayed values in the UI are read-only. Any attempt to modify them via the API outside the UI is also rejected (these fields are frozen per CONSTITUTION §2.3, NFR7).

10. **Performance: any item in a 200-page 10-K job is reachable within 10 seconds.** From the moment a user selects an item in the review list to the moment the correct PDF page is rendered with the bounding-box highlight visible, the elapsed time must not exceed 10 seconds on the local machine. This applies to any item in the job, not just the first one.

---

## Dependencies / Interfaces with Other Features

### Consumed from Feature 1
- **`job_id`**: scopes which extraction records are loaded into the review UI.
- **PDF file path**: the backend uses the persisted job record to locate and serve the source PDF binary to the frontend via API.

### Consumed from Feature 2
- **All extraction records** for the job: `value`, `label`, `page`, `bbox`, `source_file`, `confidence_band`, `status`. All fields are read for display; only `value` and `label` may be written back (on edit). `bbox`, `page`, `source_file` are strictly read-only in this feature.
- **Contract:** The frozen field names (`value`, `label`, `page`, `bbox`, `source_file`) must remain unchanged (CONSTITUTION §2.3, NFR7).

### Consumed from Feature 3
- **`pending_taxonomy_confirmation` records**: surfaced here for human resolution. Confirming such an item in the review UI must also trigger the taxonomy confirmation flow (adding the label to the seed taxonomy if it was unrecognized), in coordination with Feature 3's state model.
- **`normalized_label`**: displayed alongside `label` for confirmed records, to give the reviewer context on how the item was classified.

### Exposed for Feature 4
- **Locked items**: Feature 4's formula engine reads only confirmed records. The `locked` status set by this feature is the gate Feature 4 relies on. Any record that is not `locked` is not available to the formula engine.
- **Edited `value` / `label`**: if a user edits and then confirms an item, the edited fields are what Feature 4 reads — not the original Feature 2 values.

### Exposed for Feature 6
- **`flagged` / `locked` status per item**: Feature 6's audit trail lookup displays verified/flagged status per source component. The status set in this feature is the authoritative source for those indicators.

### Must Not Break
- The frozen field names (`value`, `label`, `page`, `bbox`, `source_file`) must not be renamed or restructured by this feature (CONSTITUTION §2.3).
- `lib/pdf/` (PDF.js integration) may only communicate with `components/review/`. It must not reach into backend modules directly (CONSTITUTION §3.7).
- The confirmed/locked state transition is human-only, permanently. No test harness, no CI script, no pipeline step may programmatically confirm an item to make a run appear clean (CONSTITUTION §6.6, §6.11).

---

## Predictable Edge Cases

| # | Edge Case | Required Behavior |
|---|---|---|
| EC-1 | An item has `status: extraction_error` (Feature 2 could not resolve its bbox or value). | The item is listed in the review UI with its error detail displayed. The confirm action is not available for `extraction_error` items — the user can only flag them or manually enter a corrected value via the edit action, after which confirm becomes available. |
| EC-2 | An item's `page` value is greater than the total number of pages in the PDF (data integrity violation from Feature 2). | The item is listed in the review UI. Attempting to render its page displays an inline error: "Page [N] not found in document." The item remains selectable and its other fields are displayed. The PDF view shows the error state, not a blank page. |
| EC-3 | Two items have identical `bbox` coordinates on the same page (e.g., a repeated summary value — Feature 2 EC-6). | Both items are listed separately. Both produce overlapping highlights on the PDF canvas. The highlights are rendered as visually stacked layers; selecting each item focuses its own highlight. No deduplication occurs. |
| EC-4 | A user edits an item's `label` to an empty string. | The edit is rejected inline with a validation error: "Label cannot be empty." The item's `label` field is not updated. |
| EC-5 | A user attempts to confirm a `pending_taxonomy_confirmation` item whose label is still unrecognized. | Confirming the item prompts the user to also confirm addition of the label to the seed taxonomy. The item is not locked until both the item confirmation and the taxonomy addition are accepted. If the user declines the taxonomy addition, the item remains in `pending_taxonomy_confirmation`. |
| EC-6 | A backend restart occurs while items are in `locked` status. | After restart, all `locked` items remain `locked`. The locked state is persisted in the backend store (not held in memory). The review UI reflects the correct locked state on reload. |
| EC-7 | The PDF binary is unavailable when the review UI attempts to render a page (e.g., file moved or deleted). | The item list loads and items are selectable. The PDF canvas displays an inline error: "Source PDF unavailable." The bounding-box highlight cannot be shown, but the item's metadata (`value`, `label`, `page`, `bbox`) is still displayed in the item panel. The user can still confirm, edit, or flag the item. |
| EC-8 | A user flags an item that was previously `auto_accepted` by Feature 2. | The item transitions to `flagged` status. Its `confidence_band` field from Feature 2 is not modified — it still records `auto_accepted` as the extraction band. `flagged` is a review-layer status, separate from the extraction confidence band. |
| EC-9 | The user submits an edit to `value` that is identical to the current stored `value` (a no-op edit). | The edit is accepted without error. No state change occurs beyond recording the edit action timestamp. The item's status does not change. |
| EC-10 | A new extraction run is triggered for a job that has locked items. | The locked items are not overwritten by the new extraction output. The new extraction run produces new candidate records for any non-locked items. Locked items remain at their confirmed state; the new candidates are presented in the review UI alongside them as distinct, unconfirmed records. |
