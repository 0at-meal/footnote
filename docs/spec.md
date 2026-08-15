# spec.md — Feature 4: Deterministic Model Generation

**Satisfies:** FR5, FR6  
**Phase:** 2 — Core Trust Loop  
**Depends on:** Feature 3 (confirmed, normalized line items with `normalized_label` populated must exist before this feature runs); Feature 2 (provenance fields `value`, `page`, `bbox`, `source_file` are read from the same records)  
**Status:** Draft

---

## What This Feature Does

1. **Formula engine input.** The formula engine reads all extraction records for a job that carry a populated `normalized_label` field — these are the confirmed, normalized line items produced by Feature 3. Records without a `normalized_label` (status `pending_taxonomy_confirmation`, `manual_required`, or `extraction_error`) are outside the engine's input set and are not read. The engine treats each confirmed record as a single, authoritative input node identified by its `normalized_label`. Both the `value` field (the raw numeric string from the source document) and the provenance fields (`page`, `bbox`, `source_file`) from Feature 2 are read alongside `normalized_label`; no field is modified.

2. **Formula tree construction.** From the confirmed input records, the formula engine builds a formula tree for the job's target metric (Adjusted EBITDA for Phase 2, per plan §1.3). The formula tree is constructed as a pure function: given the same set of confirmed records, it always produces the same tree structure with no variation. The function performs no I/O, makes no network calls, reads no clock, uses no random values, and references no global mutable state (CONSTITUTION §1.4). The resulting tree is an in-memory data structure; it is not yet serialized to any file at this step.

3. **Excel workbook generation.** The formula tree is serialized to a new `.xlsx` workbook file using xlsxwriter. Every derived value in the workbook is written as a real Excel formula string (e.g., using XLOOKUP, INDEX-MATCH, or SUMIFS constructions) — not as a static numeric literal. No numeric literal is written directly into a generated cell unless that value is explicitly tagged in the source record as a manual hardcode (CONSTITUTION §1.5). The workbook is always generated fresh; xlsxwriter never patches an existing file (CONSTITUTION §4.2). All generated formulas must resolve and recalculate correctly when the workbook is opened in Excel without any broken references.

4. **Provenance tagging.** Every generated cell in the workbook is tagged with provenance metadata sourced from the originating Feature 2 record. The tagging is exact: each cell receives exactly one cell comment and exactly one hyperlink. Both point to a single W3C Web Annotation–style provenance record (JSON, with bounding-box coordinates normalized to 0–1000 per plan §6.1 item 3). The comment and hyperlink are projections of this one canonical provenance record — not independent copies. The hyperlink must survive an Excel open/re-save cycle (plan §6.1 item 10). No cell may have zero provenance tags, and no cell may have more than one comment or more than one hyperlink.

---

## What This Feature Does NOT Do

- **Does not classify, label, or normalize any line item.** All input records are already confirmed and normalized by Feature 3. This feature reads them; it does not re-classify or modify any label field.
- **Does not re-parse the source PDF.** Provenance metadata (`page`, `bbox`, `source_file`) is read from the Feature 2 record already stored in the backend. This feature does not call Docling or PyMuPDF.
- **Does not call the Groq API or any external service.** Formula generation is entirely local and deterministic (CONSTITUTION §4.4).
- **Does not write numeric literals into derived cells.** Every derived value is a formula. A numeric literal in a generated cell is only permitted when the source record is explicitly tagged as a manual hardcode (CONSTITUTION §1.5, §6.1 item 2).
- **Does not patch or mutate an existing `.xlsx` file.** Every workbook is generated from scratch. "Regenerate" means produce a new file, not edit the previous one (CONSTITUTION §4.2).
- **Does not embed provenance as free-form text only.** The hyperlink must point to a machine-resolvable W3C Web Annotation record, not just a human-readable string in a comment.
- **Does not generate a workbook if any confirmed input record is missing provenance fields.** A record with a `null` or missing `page`, `bbox`, or `source_file` cannot be tagged and must be surfaced as a generation error — the cell is not generated with partial or absent provenance.
- **Does not display the workbook to the user.** Serving or downloading the file is outside this feature's scope; it is exposed via an API endpoint for Feature 6 and Feature 8.
- **Does not support target metrics other than Adjusted EBITDA in Phase 2.** The formula tree is built for the job's configured `target_metric`. Phase 2 delivers only Adjusted EBITDA. Adding a new metric is a future extension (NFR6) that must not require re-architecting this feature.
- **Does not implement drift detection or cross-year comparison.** That is Feature 7.

