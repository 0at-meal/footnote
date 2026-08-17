# spec.md -- Feature 9: Evaluation Harness

**Satisfies:** Verification & Validation of FR1-FR9, NFR1-NFR4
**Phase:** 5 -- Validation & Hardening
**Depends on:** Feature 1 through Feature 8 (the evaluation harness executes the complete production pipeline end-to-end against a curated benchmark corpus)
**Status:** Draft

---

## What This Feature Does

1. **Load benchmark corpus and ground truth.** The harness loads a curated benchmark corpus comprising 5 to 10 manually tied-out 10-K filings with accompanying ground-truth annotations. For each benchmark filing, the corpus provides: the source PDF document and a schema-validated ground-truth specification defining all expected line items for the target metric (Adjusted EBITDA), including raw `label`, normalized taxonomy `normalized_label`, exact ground-truth numeric `value`, 1-indexed page number, and bounding box coordinate regions. The harness verifies corpus data integrity and schema compliance before initiating an evaluation run.

2. **Execute full pipeline on benchmark filings.** The harness runs the complete, production Footnote pipeline end-to-end against each benchmark filing in the corpus. Per CONSTITUTION 3.5, the harness imports and executes the actual application modules directly (`ingestion/`, `extraction/`, `classification/`, `formula_engine/`, `excel_export/`, `drift/`, `audit_report/`) rather than duplicated or mock implementations. The pipeline processes each filing through PDF layout extraction, LLM classification, formula model generation, and provenance attachment, measuring granular execution runtimes per stage to verify compliance with NFR3 (processing a 200-page 10-K in under 5 minutes).

3. **Multi-layer diffing against ground truth.** The harness performs an automated, structured comparison between the pipeline outputs and ground-truth records across three distinct architectural layers:
   - **Extraction Diffs**: Evaluates whether all expected line items were extracted with correct raw labels, values, pages, and bounding boxes. Identifies false negatives (missed line items), false positives (spurious extractions), value string mismatches (e.g. sign or numeric parsing discrepancies), and coordinate localization errors.
   - **Classification Diffs**: For correctly extracted items, verifies whether `normalized_label` matches ground-truth taxonomy mapping. Identifies misclassifications and taxonomy routing errors.
   - **Generation & Formula Diffs**: Validates formula tree accuracy, recalculation integrity of the generated `.xlsx` workbook, and complete provenance attachment for every generated cell.

4. **Generate accuracy, false-positive, and failure-pattern reports.** The harness compiles a structured evaluation report (available in both machine-readable JSON and human-readable Markdown/terminal formats). The report computes:
   - Line-item extraction accuracy percentage (ratio of correctly extracted true positives to total ground-truth items).
   - Precision, recall, and F1 scores per filing and corpus-wide.
   - Separate metric isolation distinguishing extraction errors from classification errors and generation errors.
   - False positive rate (spurious non-GAAP extractions).
   - Failure pattern classification cataloging layout issues (multi-column text flow bleed, merged cell misalignment, footnote cross-page severance).
   - Mandatory governance disclosure per CONSTITUTION 6.13 explicitly stating the benchmark corpus size and the exact count and percentage of items requiring human review or manual correction.

5. **Enforce failed extraction threshold.** The harness computes the confidence-band distribution across all extracted items for each filing. If more than 15% of a filing's line items fall outside the auto-accept confidence band (i.e. if `(count(needs_review) + count(manual_required) + count(extraction_error)) / count(total_items) > 0.15`), the harness automatically designates that filing as a **failed extraction** (plan 6.1 item 4). Filings marked as failed extractions are flagged in the summary report and trigger targeted failure-pattern analysis.

---

## What This Feature Does NOT Do

- **Does not modify confidence-band thresholds.** The 0.95 / 0.65 thresholds are fixed project defaults; the harness validates against them rather than adjusting them to pass.
- **Does not bypass or auto-confirm review flags.** No programmatic shortcut or automated acceptance of low-confidence items is permitted to artificially inflate accuracy metrics (CONSTITUTION 6.6, 6.11).
- **Does not import application code by copy.** The `eval/` package imports live production pipeline modules directly (CONSTITUTION 3.5).
- **Does not retry failed extractions with modified heuristic parameters.** Low-confidence and failed extractions are recorded and reported as-is (CONSTITUTION 6.14).
- **Does not report accuracy without mandatory disclosures.** Aggregate accuracy numbers must always state benchmark corpus size and manual intervention counts (CONSTITUTION 6.13).
- **Does not send benchmark data to remote evaluation APIs.** All evaluation, diffing, and reporting execute locally (CONSTITUTION 6.5).
- **Does not persist test artifacts into production stores.** Eval runs operate in isolated, sandboxed test environments without altering production databases, job queues, or drift graphs.
- **Does not provide an end-user UI.** The eval harness is a CLI / script / pytest-driven verification suite for development and CI/CD automation.

---

## Acceptance Criteria

1. **Benchmark corpus integrity:** The harness loads at least 5 curated, manually tied-out 10-K filings with valid ground-truth JSON/YAML specifications without schema validation errors.

