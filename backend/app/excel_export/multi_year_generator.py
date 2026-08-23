"""
Multi-year Excel workbook generator using xlsxwriter (Feature 4 / Phase 2 Multi-Year Architecture).

Enforces:
- CONSTITUTION §1.1, §1.3, §1.4, §1.5, §2.5, §3.3, §4.2, §6.4
- Pure function: no I/O beyond output_dir, no global mutable state.
- Space-free sheet name: Multi_Year_Model.
- Layout: Row 1 Company title, Row 2 FY headers, Rows 3+ unique line items, Final row =SUM formula.
- Styling: Blue font for hardcode values, Black bold double-underline for total formulas.
- Provenance: W3C annotation comments on generated value cells.
"""

import logging
import os
from pathlib import Path
from typing import Any

import xlsxwriter

from app.excel_export.models import (
    CellReference,
    W3CAnnotationRecord,
    WorkbookGenerationResult,
)
from app.excel_export.provenance import (
    build_w3c_annotation_for_node,
    format_cell_comment,
)
from app.formula_engine.models import FormulaNode, FormulaTree
from app.ingestion.models import CompanyRecord, JobRecord

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"
_IB_CURRENCY_FORMAT: str = '$#,##0.00;($#,##0.00);"-"'


def _parse_numeric_value(raw_val: str) -> tuple[float | None, bool]:
    """
    Parses a raw string value into a float, supporting commas, parentheses for negatives.

    Returns:
        (parsed_float_or_None, is_valid_number)
    """
    cleaned = raw_val.strip()
    if not cleaned:
        return None, False

    is_negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        is_negative = True
        cleaned = cleaned[1:-1].strip()

    cleaned = cleaned.replace(",", "").replace("$", "").strip()

    try:
        val = float(cleaned)
        if is_negative:
            val = -val
        return val, True
    except ValueError:
        return None, False


