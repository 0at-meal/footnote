# spec.md — Feature 3: Classification & Normalization

**Satisfies:** FR3  
**Phase:** 2 — Core Trust Loop  
**Depends on:** Feature 2 (a completed job with assembled, confidence-scored extraction records must exist before this feature runs)  
**Status:** Completed

---

## What This Feature Does

1. **Classifier dispatch.** For each extraction record produced by Feature 2, assembles a classifier input payload consisting of the record's raw `label` field and its surrounding structural context (adjacent column/row headers from the Docling parse). The numeric `value` field and any raw filing text are excluded from the payload. The payload is sent to the Groq API (`openai/gpt-oss-120b`). Requests are batched and throttled to remain within Groq's published free-tier limits at all times: ≤ 30 RPM, ≤ 1,000 RPD, ≤ 8,000 TPM, ≤ 200,000 TPD. A 429 response triggers a retry with exponential backoff; no classification result is discarded or fabricated on a 429.

2. **Structurally numeric-free return type.** The classifier's response schema is defined such that it structurally cannot carry a numeric field — not by runtime validation alone, but by the shape of the declared response type (CONSTITUTION §6.2). The only fields the classifier may return are a textual `label` and a `confidence` score (0.0–1.0). Any response that does not conform to this schema is rejected as malformed and logged as a classification error; it does not propagate to downstream steps.

3. **Taxonomy check.** The returned `label` is checked by exact string match against the active seed taxonomy. The seed taxonomy is a persisted, human-curated list of normalized non-GAAP reconciliation item names (e.g., Stock-Based Compensation, Lease Adjustments, Litigation Charges). A match means the label is a recognized taxonomy entry. A non-match means the label is unrecognized. The taxonomy list itself is not modified by this step.

4. **Unrecognized label queuing.** A label that does not match any taxonomy entry is assigned the state `pending_taxonomy_confirmation`. The record is held in this state and is not assigned a `normalized_label`. It cannot advance to a confirmed normalized label by any automated path — only by explicit human confirmation. Records in `pending_taxonomy_confirmation` are surfaced for user action; they are never silently auto-accepted, merged with a similar-sounding taxonomy entry, or dropped.

5. **Normalized label attachment.** When a label is confirmed — either by matching the existing taxonomy in step 3, or by a human confirming an unrecognized label in step 4 — the confirmed taxonomy label is attached to the record as a new field: `normalized_label` (type `str`). The original `label` field from Feature 2's record is preserved unchanged. `normalized_label` is the only field this feature writes to an existing record's schema; no other Feature 2 field is modified.

6. **Decision log.** Every classifier call is written to a structured, append-only decision log in machine-readable format (newline-delimited JSON). Each log entry covers exactly one classifier call and contains: the input payload sent to the classifier, the raw response received (label + confidence), the taxonomy-check outcome (matched / unrecognized), and the resulting record state. The log is persisted across sessions, retrievable via an API endpoint without any UI dependency, and is the auditable proof that the classifier never produced a numeric output.

---

## What This Feature Does NOT Do

- **Does not compute, derive, or infer any numeric value.** The classifier's output is a label and a confidence score only. No numeric field from any extraction record is touched, transformed, or routed through the classifier at any point (CONSTITUTION §6.1, §6.2).
- **Does not auto-merge or fuzzy-match unrecognized labels.** An unrecognized label that is "close" to a taxonomy entry (substring match, edit-distance match, semantic similarity) is still treated as unrecognized and queued for human confirmation (CONSTITUTION §6.3).
- **Does not modify or recalibrate the confidence bands from Feature 2.** The 0.95/0.65 extraction confidence thresholds belong to Feature 2's output. This feature assigns its own classifier `confidence` field to the response; these are separate, non-interchangeable values.
- **Does not expand the seed taxonomy automatically.** New entries are added to the taxonomy only when a human explicitly confirms an unrecognized label. The classifier cannot propose or vote a new label into the taxonomy.
- **Does not perform extraction.** All records this feature processes were assembled and scored by Feature 2. This feature reads those records; it does not re-parse the PDF.
- **Does not render a review UI.** Items in `pending_taxonomy_confirmation` state are surfaced for human action; the UI for that action belongs to Feature 5.
- **Does not generate formulas or Excel output.** That is Feature 4, which reads the confirmed, normalized labels this feature produces.
- **Does not send raw filing text, filenames, page numbers, bounding boxes, or numeric values to the Groq API.** The outbound payload is structurally constrained to textual label and structural context only (CONSTITUTION §6.5).
- **Does not implement authentication or multi-user taxonomy isolation.** Taxonomy is shared and single-session by design (CONSTITUTION §6.10).
- **Does not handle non-Groq classifier backends.** The Ollama/local-inference path is a documented future option (CONSTITUTION §4.3); it is not implemented in this feature.