---

## Acceptance Criteria

1. **Identical input produces byte-identical formula structure.** Running the formula engine and workbook generator twice on the same set of confirmed records (same versions of all dependencies) produces `.xlsx` files with byte-identical formula strings and structure. Cell values, formula text, named ranges, and sheet layout must not vary between runs (NFR1, CONSTITUTION §6.7).

2. **Zero numeric literals in derived cells.** Inspecting every generated cell in the workbook: no cell that derives its value from an extraction record contains a static number. Every such cell contains a formula string. Any cell that is a manual hardcode carries an explicit tag identifying it as such (CONSTITUTION §1.5, NFR2).

3. **100% of generated formulas open and recalculate in Excel with zero broken references.** Opening the generated `.xlsx` in Excel (any version supporting XLOOKUP) and triggering a full recalculation produces no `#REF!`, `#NAME?`, `#VALUE!`, or other error results in any generated cell.

4. **Formula tree is a pure function of its inputs.** The formula tree construction function, given the same confirmed records, produces the same tree on every call. It can be verified by calling it twice on the same input in the same process and asserting structural equality of the result. Any non-determinism (different orderings, timing-dependent values) is a test failure.

5. **Every non-hardcoded cell resolves to exactly one source record.** For every generated cell that is not a manual hardcode, there exists exactly one Feature 2 provenance record (identified by `source_file`, `page`, `bbox`) that it traces to. No cell is left without a traceable source. No cell traces to more than one provenance record simultaneously.

6. **Every generated cell carries exactly one comment and exactly one hyperlink.** Inspecting cell metadata in the generated `.xlsx`: no cell has zero comments, zero hyperlinks, multiple comments, or multiple hyperlinks. This applies to every cell that was generated from a confirmed record — without exception.

7. **Provenance hyperlinks survive an Excel open/re-save cycle.** Open the generated `.xlsx` in Excel, save it without modification, close it, and reopen it. All hyperlinks in provenance-tagged cells remain present and point to the same target as before the re-save. Sheet names used in the workbook must not contain spaces (to avoid the known xlsxwriter hyperlink edge case per plan §6.1 item 10).

8. **Records without `normalized_label` are excluded from the engine.** Given a job where 80 records are confirmed and 10 are in `pending_taxonomy_confirmation`, the formula engine reads exactly 80 records. The 10 pending records do not appear in the workbook in any form — not as placeholders, not as zeros, not as error cells.

9. **Missing provenance fields surface as generation errors, not silent omissions.** If any confirmed input record has a `null` or missing `page`, `bbox`, or `source_file`, the engine records a provenance-tagging error for that record and does not generate the corresponding cell. The error is included in the job summary. The rest of the workbook is still generated for the remaining valid records.

10. **Performance: workbook generation completes within the NFR3 total budget.** For a 200-page 10-K, the full pipeline (extraction + classification + formula generation) must complete in under 5 minutes on the local machine (NFR3). Formula generation and workbook serialization for a typical Adjusted EBITDA reconciliation (up to ~50 confirmed line items) must complete in under 30 seconds.

---

## Dependencies / Interfaces with Other Features

### Consumed from Feature 1
- The `job_id` and `target_metric` fields on the job record determine which confirmed records belong to this generation run and which target metric's formula tree to build.

### Consumed from Feature 2
- **Provenance fields:** `value` (raw numeric string), `page`, `bbox`, `source_file` are read from each confirmed record. These fields are read-only; this feature must not modify them.
- **Contract:** The frozen field names (`value`, `label`, `page`, `bbox`, `source_file`) must remain unchanged (CONSTITUTION §2.3, NFR7).

