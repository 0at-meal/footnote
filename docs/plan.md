# Footnote — plan.md

Governs what gets built, how, and in what order. Governed by
`FOOTNOTE_CONSTITUTION.md`, which is not restated here — read both before
starting any phase. On conflict, the constitution wins.

---

## 1. Goals

### 1.1 Functional Requirements

| ID | Requirement |
|---|---|
| FR1 | The system shall accept multi-file PDF uploads and queue them for extraction. |
| FR2 | The system shall parse PDFs and extract line items, preserving multi-level headers, footnote references, and exact page/bbox coordinates. |
| FR3 | The system shall classify extracted line items against a standardized taxonomy, using an LLM strictly as a classifier — never as a source of computed values. |
| FR4 | The system shall detect when a company redefines or renames a metric year-over-year and link the new definition to its historical baseline. |
| FR5 | The system shall generate a native `.xlsx` workbook where every derived value is a real Excel formula, computed by deterministic code. |
| FR6 | The system shall bind provenance metadata (page, bbox, source file) to every generated cell. |
| FR7 | The system shall provide a side-by-side review UI to confirm, correct, or flag each extracted item before model generation. |
| FR8 | The system shall allow a user to select any cell and retrieve its full source chain (documents, pages, coordinates). |
| FR9 | The system shall produce a downloadable, human-readable audit report (PDF) summarizing provenance for a model. |

### 1.2 Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR1 | Identical input filings shall always produce identical formulas and structure. |
| NFR2 | 100% of generated numeric cells shall be traceable to a source location or explicitly marked as a manual hardcode. |
| NFR3 | A single 200-page 10-K shall complete extraction and model generation in under 5 minutes on local/free-tier compute. |
| NFR4 | The system shall run within free-tier or local-machine resource limits for MVP. |
| NFR5 | The architecture shall support a fully local/offline inference path (design principle, not MVP-enforced). |
| NFR6 | Adding a new target metric shall not require re-architecting the extraction or formula-generation layers. |
| NFR7 | Cross-year drift history shall survive a backend restart. |

### 1.3 Locked Decisions

| Decision | Value |
|---|---|
| Phase 1/2 target metric | Adjusted EBITDA |
| Extraction execution environment | Local machine (not a hosted notebook) |
| LLM classifier provider | Groq API, `openai/gpt-oss-120b` |

---

## 2. Tech Stack

Inherited from `FOOTNOTE_CONSTITUTION.md` §4, with the LLM entry as
specified below — the constitution has been updated to match.

