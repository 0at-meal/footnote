# spec.md -- Feature 8: Audit Report Export

**Satisfies:** FR9
**Phase:** 4 -- Extensibility & Compliance Output
**Depends on:** Feature 4 (generated `.xlsx` workbook and cell-level W3C Web Annotation provenance records); Feature 5 (review status, edit history, and confirmation timestamps); Feature 6 (source chain resolution for multi-contributor formula cells); Feature 7 (cross-year drift flags and baseline records)
**Status:** Completed

---

## What This Feature Does

1. **Compile cell-level provenance and model metadata.** For a completed model (identified by `job_id`), the feature compiles the full set of audit data from all upstream pipeline stages into a unified report dataset. This includes: job and entity metadata (entity identifier, filing filename, filing year, target metric); the complete list of generated formula cells from Feature 4 (sheet name, cell coordinate, formula expression, computed output); the full source chain for every cell resolved via Feature 6 (contributing `source_file`, `page`, `bbox`, raw `label`, `normalized_label`, `value`); review statuses and confirmation timestamps from Feature 5; classifier audit logs from Feature 3 (demonstrating numeric-free output); and any cross-year drift flags recorded by Feature 7. Report compilation requires that Feature 4 model generation has completed successfully; jobs without a completed model cannot be compiled.

2. **Render structured audit report PDF.** Using ReportLab or WeasyPrint, the compiled audit dataset is rendered into a structured, human-readable compliance-style PDF document. The report layout consists of:
   - **Executive Summary & Metadata**: Job ID, company/entity name, target metric (Adjusted EBITDA), generation timestamp, total cell count, and breakdown of automated vs human-verified items.
   - **Model & Reconciliation Summary**: High-level table of the target metric reconciliation showing all calculated formula items and line-item totals.
   - **Comprehensive Provenance Matrix**: Complete tabular ledger mapping every formula cell and line item to its source document, exact 1-indexed page number, and normalized 0-1000 bounding box coordinates (`{x0, y0, x1, y1}`). Multi-page tables maintain repeated column headers on every page break and formatted page numbers ("Page X of Y").
   - **Classifier Governance Proof**: Summary verifying that all LLM classifier interactions strictly returned labels and confidence scores with zero numeric extraction or computation.
   - **Cross-Year Definitional Consistency**: Summary of Feature 7 drift detection results, detailing any added/removed components year-over-year or confirming baseline/continuation status.

3. **Compile manual override and correction ledger.** The report includes a dedicated section detailing all manual overrides, user edits, and exceptions that occurred during the Feature 5 review stage:
   - Every item where a user edited the raw extracted `value` or `label` before confirming, displaying the original extracted value alongside the edited value, the user confirmation timestamp, and reason/flags.
   - Any cell generated as a manual hardcode (per CONSTITUTION 1.5 and NFR2).
   - Any item that originated with `status: extraction_error` or `status: manual_required` and was resolved via human intervention.
   - If zero items were edited, hardcoded, or overridden across the entire model, this section explicitly renders the statement: "Zero manual overrides -- 100% of values are derived from layout extraction and taxonomy-confirmed inputs."

4. **Expose downloadable PDF via API and UI.** The generated PDF report is saved to persistent storage associated with the job and exposed via a dedicated FastAPI endpoint (`GET /api/jobs/{job_id}/audit-report`). The endpoint serves the binary file with appropriate MIME type (`application/pdf`) and `Content-Disposition` attachment headers for browser downloading. The frontend displays an active download control within the job/model view once model generation is complete, enabling one-click export of the compliance audit PDF.

---

## What This Feature Does NOT Do

- **Does not modify any model data, extraction records, or review statuses.** Feature 8 is strictly read-only with respect to pipeline state. It compiles and formats existing data without altering any stored values.
- **Does not re-run extraction, classification, formula generation, or drift detection.** It consumes already-persisted outputs from Features 1 through 7.
- **Does not call external LLM or cloud rendering APIs.** PDF compilation and rendering run entirely locally and deterministically using ReportLab or WeasyPrint (CONSTITUTION 4.4).
- **Does not send filing content, extracted numbers, or report data to any remote telemetry or external service.** Data egress is strictly forbidden (CONSTITUTION 6.5).
- **Does not support interactive in-PDF editing.** The output is a finalized, static PDF document intended for compliance, archiving, and audit trail verification.
- **Does not generate an audit report for incomplete jobs.** Jobs still in ingestion, extraction, or review cannot produce an audit report until the `.xlsx` model has been generated.
- **Does not re-implement source chain resolution.** Feature 8 queries the existing Feature 6 source chain resolution interface and Feature 4 provenance records.
- **Does not implement multi-tenant document permissioning or DRM.** Single-user, single-session architecture per CONSTITUTION 6.10.

---

## Acceptance Criteria

1. **Report generation succeeds for any completed model.** Given any job that has completed Feature 4 model generation with valid provenance records, triggering audit report generation produces a valid, non-empty PDF file.

2. **Every summarized value links to a complete source chain.** 100% of numeric values and formula cells presented in the audit report provenance matrix trace to valid source metadata (`source_file`, `page`, `bbox`, `normalized_label`) or are explicitly cataloged in the manual overrides ledger.

3. **Manual overrides section is complete and explicit.** Every item modified, hardcoded, or manually entered during Feature 5 review appears in the manual overrides table with both original and final values. If zero overrides exist, the report explicitly states that zero overrides occurred.

