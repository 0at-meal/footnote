"""
Excel workbook generator using xlsxwriter with exact provenance tagging (Feature 4 Step 4).

Enforces:
- CONSTITUTION §1.1, §1.3, §1.5, §2.5, §3.3, §4.2, §6.4
- AC-1: Deterministic byte structure
- AC-2: Zero numeric literals in derived cells
- AC-3: Valid recalculable Excel formulas without broken references
- AC-5: Every non-hardcoded cell resolves to exactly one source record
- AC-6: Exactly one comment and exactly one hyperlink per generated cell
- AC-7 / EC-6: Space-free sheet names
- EC-2 / EC-3: Value parsing and warnings
- EC-7: Atomic serialization and cleanup on error
- EC-10: Fresh workbook generation from scratch
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
    format_cell_hyperlink_url,
)
from app.formula_engine.models import FormulaNodeType, FormulaTree

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"

# Standard IB currency number format: positive, negative in parens, zero as dash
_IB_CURRENCY_FORMAT = '$#,##0.00;($#,##0.00);"-"'


def _parse_numeric_value(raw_val: str) -> tuple[float | None, bool]:
    """
    Parses a raw string value into a float, supporting commas, parentheses for negatives.

    Returns:
        (parsed_float_or_None, is_valid_number)
    """
    cleaned = raw_val.strip()
    if not cleaned:
        return None, False

    # Check for negative in parentheses: e.g. (1,234.56) -> -1234.56
    is_negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        is_negative = True
        cleaned = cleaned[1:-1].strip()

    # Remove commas and currency symbols
    cleaned = cleaned.replace(",", "").replace("$", "").strip()

    try:
        val = float(cleaned)
        if is_negative:
            val = -val
        return val, True
    except ValueError:
        return None, False


def _col_to_letter(col_idx: int) -> str:
    """Converts 0-indexed column number to Excel column letter (0 -> 'A', 5 -> 'F')."""
    result = ""
    col = col_idx
    while col >= 0:
        result = chr(ord("A") + (col % 26)) + result
        col = (col // 26) - 1
    return result


def _to_cell_coord(row_idx: int, col_idx: int) -> str:
    """Converts 0-indexed (row, col) to A1-style coordinate (e.g. (1, 5) -> 'F2')."""
    return f"{_col_to_letter(col_idx)}{row_idx + 1}"


def generate_workbook(
    tree: FormulaTree,
    job_id: str,
    output_dir: Path | None = None,
    base_url: str = "http://localhost:8000",
) -> WorkbookGenerationResult:
    """
    Serializes a FormulaTree into a fresh .xlsx workbook with exact provenance tagging.

    Layout:
    - Sheet 'Source_Inputs': Tabular listing of extracted confirmed items with raw values.
    - Sheet 'Reconciliation': Calculated financial model with dynamic cross-sheet formulas.
    """
    target_dir = (output_dir or _DEFAULT_DATA_DIR) / "models"
    target_dir.mkdir(parents=True, exist_ok=True)

    dest_file = target_dir / f"{job_id}_model.xlsx"
    tmp_file = target_dir / f"{job_id}_model.xlsx.tmp"

    if not tree.is_valid or tree.root is None:
        if tmp_file.exists():
            try:
                tmp_file.unlink(missing_ok=True)
            except OSError:
                pass
        return WorkbookGenerationResult(
            job_id=job_id,
            file_path=str(dest_file),
            target_metric=tree.target_metric,
            sheet_names=[],
            total_cells_generated=0,
            formula_cells_count=0,
            source_cells_count=0,
            cell_references=[],
            provenance_records=[],
            warnings=[],
            is_success=False,
            error_detail=tree.error_message or "Invalid formula tree provided.",
        )

    cell_refs: list[CellReference] = []
    provenance_records: list[W3CAnnotationRecord] = []
    warnings: list[str] = []
    sheet_names = ["Source_Inputs", "Reconciliation"]

    workbook: Any = None
    try:
        workbook = xlsxwriter.Workbook(str(tmp_file))

        # Define IB-compliant format styles (CONSTITUTION §2.5)
        fmt_header = workbook.add_format(
            {
                "bold": True,
                "bg_color": "#F2F2F2",
                "border": 1,
                "align": "left",
                "valign": "vcenter",
            }
        )
        fmt_header_num = workbook.add_format(
            {
                "bold": True,
                "bg_color": "#F2F2F2",
                "border": 1,
                "align": "right",
                "valign": "vcenter",
            }
        )
        fmt_title = workbook.add_format(
            {
                "bold": True,
                "font_size": 14,
                "font_color": "#000000",
            }
        )
        fmt_source_num = workbook.add_format(
            {
                "font_color": "#000000",
                "num_format": _IB_CURRENCY_FORMAT,
                "align": "right",
            }
        )
        fmt_hardcode_num = workbook.add_format(
            {
                "font_color": "#0000FF",  # Blue for hardcodes (CONSTITUTION §2.5)
                "num_format": _IB_CURRENCY_FORMAT,
                "align": "right",
            }
        )
        fmt_formula_num = workbook.add_format(
            {
                "font_color": "#000000",  # Black for formulas (CONSTITUTION §2.5)
                "num_format": _IB_CURRENCY_FORMAT,
                "align": "right",
            }
        )
        fmt_sheet_link = workbook.add_format(
            {
                "font_color": "#008000",  # Green for sheet links (CONSTITUTION §2.5)
                "num_format": _IB_CURRENCY_FORMAT,
                "align": "right",
            }
        )
        fmt_total = workbook.add_format(
            {
                "bold": True,
                "font_color": "#000000",
                "num_format": _IB_CURRENCY_FORMAT,
                "top": 1,
                "bottom": 6,  # Double line bottom
                "align": "right",
            }
        )
        fmt_total_label = workbook.add_format(
            {
                "bold": True,
                "font_color": "#000000",
                "top": 1,
                "bottom": 6,
                "align": "left",
            }
        )
        fmt_text = workbook.add_format({"align": "left"})

        # ----------------------------------------------------
        # 1. Populate Sheet 'Source_Inputs'
        # ----------------------------------------------------
        ws_inputs = workbook.add_worksheet("Source_Inputs")
        ws_inputs.set_column("A:A", 22)
        ws_inputs.set_column("B:B", 35)
        ws_inputs.set_column("C:C", 35)
        ws_inputs.set_column("D:D", 10)
        ws_inputs.set_column("E:E", 25)
        ws_inputs.set_column("F:F", 20)

        # Header
        input_headers = [
            "Item ID",
            "Normalized Label",
            "Original Structural Label",
            "Page",
            "Source File",
            "Extracted Value",
        ]
        for col_idx, h_text in enumerate(input_headers):
            ws_inputs.write(
                0,
                col_idx,
                h_text,
                fmt_header_num if col_idx == 5 else fmt_header,
            )

        # Leaf node rows mapping: node_id -> row_idx
        source_cell_map: dict[str, int] = {}
        for row_idx, leaf in enumerate(tree.leaves, start=1):
            source_node = leaf.source_node
            raw_val = source_node.value if source_node else ""
            source_file = source_node.source_file if source_node else ""
            page = source_node.page if source_node else 1
            orig_label = source_node.label if source_node else ""

            ws_inputs.write(row_idx, 0, leaf.node_id, fmt_text)
            ws_inputs.write(row_idx, 1, leaf.label, fmt_text)
            ws_inputs.write(row_idx, 2, orig_label, fmt_text)
            ws_inputs.write(row_idx, 3, page, fmt_text)
            ws_inputs.write(row_idx, 4, source_file, fmt_text)

            parsed_num, is_num = _parse_numeric_value(raw_val)
            val_col = 5
            val_coord = _to_cell_coord(row_idx, val_col)

            # Build canonical W3C Web Annotation record (plan §6.1 item 7)
            anno = build_w3c_annotation_for_node(
                job_id, "Source_Inputs", val_coord, leaf
            )
            provenance_records.append(anno)

            # Format 1 comment and 1 hyperlink URL (AC-6, AC-7)
            comment_text = format_cell_comment(anno)
            hyperlink_url = format_cell_hyperlink_url(
                job_id, "Source_Inputs", val_coord, base_url=base_url
            )

            # Write comment (AC-6)
            ws_inputs.write_comment(
                row_idx,
                val_col,
                comment_text,
                {"visible": False, "width": 240, "height": 110},
            )

            is_hardcode = source_node.is_hardcode if source_node else False
            val_format = fmt_hardcode_num if is_hardcode else fmt_source_num

            display_str = (
                f"{parsed_num:,.2f}" if (is_num and parsed_num is not None) else raw_val
            )
            if not is_num:
                warnings.append(
                    f"Row {row_idx + 1} item '{leaf.label}' raw value '{raw_val}' is not a valid number (EC-2)"
                )

            # Write hyperlink with formatted display value (AC-6, AC-7)
            ws_inputs.write_url(
                row_idx,
                val_col,
                hyperlink_url,
                cell_format=val_format,
                string=display_str,
                tip=f"Source: {source_file} (p. {page})",
            )

            source_cell_map[leaf.node_id] = row_idx

            cell_refs.append(
                CellReference(
                    sheet_name="Source_Inputs",
                    row=row_idx,
                    col=val_col,
                    coordinate=val_coord,
                    node_id=leaf.node_id,
                    formula=None,
                    is_formula=False,
                    is_hardcode=is_hardcode,
                    source_node_id=source_node.node_id if source_node else None,
                    annotation_id=anno.id,
                )
            )

        # ----------------------------------------------------
        # 2. Populate Sheet 'Reconciliation'
        # ----------------------------------------------------
        ws_recon = workbook.add_worksheet("Reconciliation")
        ws_recon.set_column("A:A", 40)
        ws_recon.set_column("B:B", 30)
        ws_recon.set_column("C:C", 22)

        # Title
        ws_recon.write(0, 0, f"{tree.target_metric} Reconciliation", fmt_title)

        # Headers (Row 2)
        ws_recon.write(2, 0, "Line Item", fmt_header)
        ws_recon.write(2, 1, "Source Reference", fmt_header)
        ws_recon.write(2, 2, "Value ($)", fmt_header_num)

        curr_row = 3
        component_value_cells: list[str] = []

        for child in tree.root.children:
            if child.node_type == FormulaNodeType.leaf:
                input_row = source_cell_map[child.node_id]
                source_input_coord = f"Source_Inputs!F{input_row + 1}"
                val_coord = _to_cell_coord(curr_row, 2)

                # Canonical W3C annotation for reconciliation cell (AC-5, plan §6.1 item 7)
                anno = build_w3c_annotation_for_node(
                    job_id, "Reconciliation", val_coord, child
                )
                provenance_records.append(anno)

                comment_text = format_cell_comment(anno)
                hyperlink_url = format_cell_hyperlink_url(
                    job_id, "Reconciliation", val_coord, base_url=base_url
                )

                src_ref = (
                    f"{child.source_node.source_file} (p. {child.source_node.page})"
                    if child.source_node
                    else "Extracted"
                )

                formula_str = f'=HYPERLINK("{hyperlink_url}", {source_input_coord})'

                ws_recon.write(curr_row, 0, child.label, fmt_text)
                ws_recon.write(curr_row, 1, src_ref, fmt_text)
                ws_recon.write_formula(curr_row, 2, formula_str, fmt_sheet_link)
                ws_recon.write_comment(
                    curr_row,
                    2,
                    comment_text,
                    {"visible": False, "width": 240, "height": 110},
                )

                component_value_cells.append(val_coord)

                cell_refs.append(
                    CellReference(
                        sheet_name="Reconciliation",
                        row=curr_row,
                        col=2,
                        coordinate=val_coord,
                        node_id=child.node_id,
                        formula=formula_str,
                        is_formula=True,
                        is_hardcode=False,
                        source_node_id=(
                            child.source_node.node_id if child.source_node else None
                        ),
                        annotation_id=anno.id,
                    )
                )
                curr_row += 1

            elif child.node_type == FormulaNodeType.aggregate:
                # Multi-leaf aggregated items (EC-1)
                sub_coords: list[str] = []
                for sub_leaf in child.children:
                    sub_input_row = source_cell_map[sub_leaf.node_id]
                    sub_source_input_coord = f"Source_Inputs!F{sub_input_row + 1}"
                    sub_val_coord = _to_cell_coord(curr_row, 2)

                    sub_anno = build_w3c_annotation_for_node(
                        job_id, "Reconciliation", sub_val_coord, sub_leaf
                    )
                    provenance_records.append(sub_anno)

                    sub_comment = format_cell_comment(sub_anno)
                    sub_url = format_cell_hyperlink_url(
                        job_id, "Reconciliation", sub_val_coord, base_url=base_url
                    )

                    sub_src_ref = (
                        f"{sub_leaf.source_node.source_file} (p. {sub_leaf.source_node.page})"
                        if sub_leaf.source_node
                        else "Extracted"
                    )

                    sub_formula_str = (
                        f'=HYPERLINK("{sub_url}", {sub_source_input_coord})'
                    )

                    ws_recon.write(curr_row, 0, f"  - {sub_leaf.label}", fmt_text)
                    ws_recon.write(curr_row, 1, sub_src_ref, fmt_text)
                    ws_recon.write_formula(curr_row, 2, sub_formula_str, fmt_sheet_link)
                    ws_recon.write_comment(
                        curr_row,
                        2,
                        sub_comment,
                        {"visible": False, "width": 240, "height": 110},
                    )

                    sub_coords.append(sub_val_coord)

                    cell_refs.append(
                        CellReference(
                            sheet_name="Reconciliation",
                            row=curr_row,
                            col=2,
                            coordinate=sub_val_coord,
                            node_id=sub_leaf.node_id,
                            formula=sub_formula_str,
                            is_formula=True,
                            is_hardcode=False,
                            source_node_id=(
                                sub_leaf.source_node.node_id
                                if sub_leaf.source_node
                                else None
                            ),
                            annotation_id=sub_anno.id,
                        )
                    )
                    curr_row += 1

                # Aggregate summary row
                agg_val_coord = _to_cell_coord(curr_row, 2)
                agg_anno = build_w3c_annotation_for_node(
                    job_id, "Reconciliation", agg_val_coord, child
                )
                provenance_records.append(agg_anno)

                agg_comment = format_cell_comment(agg_anno)
                agg_url = format_cell_hyperlink_url(
                    job_id, "Reconciliation", agg_val_coord, base_url=base_url
                )

                agg_formula = f'=HYPERLINK("{agg_url}", SUM({", ".join(sub_coords)}))'

                ws_recon.write(curr_row, 0, child.label, fmt_text)
                ws_recon.write(curr_row, 1, "Aggregated", fmt_text)
                ws_recon.write_formula(curr_row, 2, agg_formula, fmt_formula_num)
                ws_recon.write_comment(
                    curr_row,
                    2,
                    agg_comment,
                    {"visible": False, "width": 240, "height": 110},
                )

                component_value_cells.append(agg_val_coord)

                cell_refs.append(
                    CellReference(
                        sheet_name="Reconciliation",
                        row=curr_row,
                        col=2,
                        coordinate=agg_val_coord,
                        node_id=child.node_id,
                        formula=agg_formula,
                        is_formula=True,
                        is_hardcode=False,
                        source_node_id=None,
                        annotation_id=agg_anno.id,
                    )
                )
                curr_row += 1

        # Final Target Metric Root Row
        root_val_coord = _to_cell_coord(curr_row, 2)
        root_anno = build_w3c_annotation_for_node(
            job_id, "Reconciliation", root_val_coord, tree.root
        )
        provenance_records.append(root_anno)

        root_comment = format_cell_comment(root_anno)
        root_url = format_cell_hyperlink_url(
            job_id, "Reconciliation", root_val_coord, base_url=base_url
        )

        total_formula = (
            f'=HYPERLINK("{root_url}", SUM({", ".join(component_value_cells)}))'
        )

        ws_recon.write(curr_row, 0, tree.target_metric, fmt_total_label)
        ws_recon.write(curr_row, 1, "Total", fmt_total_label)
        ws_recon.write_formula(curr_row, 2, total_formula, fmt_total)
        ws_recon.write_comment(
            curr_row,
            2,
            root_comment,
            {"visible": False, "width": 240, "height": 110},
        )

        cell_refs.append(
            CellReference(
                sheet_name="Reconciliation",
                row=curr_row,
                col=2,
                coordinate=root_val_coord,
                node_id=tree.root.node_id,
                formula=total_formula,
                is_formula=True,
                is_hardcode=False,
                source_node_id=None,
                annotation_id=root_anno.id,
            )
        )

        workbook.close()
        workbook = None

        # Atomic rename (CONSTITUTION §1.9, EC-7, EC-10)
        os.replace(tmp_file, dest_file)

        formula_count = sum(1 for c in cell_refs if c.is_formula)
        source_count = sum(1 for c in cell_refs if not c.is_formula)

        return WorkbookGenerationResult(
            job_id=job_id,
            file_path=str(dest_file),
            target_metric=tree.target_metric,
            sheet_names=sheet_names,
            total_cells_generated=len(cell_refs),
            formula_cells_count=formula_count,
            source_cells_count=source_count,
            cell_references=cell_refs,
            provenance_records=provenance_records,
            warnings=warnings,
            is_success=True,
            error_detail=None,
        )

    except Exception as err:  # noqa: BLE001
        logger.error("Failed to generate workbook for job %s: %s", job_id, err)
        if workbook is not None:
            workbook.fileclosed = 1
            del workbook
        if tmp_file.exists():
            try:
                tmp_file.unlink(missing_ok=True)
            except OSError:
                pass
        return WorkbookGenerationResult(
            job_id=job_id,
            file_path=str(dest_file),
            target_metric=tree.target_metric,
            sheet_names=[],
            total_cells_generated=0,
            formula_cells_count=0,
            source_cells_count=0,
            cell_references=[],
            provenance_records=[],
            warnings=warnings,
            is_success=False,
            error_detail=str(err),
        )