2. **Direct production module execution:** The evaluation harness imports and runs the actual production pipeline codebase without duplicating logic (CONSTITUTION 3.5).

3. **Target extraction accuracy achievement:** The end-to-end pipeline achieves >= 90% line-item extraction accuracy across the benchmark corpus on auto-accepted line items.

4. **Three-layer error categorization:** The evaluation report strictly isolates and quantifies: (a) extraction errors, (b) classification errors, and (c) formula/generation errors into distinct metric summaries.

5. **Deterministic 15% threshold enforcement:** Any filing where > 15% of extracted line items fall outside the auto-accept confidence band (score < 0.95) is explicitly marked as `failed_extraction: true` in the output report.

6. **Mandatory transparency disclosure:** Every generated evaluation report explicitly outputs the benchmark corpus size (number of filings and total line items) and the exact count and percentage of manually corrected/reviewed items (CONSTITUTION 6.13).

7. **Structured failure pattern reporting:** Extraction errors are categorized into recognized failure patterns (e.g. multi-column flow error, merged cell error, footnote severance, sign misparsing).

8. **Zero formula error verification:** 100% of `.xlsx` workbooks generated across the benchmark corpus open cleanly and recalculate in Excel with zero formula errors (`#REF!`, `#VALUE!`, `#NAME?`).

9. **Complete test isolation:** Running the evaluation harness leaves zero persistent test records, temporary files, or modified state in production SQLite databases or file paths.

10. **Performance budget validation:** The harness measures and logs runtime for each filing, confirming whether a 200-page 10-K completes within the NFR3 budget (<= 5 minutes).

---

## Dependencies / Interfaces with Other Features

### Consumed from Feature 1
- **Job Ingestion & Validation**: `ingestion/` module and job models for initializing pipeline runs.

### Consumed from Feature 2
- **Layout Extraction & Confidence Bands**: `extraction/` Docling parsing, PyMuPDF coordinates, and confidence scoring.

### Consumed from Feature 3
- **Classification & Normalization**: `classification/` Groq batching, taxonomy lookup, and decision logs.

### Consumed from Feature 4
- **Deterministic Model Generation**: `formula_engine/` and `excel_export/` formula trees, workbook generation, and provenance tags.

### Consumed from Feature 5
- **Review State Contracts**: Confidence band thresholds (0.95 / 0.65) and lock contracts.

### Consumed from Feature 6
- **Audit Trail Lookup**: `audit_trail/` source chain resolution validation.

### Consumed from Feature 7
- **Cross-Year Drift**: `drift/` graph consistency and drift flag verification.

### Consumed from Feature 8
- **Audit Report Export**: `audit_report/` PDF compilation validation.

### Exposed for CI/CD & Testing
- **CLI Runner**: `eval/run_benchmark.py` runnable from terminal.
- **Pytest Suite**: Test suite integration under `backend/tests/eval/`.

### Must Not Break
- `eval/` imports live modules; code copy is strictly prohibited (CONSTITUTION 3.5).
- Accuracy reporting must include full corpus and intervention disclosures (CONSTITUTION 6.13).
- Review flags must never be suppressed to pass evaluation thresholds (CONSTITUTION 6.11, 6.14).

---

## Predictable Edge Cases

| # | Edge Case | Required Behavior |
|---|---|---|
| EC-1 | A benchmark ground-truth line item is absent from a filing because the company did not report that specific adjustment that year. | The ground-truth schema supports optional/conditional items; the diff engine correctly treats valid non-reporting as expected rather than penalizing recall. |
| EC-2 | Extracted value represents a negative number in parentheses e.g. `(1,234)` while ground truth is stored as `-1234`. | The diff engine performs semantic numeric equivalence checking while also validating raw string formatting fidelity. |
| EC-3 | A filing has exactly 15.01% of items in the review/manual band (boundary threshold). | The filing is deterministically marked as a failed extraction per the strict > 15% rule. |
| EC-4 | A benchmark PDF file is missing or corrupted on disk. | The harness logs a descriptive error for that filing during corpus validation and aborts before running evaluations. |
| EC-5 | Rate limit (429) is returned by Groq API during an evaluation run. | Feature 3's exponential backoff handles retry; the harness logs the rate-limit delay and tracks its impact on total runtime. |
| EC-6 | Extracted bounding box covers 90% of the true bounding box with minor coordinate offset. | The diff engine uses an IoU (Intersection-over-Union) tolerance threshold to evaluate bounding box localization without penalizing minor pixel offsets. |
| EC-7 | A filing achieves 100% auto-accepted extractions with zero items flagged for review. | The filing is recorded as an extraction success; report displays 0% manual review rate and 100% auto-accept rate. |
| EC-8 | Model generation fails for one filing in the corpus due to missing provenance fields. | The failure is categorized specifically as a generation error; remaining benchmark filings continue processing. |
| EC-9 | A benchmark filing exceeds 200 pages. | The pipeline processes all pages; the harness records the page count and flags if runtime exceeds the NFR3 5-minute budget. |
| EC-10 | Ground truth contains duplicate normalized labels across different sections/pages. | The diff engine disambiguates and aligns items using page numbers and table structural context rather than collapsing by label string alone. |