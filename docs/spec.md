# spec.md — Feature 2: Layout-Aware Extraction

**Satisfies:** FR2  
**Phase:** 1 — Ingestion Pipeline  
**Depends on:** Feature 1 (a valid, persisted job record with a local PDF path must exist before this feature runs)  
**Status:** Draft

---

## What This Feature Does

1. **Docling structural parse.** For each PDF in a `queued` job, runs a Docling layout parse using its JSON export mode (`row_span`/`col_span` — not Markdown/HTML, per plan §6.1 item 8). Extracts: table cells, multi-level column and row headers, and footnote reference markers. The parse runs locally on the host machine; it never runs on a hosted service.

2. **PyMuPDF bounding-box extraction.** For each value identified by Docling, PyMuPDF resolves the exact bounding box (pixel/coordinate rectangle) and page number for that value within the source PDF.

3. **Record assembly.** Each extracted value is assembled into one Pydantic model with exactly these five fields — no more, no less:

   | Field | Type | Description |
   |---|---|---|
   | `value` | `str` | The raw text of the extracted value, exactly as it appears in the document. |
   | `label` | `str` | The raw structural label from the document (e.g., "Stock-Based Compensation"). This is **not** a normalized taxonomy label — that is Feature 3's output. |
   | `page` | `int` | 1-indexed page number in the source PDF. |
   | `bbox` | `dict` | W3C Web Annotation–style bounding box, normalized to 0–1000 coordinate space: `{x0, y0, x1, y1}`. |
   | `source_file` | `str` | The original filename as stored in the job record (UTF-8, unmodified). |

   These field names are **frozen for the lifetime of the project** (CONSTITUTION §2.3, NFR7). No renaming, no aliasing, no extension of this schema without an explicit, separate decision.

4. **Confidence scoring.** Each assembled record receives a structural confidence score (0.0–1.0), computed deterministically from Docling's parse signals (e.g., cell-merge ambiguity, header-depth uncertainty, footnote-marker resolution). The score routes the record to exactly one of three states:

   | Band | Score Range | State Assigned |
   |---|---|---|
   | Auto-accept | ≥ 0.95 | `auto_accepted` |
   | Human review | 0.65 – 0.95 | `needs_review` |
   | Manual entry | < 0.65 | `manual_required` |

5. **Flagging, not guessing.** Records in `needs_review` or `manual_required` are written to the output with their confidence score and band — they are never silently auto-accepted, never silently discarded, and never silently corrected by re-running with different parse settings (CONSTITUTION §6.14). They appear as explicitly flagged items for Feature 5's review UI.

6. **Exception surfacing.** Any parse error, coordinate-resolution failure, or record-assembly error for a specific value is recorded as a flagged item with `status: extraction_error` and the error detail attached. The pipeline does not swallow the exception and continue as if the item succeeded (CONSTITUTION §1.9). A single item's failure does not abort the whole job.

7. **Job status update.** On completion (all items processed, with or without flagged errors), the job status is updated from `extracting` to `done`. If the extraction process itself crashes unrecoverably (not a per-item error), the job status is set to `failed` with an error description.

---

## What This Feature Does NOT Do

- **Does not classify labels against a taxonomy.** The `label` field at this stage is raw text from the document. Normalization to a seed taxonomy is Feature 3's sole responsibility.
- **Does not compute, derive, or infer any numeric value.** Every `value` is the literal string as it appears in the PDF. No arithmetic, no currency conversion, no unit normalization.
- **Does not allow the LLM classifier anywhere near this stage.** No Groq API calls occur in this feature. The extraction process is fully deterministic and local (CONSTITUTION §6.1, §1.4).
- **Does not display extracted items to the user.** The review UI is Feature 5. This feature writes records to the backend store only.
- **Does not resolve cross-year drift.** Comparing this filing's items to prior years is Feature 7.
- **Does not generate the Excel workbook.** That is Feature 4.
- **Does not import from `classification/`.** The extraction module's import graph must never include the classification package (CONSTITUTION §3.2).
- **Does not recalibrate confidence thresholds.** The 0.95/0.65 thresholds are the project defaults (plan §6.2 item 1). Recalibration is a post-Phase-1 activity, not part of this feature's build.
- **Does not run on a hosted/free-tier server.** Docling's ≥ 2 GB RAM floor makes this local-only. The feature must not be designed in a way that assumes a hosted environment (plan §5, CONSTITUTION §4.4).
- **Does not handle non-PDF formats.** Feature 1 guarantees only PDFs reach this stage. No defensive conversion logic needed here.

---

## Acceptance Criteria

1. **Runs against real, messy 10-Ks without crashing.** The extraction pipeline completes (job reaches `done` or `failed`) for at least 3 real 10-K filings of varying formatting complexity without an unhandled exception. Messy = multi-column layouts, merged cells, footnote-heavy tables.