---

## Acceptance Criteria

1. **Classifier calls stay within Groq free-tier limits.** Under a realistic batch (a full 10-K filing's extracted records sent in one job), the batching and throttling logic does not exceed 30 RPM, 1,000 RPD, 8,000 TPM, or 200,000 TPD — whichever is hit first. Compliance is verifiable by inspecting the decision log's timestamps and token counts against the published caps.

2. **No numeric field appears in any classifier request or response.** Inspection of any entry in the decision log must show: (a) no `value` field or raw numeric string in the input payload, and (b) no numeric field in the recorded response. This must hold for every entry in the log — not just a sampled subset.

3. **Malformed classifier responses are rejected and logged, never propagated.** If the Groq API returns a response that does not conform to the declared schema (e.g., contains a numeric field, missing `label`, unparseable JSON), the response is discarded and a classification error is recorded for that item. The item is not assigned a `normalized_label` from a malformed response.

4. **Taxonomy match is by exact string comparison only.** Given a returned label of `"Stock Based Compensation"` and a taxonomy entry of `"Stock-Based Compensation"`, the result is unrecognized, not matched. Matching is case-sensitive exact string equality against the persisted taxonomy at the time of classification. No normalization, stemming, or fuzzy comparison occurs.

5. **Unrecognized labels are never auto-accepted.** No record in `pending_taxonomy_confirmation` state may transition to a confirmed `normalized_label` without a human action recorded in the decision log. This must hold even if the same unrecognized label appears multiple times across records in the same job — each instance remains pending independently until confirmed.

6. **`normalized_label` does not overwrite `label`.** After Feature 3 completes for any record, that record's `label` field is byte-identical to what Feature 2 wrote. `normalized_label` is a separate field. A record that is still pending confirmation has no `normalized_label` field (or an explicit null) — it does not inherit the raw `label` as a default.

7. **Decision log is complete and retrievable without the UI.** Every classifier call made during a job produces exactly one log entry. The log for a completed job is retrievable via an API endpoint. The log persists across backend restarts. A log entry's fields include: input payload, raw Groq response, taxonomy-check outcome, and resulting record state — all present and non-empty.

8. **429 handling preserves all items.** If a Groq 429 is received, the affected batch is retried with exponential backoff. No item is skipped, marked as classified, or assigned an error state solely because of a rate-limit response. Items remain in their pre-classification state until a successful response is received or a non-retryable error occurs.

9. **Classification does not run on `extraction_error` records.** Records from Feature 2 with `status: extraction_error` are excluded from classifier dispatch. They are not sent to Groq and do not appear in the decision log as classifier calls. They remain in their error state unchanged.

10. **Determinism within a session.** Given the same set of extraction records and the same Groq responses (i.e., same model version returning the same labels), the output — which records are confirmed, which are pending, what `normalized_label` values are assigned — is identical across two runs on the same input. No random ordering, no clock-dependent branching in the classification logic (CONSTITUTION §6.7, NFR1).

---

## Dependencies / Interfaces with Other Features

### Consumed from Feature 1
- The `job_id` and `target_metric` fields on the job record are used to scope which extraction records belong to which job. No other Feature 1 contract is touched.

### Consumed from Feature 2
- **Input:** The 5-field extraction record Pydantic model (`value`, `label`, `page`, `bbox`, `source_file`) plus the `confidence_band` and `status` fields Feature 2 appended. All fields are read-only from this feature's perspective.
- **Contract:** The `label` field is the classifier input signal. It must not be modified. The `value` field must not be sent to the classifier.
- **Precondition:** Feature 3 only processes records where `status` is one of `auto_accepted` or `needs_review`. Records with `status: manual_required` or `status: extraction_error` are excluded from classifier dispatch (they require human input at the Feature 5 review stage before classification is meaningful).

### Exposed for Feature 4
- **Output:** The `normalized_label` field on each confirmed record. Feature 4's formula engine reads only confirmed records — records still in `pending_taxonomy_confirmation` are not available to Feature 4 until confirmed.
- **Contract:** `normalized_label` is a non-empty string, exactly matching a taxonomy entry. Feature 4 may treat any record with a populated `normalized_label` as authoritative without re-validating it.

### Exposed for Feature 5
- **Output:** The set of records in `pending_taxonomy_confirmation` state, surfaced for human review and confirmation.
- **Output:** The decision log endpoint, which Feature 5's review UI may link to for audit display.

### Exposed for Feature 8
- **Output:** The decision log, which the audit report uses as evidence that no classifier output populated a numeric field.

### Must Not Break
- The frozen schema field names (`value`, `label`, `page`, `bbox`, `source_file`) must remain unchanged in any record this feature reads or writes to (CONSTITUTION §2.3, NFR7).
- The `classification/` module must not import from `extraction/` (CONSTITUTION §3.2), and must not import from `formula_engine/` or `excel_export/` (CONSTITUTION §3.3).

---

## Predictable Edge Cases

| # | Edge Case | Required Behavior |
|---|---|---|
| EC-1 | Groq returns a `label` that is an empty string. | Treated as a malformed response. The item is not assigned a `normalized_label`. A classification error is logged. |
| EC-2 | Groq returns a `confidence` value outside 0.0–1.0 (e.g., `1.5`, `-0.1`). | Treated as a malformed response. Same handling as EC-1. The out-of-range value is recorded in the decision log as received. |
| EC-3 | The same unrecognized label appears in 50 records across one job. | Each of the 50 records is independently placed in `pending_taxonomy_confirmation`. When a human confirms the label once (adding it to the taxonomy), subsequent records may use the now-confirmed taxonomy entry — but no record is retroactively confirmed without at least one human action initiating the taxonomy addition. |
| EC-4 | Network is unavailable when a Groq call is attempted. | The failure is recorded as a classification error for the affected items. The job does not crash. Items remain unclassified. The error is surfaced in the job summary. |
| EC-5 | A taxonomy entry is deleted or renamed between the time a label was confirmed and the time Feature 4 reads it. | Out of scope for this feature. `normalized_label` stores the string value at the time of confirmation; it is not a live reference. Taxonomy mutation handling is a future concern. |
| EC-6 | The Groq API returns a valid label that exactly matches a taxonomy entry, but with a `confidence` of 0.0. | The label is recognized (taxonomy match), and `normalized_label` is assigned. The `confidence` value is recorded in the decision log as 0.0. Low classifier confidence does not gate taxonomy recognition — the confidence value is informational, not a routing gate at this stage. |
| EC-7 | An extraction record's `label` is an extremely long string (e.g., full paragraph of footnote text), causing the classifier payload to approach or exceed the 8,000 TPM cap on its own. | The payload must be truncated to fit within per-call token limits before dispatch. The truncation boundary and resulting payload are recorded in the decision log. The truncation does not alter the stored `label` field on the record. |
| EC-8 | The Groq RPD cap (1,000 per day) is exhausted mid-job. | Remaining unclassified items in the job are left in a pre-classification state. The job summary records how many items were not reached due to the daily cap. No item is marked as classified without a successful Groq response. The pipeline does not switch to a different model or provider to compensate (CONSTITUTION §4.1). |
| EC-9 | A `manual_required` record is sent for classification despite being excluded by the precondition. | This is a pipeline invariant violation. The system must reject the dispatch, log an error, and not send the item to Groq. The item remains in `manual_required` state. |
| EC-10 | The decision log file or endpoint is unavailable at write time. | The classification result is not discarded — the log write failure is itself logged (to stderr or an error log), and the classification result is held for a retry. A classifier call whose result cannot be durably logged is not treated as complete. |