4. **PDF formatting and visual structure are valid.** The generated PDF opens cleanly in standard PDF viewers without syntax or font errors. Multi-page tables include repeated table headers at the top of each page, proper cell wrapping without text clipping, and sequential page numbers ("Page X of Y").

5. **Deterministic report output.** Generating the audit report multiple times for the same unchanged job produces structurally identical PDF content and identical data tables.

6. **API download endpoint compliance.** The `GET /api/jobs/{job_id}/audit-report` endpoint returns HTTP 200, header `Content-Type: application/pdf`, and a valid attachment filename (`Content-Disposition: attachment; filename="audit_report_{job_id}.pdf"`).

7. **Classifier audit proof is included.** The report contains a dedicated section referencing the Feature 3 decision log, providing auditable confirmation that the LLM classifier operated strictly on labels with zero numeric output.

8. **Cross-year drift status is included.** The report contains the Feature 7 drift analysis for the target metric, displaying any added/removed component flags or clearly stating baseline/continuation status.

9. **Zero modification of underlying state.** Invoking audit report compilation and downloading the PDF causes zero modifications to stored extraction records, review statuses, formula trees, or drift graphs.

10. **Performance budget.** For a standard financial model (up to 50 line items and associated provenance records), PDF compilation and rendering complete in under 15 seconds on the local machine.

---

## Dependencies / Interfaces with Other Features

### Consumed from Feature 1
- **`job_id`, entity name, and filing metadata**: Job parameters and source file references used in report headers and provenance mapping.

### Consumed from Feature 2
- **Extraction records**: `value`, `label`, `page`, `bbox`, `source_file`, and `confidence_band` fields used as leaf records in the provenance matrix.
- **Contract:** Frozen schema fields (`value`, `label`, `page`, `bbox`, `source_file`) are read-only (CONSTITUTION 2.3, NFR7).

### Consumed from Feature 3
- **`normalized_label` and decision log**: Taxonomy-mapped labels for line items and decision log entries proving numeric-free classification.

### Consumed from Feature 4
- **`.xlsx` model structure and provenance records**: Cell coordinates, formulas, calculated values, and W3C Web Annotation records.

### Consumed from Feature 5
- **Review statuses and edit logs**: `locked`/`flagged` statuses, original vs edited values for modified items, and human confirmation timestamps.

### Consumed from Feature 6
- **Source chain resolution API**: Resolves multi-contributor formula cells into ordered lists of source components for provenance table rendering.

### Consumed from Feature 7
- **Drift flags and graph status**: Historical component comparison data for the filing and target metric.

### Exposed for Frontend
- **Download Endpoint**: `GET /api/jobs/{job_id}/audit-report` serving the generated PDF file.
- **Report Status Endpoint**: Metadata endpoint indicating whether the audit report is ready for download.

### Must Not Break
- `audit_report/` must be fully typed and pass `mypy --strict` (CONSTITUTION 1.1).
- `audit_report/` must not import from `classification/` or `formula_engine/` (CONSTITUTION 3.8).
- Report generation must not send filing data outside the local environment (CONSTITUTION 6.5).

---

## Predictable Edge Cases

| # | Edge Case | Required Behavior |
|---|---|---|
| EC-1 | A model has zero manual overrides, zero edits, and zero hardcodes. | The manual overrides section is not omitted; it explicitly renders the text confirming zero overrides were made during review. |
| EC-2 | A line item had an extraction error in Feature 2 (`status: extraction_error`) and was corrected manually during Feature 5 review. | The report lists the item in the overrides section, displaying the original error description, the human-entered value, and the confirmation timestamp. |
| EC-3 | A formula aggregates multiple line items located across different PDF pages (e.g. SBC footnote on page 45 and lease adjustment on page 78). | The provenance table lists all contributing components under that formula cell, showing each component's distinct page and bounding box. |
| EC-4 | An extracted label or footnote text is unusually long (e.g. multi-line description). | The PDF table cell automatically wraps text with appropriate row height adjustments; text is never clipped or overflowing table borders. |
| EC-5 | The provenance matrix spans a large number of pages (e.g. 15+ pages). | Page breaks occur cleanly between table rows; column headers repeat at the top of every page; page numbering ("Page X of Y") remains accurate. |
| EC-6 | Audit report generation is requested for a job where model generation has not completed or failed. | The API returns an HTTP 400/404 error ("Audit report unavailable: model generation not complete"). No empty or partial PDF is generated. |
| EC-7 | The filing is a baseline year with no prior drift history in Feature 7. | The drift section clearly states: "Baseline Year -- Initialized definition for [Metric]; no prior-year comparison available." |
| EC-8 | Source filing filenames or taxonomy labels contain Unicode or special currency symbols (e.g. â‚¬, Â¥, Â£, â€”, &). | ReportLab/WeasyPrint renders all characters cleanly using UTF-8 compliant fonts without character substitution errors (tofu boxes) or crashes. |
| EC-9 | Concurrent download requests are received for the same completed job's audit report. | The backend serves the persisted PDF file safely without file locking collisions or duplicate generation overhead. |
| EC-10 | A filesystem error occurs while saving the generated PDF (e.g. disk full or permission error). | The error is caught, logged, and an HTTP 500 error is returned with a descriptive message. No corrupt or truncated PDF file is saved or served. |