| Layer | Choice |
|---|---|
| Backend framework | FastAPI |
| PDF layout parsing | Docling |
| PDF coordinate/rendering utility | PyMuPDF |
| LLM (classification only) | Groq API, `openai/gpt-oss-120b`. Free tier: no card required — 30 RPM / 1,000 RPD / 8,000 TPM / 200,000 TPD. Open-source models only. Local Ollama remains the documented production/offline alternative per NFR5. |
| Formula engine | Custom Python module, deterministic |
| Excel generation | xlsxwriter |
| Graph/state (drift tracking) | NetworkX + SQLite/JSON persistence |
| Frontend framework | React |
| PDF rendering (frontend) | PDF.js |
| Audit report export | ReportLab or WeasyPrint |
| Testing/eval | Pytest |
| CI/CD | GitHub Actions |
| Docs | MkDocs |
| Extraction execution environment | Local machine (Docling's ≥2GB RAM floor rules out the hosted free tier) |

---

## 3. Features

Each feature is a complete, independently verifiable unit. Build steps are
ordered; acceptance criteria define "done."

### Feature 1 — Multi-File PDF Upload & Job Queueing (FR1)
1. Drag/drop or file-select upload zone (frontend).
2. Server-side file type/size validation before a job is accepted.
3. Job metadata (filename, size, status) persisted to a visible job list.
4. Target metric(s) selectable per job — default: Adjusted EBITDA.
5. Job submission triggers the extraction pipeline.

**Acceptance criteria:** multiple PDFs can be queued in one session; an
invalid file is rejected with a clear error, not silently dropped.

### Feature 2 — Layout-Aware Extraction (FR2)
1. Docling structural parse (tables, headers, footnote markers) per PDF.
2. PyMuPDF bounding-box extraction per identified value.
3. Assemble each value into: `{value, label, page, bbox, source_file}`.
4. Structural-confidence scoring; low-confidence items flagged, not
   guessed. Confidence-band definitions: **auto-accept ≥ 0.95**,
   **human-review 0.65–0.95**, **manual entry < 0.65**.

**Acceptance criteria:** runs against 3–5 real 10-Ks, locally, without
crashing; every extracted value carries a resolvable page and bbox;
items below auto-accept confidence are visibly flagged, never silently
included.

### Feature 3 — Classification & Normalization (FR3)
1. Send each extracted item, with surrounding context, to the Groq
   classifier (`openai/gpt-oss-120b`).
2. Classifier's return type structurally cannot carry a numeric field
   (constitution §4.7, §6.2).
3. Returned label checked against a seed taxonomy (common non-GAAP
   reconciliation items: SBC, lease adjustments, litigation, etc.).
4. Unrecognized labels queued for user confirmation, never auto-accepted
   into the taxonomy.
5. Confirmed, normalized label attached to the item's record.
6. Every classifier call logged: input context, returned label,
   confidence — exportable, machine-readable (see §6.1, item 6).

**Acceptance criteria:** classifier calls stay within Groq's published
free-tier RPM/TPM/RPD limits under realistic batch sizes; no code path
allows a classifier response to populate a numeric field; the decision
log for every item is retrievable.

### Feature 4 — Deterministic Model Generation (FR5, FR6)
1. Formula engine reads confirmed, normalized line items.
2. Formula tree built per target metric as a pure function — no I/O, no
   randomness (constitution §1.4).
3. `.xlsx` workbook generated via xlsxwriter with real formulas
   (XLOOKUP / INDEX-MATCH / SUMIFS).
4. Every cell tagged with provenance metadata: exactly one comment, one
   hyperlink, pointing to a single W3C Web-Annotation-style provenance
   record (see §6.1, item 3).

**Acceptance criteria:** identical input produces byte-identical formula
structure on repeated runs (NFR1); 100% of generated formulas open and
recalculate in Excel with zero broken references; every non-hardcoded
cell resolves to a source record; hyperlinks survive an Excel
open/re-save cycle.

### Feature 5 — Extraction Review UI (FR7)
1. Source PDF page rendered via PDF.js.
2. Extracted items displayed alongside, each highlighted to its source
   bounding box.
3. Confirm / edit / flag actions per item.
4. Confirmed items locked against further silent modification.

**Acceptance criteria:** every extracted item is reachable from the
review UI; a locked item cannot be altered by any code path except an
explicit user unlock action.

### Feature 6 — Audit Trail Lookup (FR8)
1. Cell selection (workbook or exported metadata) resolves to its full
   source chain.
2. Source chain displayed with a direct link to the originating PDF page.
3. Verified/flagged status shown per component.

**Acceptance criteria:** a reviewer can trace any flagged number back to
its source PDF page in under 10 seconds using the UI.

### Feature 7 — Cross-Year Drift Detection (FR4)
1. Current filing's normalized labels compared against prior-year graph
   entries.
2. Discrepancy flagged when a metric's definition or components changed.
3. New definition linked to the historical graph node.
4. Graph persisted to SQLite/JSON after every update (NFR7).

**Acceptance criteria:** drift history survives a backend restart; a
known year-over-year redefinition in the benchmark corpus is correctly
flagged.

### Feature 8 — Audit Report Export (FR9)
1. Compile all cell-level provenance for a completed model.
2. Render as a structured PDF via ReportLab/WeasyPrint.
3. Include a summary of manually overridden items.
4. Expose as a downloadable file from the UI.

**Acceptance criteria:** report generation succeeds for any model that
passed Feature 4/6; every summarized value links back to a real source
chain.

### Feature 9 — Evaluation Harness
1. Load benchmark corpus (5–10 manually tied-out 10-Ks).
2. Run full pipeline against each benchmark filing.
3. Diff extracted values against ground truth.
4. Generate accuracy / false-positive / failure-pattern report per run.
5. Mark a filing as a **failed extraction** if more than 15% of its line
   items fall outside the auto-accept confidence band.

**Acceptance criteria:** ≥ 90% line-item extraction accuracy against the
benchmark; report clearly separates extraction errors from classification
errors from generation errors.

---

## 4. Phased Delivery

Each phase delivers whole, working features — not partial slices. Phase 5
ends with the complete product, all nine features integrated. No phase
begins until the prior phase's Definition of Done is met and reviewed by
a human.

### Phase 1 — Ingestion Pipeline
**Delivers:** Feature 1, Feature 2 (complete).
**Out of scope this phase:** classification, generation, any UI beyond a
raw job list.
**Definition of Done:** multi-file upload and layout-aware extraction run
end-to-end, locally, against real, messy 10-Ks; every extracted value
carries resolvable page/bbox metadata; confidence-band flagging is live.

### Phase 2 — Core Trust Loop
**Delivers:** Feature 3, Feature 4 (complete).
**Out of scope this phase:** review UI, audit lookup, drift tracking,
export, eval harness.
**Definition of Done:** the full chain — extracted item → Groq label →
deterministic formula → provenance-tagged `.xlsx` cell — is provably
intact for Adjusted EBITDA across the Phase 1 corpus. This phase proves
the project's central claim.

### Phase 3 — Human Trust Layer
**Delivers:** Feature 5, Feature 6 (complete).
**Out of scope this phase:** drift tracking, export, eval harness.
**Definition of Done:** a reviewer can confirm/correct/flag any extracted
item and trace any generated cell back to its source PDF page in under
10 seconds, entirely through the UI.

### Phase 4 — Extensibility & Compliance Output
**Delivers:** Feature 7, Feature 8 (complete).
**Out of scope this phase:** eval harness, CI/CD, docs.
**Definition of Done:** drift history survives a restart and correctly
flags a known redefinition in the corpus; a compliance-style audit PDF
exports correctly for a completed model.

### Phase 5 — Validation & Hardening
**Delivers:** Feature 9 (complete); CI/CD via GitHub Actions; docs via
MkDocs; performance tuning against NFR3.
**Out of scope this phase:** any new feature not listed in Section 3.
**Definition of Done:** ≥ 90% benchmark accuracy; 100% of formulas open
cleanly in Excel; 100% of non-hardcoded cells carry resolvable
provenance; full pipeline completes a 200-page filing in under 5 minutes
on the local machine. All nine features are built, integrated, and
passing their individual acceptance criteria — the product is complete.

---

## 5. Technical Constraints

- Docling requires ≥ 2GB RAM — this is why extraction runs on the local
  machine, not the hosted free tier (Phase 1).
- xlsxwriter can only create new workbooks, never patch existing ones —
  every regeneration is from scratch (Phase 2; revisit only if "edit an
  existing model" is ever requested).
- Groq free tier for `openai/gpt-oss-120b`: 30 RPM / 1,000 RPD / 8,000
  TPM / 200,000 TPD. Whichever cap is hit first triggers a 429. Batching
  in Feature 3 must be designed against these exact numbers (Phase 2).
- Groq serves open-source models only — no GPT, Claude, or Gemini access
  through this endpoint. Classifier prompt design must not assume
  proprietary-model-only behaviors (Phase 2).
- LLM API calls leave the local environment and are logged by the
  provider — true data-privacy guarantees require local Ollama inference,
  documented but not enforced at MVP (relevant only if a real, non-public
  filing is ever tested).
- MVP is single-user, single-session — no auth, no multi-tenancy, by
  design (constitution §6.10).

---

## 6. Open Questions

### 6.1 Answered

1. **Phase 1/2 target metric.** Adjusted EBITDA — confirmed.
2. **Extraction execution environment.** Local machine — confirmed.
   Consistent with Docling's RAM floor (§5); no notebook-runtime
   reproducibility risk.
3. **LLM provider and model.** Groq API, `openai/gpt-oss-120b` —
   confirmed. See §2 for free-tier limits.
4. **Manual-correction failure threshold.** Set via a three-tier
   confidence-routing model, the current industry standard for financial
   field extraction: auto-accept ≥ 0.95, human-review 0.65–0.95, manual
   entry < 0.65. Well-tuned pipelines using this pattern route roughly
   5–15% of fields to review while holding ≥ 99.5% effective accuracy.
   Footnote's Feature 9 threshold is set at the upper end of that
   published range: **> 15% of a filing's line items outside the
   auto-accept band = failed extraction.**
5. **Taxonomy: hand-curated or dynamic?** Resolved by existing literature
   on taxonomy design: a hand-curated seed list expanded only through a
   human-in-the-loop confirmation step is the established pattern across
   taxonomy-design research (iterative expert review, RAG-based
   expansion with expert validation) — not a genuinely open question.
   This is already how Feature 3 is specified; no change needed.
6. **Proving "AI as classifier only" is real, not just claimed.**
   Resolved by an established explainability pattern: a hard interface
   boundary ("explainability barrier") between the LLM's output space
   (label + confidence only) and the deterministic engine's output space
   (the number), paired with a structured, exportable decision log
   recording, per item, the classifier's input context, its label and
   confidence, and the formula engine's resulting numeric output. This is
   now built into Feature 3, step 6 — the log itself is the proof,
   surfaced in the UI/audit export rather than asserted in documentation.
7. **Bounding-box metadata format.** W3C Web Annotation Data Model
   (JSON), normalized 0–1000 bounding-box coordinates. One canonical
   record per value; the Excel cell comment/hyperlink is a projection of
   it, not a second copy (Feature 4).
8. **Docling on non-standard layouts.** Documented limitation: text can
   flow across column boundaries on multi-column layouts; merged cells
   and multi-level headers are frequently misinterpreted. Mitigation: use
   the JSON export (`row_span`/`col_span`) over Markdown/HTML, compare
   "accurate" vs. "fast" table modes; worst cases still need manual
   post-processing (Phase 1).
9. **NetworkX + SQLite sufficiency.** Sufficient at MVP scale (dozens of
   graph nodes). Reload-on-startup/serialize-on-write is a standard,
   documented workaround for NetworkX's lack of native persistence.
   Revisit only past ~10,000+ nodes.
10. **xlsxwriter provenance survival on re-save.** Generally survives;
    known edge cases (multiple URLs in one cell, spaces in sheet names)
    are avoided by Feature 4's one-hyperlink-per-cell rule.

### 6.2 Still Open

1. The 0.95 / 0.65 confidence thresholds in Feature 2/9 are informed
   defaults, not calibrated to this project's actual documents —
   recalibrate after the Phase 1 corpus produces real confidence-score
   data (industry guidance: reassess after roughly 500 processed items).
2. Whether `openai/gpt-oss-120b`'s 8,000 TPM / 200,000 TPD Groq free-tier
   ceiling comfortably covers realistic per-filing batch sizes given
   typical footnote context length — untested until Phase 2 batching is
   implemented against real filings.
