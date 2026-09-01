# Architectural Decision Record (ADR) 002: Excel Output Format — Plain Values + Cross-Sheet References

* **Status:** ✅ Implemented
* **Date:** 2026-08-XX (decided during Refinement Phase 1 Step 1.3)
* **Implemented:** Refinement Phase 1, Ticket 1.3.1–1.3.3
* **Deciders:** Antigravity Team

---

## 1. Context and Problem Statement

The initial Excel output (Feature 4) used `write_url()` to wrap numeric values in
`=HYPERLINK(url, Source_Inputs!F{row})` formulas on the `Reconciliation` sheet, and
`write_url()` on `Source_Inputs` cells to embed provenance hyperlinks directly on value
cells. This produced technically correct output but failed practitioner usability tests:

- `=HYPERLINK(url, ...)` wrappers are fragile — they break when a banker inserts a row
  above the reference.
- Source cells wrapped in hyperlinks cannot be directly referenced in ad-hoc formulas
  without stripping the `=HYPERLINK(...)` wrapper first.
- The IB convention for editable models is plain numeric values (blue font = hardcode)
  with cell comments for metadata — not embedded URL wrappers.

---

## 2. Decision Drivers

1. **Banker-Editable Output:** The workbook must be immediately usable in a banker's
   working model without format cleanup. IB convention: blue = hardcode, black = formula,
   green = sheet-link.
2. **Formula Robustness:** Formulas must survive a banker inserting rows, sorting, or
   extending the table. `=HYPERLINK()` wrappers break; `=Source_Inputs!F{row}` cross-sheet
   references do not (for in-place edits).
3. **Provenance Preservation (NFR2):** All provenance metadata (page, bbox, source file,
   label) must remain attached to every cell. Cell comments are the correct mechanism.
4. **CONSTITUTION §1.5:** Excel-facing artifacts follow IB convention. Hardcodes are blue,
   formulas are black, sheet-links are green.

---

## 3. Decision

**Source_Inputs sheet:**
- Plain numeric values written with `write_number()` (blue font = hardcode, per
  CONSTITUTION §2.5).
- Provenance attached as cell comments: `Source: {source_file} / Page: {page} / BBox:
  ({x0}, {y0}) → ({x1}, {y1}) / Label: {label}`.
- No `write_url()` or `=HYPERLINK()` on source cells.

**Reconciliation sheet:**
- Each line item cell: `=Source_Inputs!F{row}` cross-sheet reference via `write_formula()`,
  styled with `fmt_sheet_link` (green, per CONSTITUTION §2.5).
- Total row: `=SUM(C{start}:C{end})` (black bold, double-underline).
- Sub-totals for aggregate groups: `=SUM(C{sub_start}:C{sub_end})`.
- Provenance comments retained on every cell.
- W3C Annotation records still generated and persisted to
  `data/results/{job_id}_provenance.json`.

---

## 4. Consequences & Benefits

* **Positive:** Any banker can open the workbook and use it immediately in their model.
  No URL wrappers to strip, no fragile HYPERLINK formulas.
* **Positive:** `=Source_Inputs!F{row}` cross-sheet references survive row inserts
  in `Source_Inputs` (Excel adjusts the row reference automatically).
* **Positive:** Cell comments carry the full provenance trail without cluttering the cell.
* **Negative/Trade-off:** Hyperlinks from cell to source PDF are no longer
  single-click-accessible from within Excel. The audit trail UI in the frontend remains
  the primary source-chain lookup mechanism.

---

## 5. Implementation Notes

| Ticket | File | Change |
|---|---|---|
| 1.3.1 | `excel_export/generator.py` | Replaced `write_url()` with `write_number()` + `write_comment()` on `Source_Inputs` cells |
| 1.3.2 | `excel_export/generator.py` | Wrote `=Source_Inputs!F{row}` formulas and `=SUM(...)` total on `Reconciliation` sheet; removed all `=HYPERLINK()` wrappers |
| 1.3.3 | `tests/excel_export/test_generator.py` | Tests: source cells `is_formula=False`; Reconciliation cells contain `=Source_Inputs!F{row}`; total is `=SUM(...)` format |