2. **Every extracted record carries a resolvable `page` and `bbox`.** No record reaches the output store with a `null`, missing, or out-of-range `page` or `bbox`. Out-of-range means: `page` < 1 or `page` > total pages in that PDF; `bbox` coordinates outside 0–1000.

3. **Schema is exactly the five frozen fields.** The Pydantic model for an extracted record has exactly `value`, `label`, `page`, `bbox`, `source_file` as required fields. Mypy `--strict` passes on the `extraction/` module (CONSTITUTION §1.1).

4. **Confidence band assignment is exhaustive and mutually exclusive.** Every record is assigned exactly one of `auto_accepted`, `needs_review`, or `manual_required`. No record exits the pipeline without a confidence score and band.

5. **Items below auto-accept threshold are visibly flagged — never silently included.** The output store for a completed job must contain a queryable flag (`confidence_band != "auto_accepted"`) for every non-auto-accepted item. Zero items may reach `auto_accepted` state with a score below 0.95.

6. **Per-item extraction errors are captured, not swallowed.** If any individual value fails to parse or resolve coordinates, the record appears in the output with `status: extraction_error` and a non-empty `error_detail` string. The count of `extraction_error` records is included in the job summary.

7. **Single-item failure does not abort the job.** A job processing a 50-page filing where 3 items fail coordinate resolution still completes with 47+ successful records and 3 error records. The job status is `done`, not `failed`.

8. **Job reaches `failed` only on unrecoverable crash.** `failed` status means the extraction process itself could not run (e.g., Docling is unavailable, file is unreadable at parse time). It does not mean "some items had errors."

9. **Determinism: identical input produces identical output.** Running the extraction pipeline twice on the same PDF (same Docling version, same PyMuPDF version) produces byte-identical records in the same order (NFR1). No random seeds, no clock-dependent branching, no unordered iteration (CONSTITUTION §6.7).

10. **Performance: a 200-page 10-K completes within the NFR3 budget.** Extraction alone must leave enough headroom in the 5-minute total budget (NFR3) for Features 3 and 4 to also run. A 200-page filing must complete extraction in under 3 minutes on the local machine.

---

## Known Edge Cases

| # | Edge Case | Required Behavior |
|---|---|---|
| EC-1 | Multi-column layout where text flows across column boundaries. | Docling's known limitation (plan §6.1 item 8). Affected items are assigned a lower confidence score, routing them to `needs_review` or `manual_required`. They are never silently merged or split. |
| EC-2 | Merged cells spanning multiple rows or columns. | Parse using Docling's `row_span`/`col_span` JSON fields. If the span is ambiguous (e.g., value appears in multiple cells), each candidate cell produces a separate record — both flagged `needs_review`. Do not auto-pick one. |
| EC-3 | Footnote marker present in a cell but the footnote text is on a different page. | The record is assembled with the value and its bbox. The footnote text is extracted as a separate record with its own `page` and `bbox`, linked by the footnote marker string. If the footnote text cannot be resolved, the original record is flagged `needs_review` with a note. |
| EC-4 | Header row spans multiple rows (e.g., "Fiscal Year" over "2022 / 2023 / 2024"). | Each leaf column header is resolved independently using Docling's hierarchical header structure. If the hierarchy cannot be resolved unambiguously, affected records are flagged `needs_review`. |
| EC-5 | Value appears as a negative number in parentheses, e.g., `(1,234)`. | Stored as the literal string `"(1,234)"` in `value`. No numeric interpretation or sign normalization occurs at this stage. |
| EC-6 | Same value appears identically in multiple locations on the same page (e.g., repeated in a summary row). | Each occurrence produces a separate record with its own `bbox`. They are not deduplicated. Deduplication is a downstream concern (Feature 5 review). |
| EC-7 | PDF contains scanned image pages (no selectable text). | Docling returns no structured content for image-only pages. Affected pages produce zero records. The job summary notes the count of image-only pages. No OCR is attempted (OCR is not in the tech stack). |
| EC-8 | Docling parse produces a confidence score of exactly 0.95 or exactly 0.65. | Boundary values are inclusive on the upper band: `score == 0.95` → `auto_accepted`; `score == 0.65` → `needs_review`. This must be encoded as `score >= 0.95` and `score >= 0.65` respectively, not strict inequality. |
| EC-9 | PDF has more than 200 pages. | The pipeline processes all pages. NFR3's 5-minute budget applies to 200-page filings; longer filings may exceed it — this is flagged in the job summary but is not a pipeline error. |
| EC-10 | `source_file` value contains characters that would be invalid in a file path on the host OS. | `source_file` stores the original filename string as-is (per Feature 1's EC-8 contract). It is not used as a filesystem path by this feature. The `job_id` is the filesystem key. |