### Consumed from Feature 3
- **Input gate:** Only records with a populated `normalized_label` are processed. `normalized_label` is treated as authoritative without re-validation (per Feature 3's exposed contract).

### Exposed for Feature 6
- **Output:** The generated `.xlsx` workbook file, accessible via an API endpoint for cell selection and source-chain lookup.
- **Output:** The set of W3C Web Annotation provenance records, one per generated cell, queryable by cell reference. Feature 6 uses these to resolve a cell selection to its full source chain.

### Exposed for Feature 8
- **Output:** The generated workbook and its provenance record set are the primary input for the audit report compilation.

### Must Not Break
- The `formula_engine/` module must be pure: no I/O, no clock, no random, no global state (CONSTITUTION §1.4). Any helper that needs I/O must live outside `formula_engine/`.
- The `excel_export/` module must not import from `classification/` (CONSTITUTION §3.3).
- Every PR touching `formula_engine/` or `excel_export/` must include or update a test (CONSTITUTION §1.6).
- Provenance records use the W3C Web Annotation JSON schema with 0–1000 normalized bounding-box coordinates — this format is fixed by plan §6.1 item 3 and must not be changed unilaterally.

---

## Predictable Edge Cases

| # | Edge Case | Required Behavior |
|---|---|---|
| EC-1 | Two confirmed records share the same `normalized_label` (e.g., Stock-Based Compensation appears twice from different pages). | Both records are included as separate leaf nodes in the formula tree. The formula aggregates them (e.g., via SUMIFS across both source cells). Each cell in the workbook traces to its own provenance record. They are not merged or deduplicated. |
| EC-2 | A confirmed record's `value` string is not parseable as a number (e.g., `"N/A"`, `"—"`, `"(see note 3)"`). | The record is included in the formula tree with its raw string value. The generated formula references the source cell. If Excel cannot interpret the source as a number in context, a generation warning is recorded. The cell is still generated and tagged — not silently dropped. |
| EC-3 | A confirmed record's `value` is a negative number in parentheses, e.g., `"(1,234)"`. | The raw string is passed through unchanged. The formula is responsible for any sign interpretation required by the target metric definition. No normalization occurs in this feature. |
| EC-4 | The job's `target_metric` is not Adjusted EBITDA (e.g., an unsupported metric was configured). | The formula engine surfaces an unsupported-metric error. No workbook is generated. The job summary records the error. This is not a silent no-op. |
| EC-5 | Zero confirmed records exist for a job (all records are pending or in error). | No workbook is generated. A generation error is recorded in the job summary: "No confirmed records available for formula generation." |
| EC-6 | The generated workbook would contain a sheet name with spaces (which causes xlsxwriter hyperlink issues per plan §6.1 item 10). | Sheet names are normalized at generation time — spaces replaced with underscores or removed — before any hyperlink is written. The normalization is applied consistently so hyperlinks and cell references remain coherent. |
| EC-7 | xlsxwriter raises an exception mid-generation (e.g., disk full, file permission error). | The partial workbook file is discarded. The job is marked with a generation error. No partial workbook is surfaced to downstream features. |
| EC-8 | A confirmed record's `bbox` contains coordinates outside the 0–1000 range. | This is a Feature 2 invariant violation (per Feature 2 AC-2). This feature surfaces a provenance-tagging error for that record and does not generate its cell. The error is included in the job summary. |
| EC-9 | The formula tree for Adjusted EBITDA resolves to a single line item with no addbacks (degenerate case). | A workbook is still generated with one source cell and one formula cell. The structure is valid; no minimum-node requirement exists. |
| EC-10 | Regeneration is triggered for a job that already has a generated workbook. | A new workbook is generated from scratch (xlsxwriter cannot patch existing files — CONSTITUTION §4.2). The prior workbook file is replaced. Provenance metadata is re-attached from the current confirmed records; no metadata is carried over from the prior file (CONSTITUTION §6.4). |