def _col_to_letter(col_idx: int) -> str:
    """Converts 0-indexed column number to Excel column letter (0 -> 'A', 1 -> 'B')."""
    result = ""
    col = col_idx
    while col >= 0:
        result = chr(ord("A") + (col % 26)) + result
        col = (col // 26) - 1
    return result


def _to_cell_coord(row_idx: int, col_idx: int) -> str:
    """Converts 0-indexed (row, col) to A1-style coordinate (e.g. (1, 1) -> 'B2')."""
    return f"{_col_to_letter(col_idx)}{row_idx + 1}"


def generate_multi_year_workbook(
    company: CompanyRecord,
    jobs: list[tuple[JobRecord, FormulaTree]],
    output_dir: Path | None = None,
) -> WorkbookGenerationResult:
    """
    Generate a standardized multi-year Excel model workbook across multiple fiscal years.

    Layout:
    - Row 1: Company Title e.g. 'Acme Corporation (ACME) -- Multi-Year Model'
    - Row 2: Column Headers: 'Line Item' (Col A), 'FY{year}' per job (Cols B..N) ordered by filing_year ascending
    - Rows 3..K: One row per unique normalized line item across all years.
      Value cells: plain numeric blue font with W3C provenance comment. Absent years left blank.
    - Final Row: Total row with =SUM(col_start:col_end) formula per year column, styled with double-underline.
    """
    target_dir = (output_dir or _DEFAULT_DATA_DIR) / "models"
    target_dir.mkdir(parents=True, exist_ok=True)

    dest_file = target_dir / f"{company.company_id}_multi_year.xlsx"
    tmp_file = target_dir / f"{company.company_id}_multi_year.xlsx.tmp"

    valid_jobs: list[tuple[JobRecord, FormulaTree]] = [
        (job, tree) for job, tree in jobs if tree.is_valid and tree.root is not None
    ]

    if len(valid_jobs) == 0:
        if tmp_file.exists():
            try:
                tmp_file.unlink(missing_ok=True)
            except OSError:
                pass
        return WorkbookGenerationResult(
            job_id=company.company_id,
            file_path=str(dest_file),
            target_metric="Multi-Year Model",
            sheet_names=[],
            total_cells_generated=0,
            formula_cells_count=0,
            source_cells_count=0,
            cell_references=[],
            provenance_records=[],
            warnings=[],
            is_success=False,
            error_detail="No valid jobs/formula trees provided for multi-year model generation.",
        )

    # Sort jobs by filing_year ascending
    sorted_jobs = sorted(
        valid_jobs,
        key=lambda pair: (
            pair[0].filing_year if pair[0].filing_year is not None else 0,
            pair[0].submitted_at,
        ),
    )

    target_metric: str = (
        sorted_jobs[0][1].target_metric
        if sorted_jobs[0][1].target_metric
        else "Adjusted EBITDA"
    )

    # Collect unique normalized labels across all years while preserving discovery order
    ordered_labels: list[str] = []
    year_leaf_maps: list[dict[str, FormulaNode]] = []

    for _, tree in sorted_jobs:
        leaf_map: dict[str, FormulaNode] = {}
        for leaf in tree.leaves:
            label: str = (
                leaf.source_node.normalized_label
                if leaf.source_node and leaf.source_node.normalized_label
                else leaf.label
            )
            if label not in ordered_labels:
                ordered_labels.append(label)
            leaf_map[label] = leaf
        year_leaf_maps.append(leaf_map)

    sheet_name = "Multi_Year_Model"
    cell_refs: list[CellReference] = []
    provenance_records: list[W3CAnnotationRecord] = []
    warnings: list[str] = []

    workbook: Any = None
    try:
        workbook = xlsxwriter.Workbook(str(tmp_file))

        fmt_title = workbook.add_format(
            {
                "bold": True,
                "font_size": 12,
                "font_color": "#000000",
            }
        )
        fmt_header = workbook.add_format(
            {
                "bold": True,
                "bg_color": "#F2F2F2",
                "border": 1,
                "font_size": 10,
                "align": "left",
                "valign": "vcenter",
            }
        )
        fmt_header_num = workbook.add_format(
            {
                "bold": True,
                "bg_color": "#F2F2F2",
                "border": 1,
                "font_size": 10,
                "align": "right",
                "valign": "vcenter",
            }
        )
        fmt_text = workbook.add_format(
            {
                "align": "left",
                "font_size": 10,
                "border": 1,
            }
        )
        fmt_hardcode_num = workbook.add_format(
            {
                "font_color": "#0000FF",  # Blue font for values per CONSTITUTION §2.5
                "font_size": 10,
                "num_format": _IB_CURRENCY_FORMAT,
                "align": "right",
                "border": 1,
            }
        )
        fmt_total = workbook.add_format(
            {
                "bold": True,
                "font_size": 10,
                "font_color": "#000000",
                "num_format": _IB_CURRENCY_FORMAT,
                "top": 1,
                "bottom": 6,  # Double underline bottom border
                "align": "right",
            }
        )
        fmt_total_label = workbook.add_format(
            {
                "bold": True,
                "font_size": 10,
                "font_color": "#000000",
                "top": 1,
                "bottom": 6,
                "align": "left",
            }
        )

        ws = workbook.add_worksheet(sheet_name)
        ws.set_column("A:A", 40)
        for col_idx in range(1, len(sorted_jobs) + 1):
            col_letter = _col_to_letter(col_idx)
            ws.set_column(f"{col_letter}:{col_letter}", 18)

        # Row 0: Company Title
        title_text = (
            f"{company.name} ({company.ticker}) -- Multi-Year {target_metric} Model"
            if company.ticker
            else f"{company.name} -- Multi-Year {target_metric} Model"
        )
        ws.write(0, 0, title_text, fmt_title)

        # Row 1: Headers
        ws.write(1, 0, "Line Item", fmt_header)
        for idx, (job, _) in enumerate(sorted_jobs, start=1):
            header_text = (
                f"FY{job.filing_year}"
                if job.filing_year is not None
                else f"FY({job.filename})"
            )
            ws.write(1, idx, header_text, fmt_header_num)

        # Rows 2..(2 + len(ordered_labels) - 1): Line item data rows
        start_data_row = 2
        for offset, label in enumerate(ordered_labels):
            row_idx = start_data_row + offset
            ws.write(row_idx, 0, label, fmt_text)

            for col_idx, (job, _) in enumerate(sorted_jobs, start=1):
                leaf_node: FormulaNode | None = year_leaf_maps[col_idx - 1].get(label)
                if leaf_node is not None and leaf_node.source_node is not None:
                    source_node = leaf_node.source_node
                    raw_val = source_node.value
                    parsed_num, is_num = _parse_numeric_value(raw_val)
                    cell_coord = _to_cell_coord(row_idx, col_idx)

                    anno = build_w3c_annotation_for_node(
                        job.job_id, sheet_name, cell_coord, leaf_node
                    )
                    provenance_records.append(anno)
                    comment_text = format_cell_comment(anno)

                    ws.write_comment(
                        row_idx,
                        col_idx,
                        comment_text,
                        {"visible": False, "width": 240, "height": 110},
                    )

                    if is_num and parsed_num is not None:
                        ws.write_number(row_idx, col_idx, parsed_num, fmt_hardcode_num)
                    else:
                        ws.write(row_idx, col_idx, raw_val, fmt_text)
                        warnings.append(
                            f"Cell {cell_coord} '{label}' has non-numeric value '{raw_val}'"
                        )

                    cell_refs.append(
                        CellReference(
                            sheet_name=sheet_name,
                            row=row_idx,
                            col=col_idx,
                            coordinate=cell_coord,
                            node_id=leaf_node.node_id,
                            formula=None,
                            is_formula=False,
                            is_hardcode=True,
                            source_node_id=source_node.node_id,
                            annotation_id=anno.id,
                        )
                    )
                else:
                    # Absent in this year: cell is left blank (no write / blank cell)
                    pass

        # Final row: Total row
        total_row_idx = start_data_row + len(ordered_labels)
        ws.write(total_row_idx, 0, f"{target_metric} Total", fmt_total_label)

        excel_start_row = start_data_row + 1  # 1-indexed for Excel
        excel_end_row = (
            total_row_idx  # 1-indexed for Excel (the row right before total)
        )

        for col_idx in range(1, len(sorted_jobs) + 1):
            col_letter = _col_to_letter(col_idx)
            formula_str = (
                f"=SUM({col_letter}{excel_start_row}:{col_letter}{excel_end_row})"
            )
            total_coord = _to_cell_coord(total_row_idx, col_idx)

            ws.write_formula(total_row_idx, col_idx, formula_str, fmt_total)

            cell_refs.append(
                CellReference(
                    sheet_name=sheet_name,
                    row=total_row_idx,
                    col=col_idx,
                    coordinate=total_coord,
                    node_id=None,
                    formula=formula_str,
                    is_formula=True,
                    is_hardcode=False,
                    source_node_id=None,
                    annotation_id=None,
                )
            )

        workbook.close()
        workbook = None
        os.replace(tmp_file, dest_file)

        formula_count = sum(1 for c in cell_refs if c.is_formula)
        source_count = sum(1 for c in cell_refs if not c.is_formula)

        return WorkbookGenerationResult(
            job_id=company.company_id,
            file_path=str(dest_file),
            target_metric=target_metric,
            sheet_names=[sheet_name],
            total_cells_generated=len(cell_refs),
            formula_cells_count=formula_count,
            source_cells_count=source_count,
            cell_references=cell_refs,
            provenance_records=provenance_records,
            warnings=warnings,
            is_success=True,
        )

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Multi-year workbook generation failed for company %s: %s",
            company.company_id,
            exc,
        )
        if workbook is not None:
            workbook.fileclosed = 1
            del workbook
        if tmp_file.exists():
            try:
                tmp_file.unlink(missing_ok=True)
            except OSError:
                pass
        return WorkbookGenerationResult(
            job_id=company.company_id,
            file_path=str(dest_file),
            target_metric=target_metric,
            sheet_names=[],
            total_cells_generated=0,
            formula_cells_count=0,
            source_cells_count=0,
            cell_references=[],
            provenance_records=[],
            warnings=[],
            is_success=False,
            error_detail=f"Multi-year workbook generation failed: {exc}",
        )
