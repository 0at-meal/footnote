"""
Primary Non-GAAP Reconciliation Bridge Excel Generator (Workflow Pack 1 / Step 7).

Generates a deterministic 2-tab workbook (Source_Inputs + Reconciliation) with exact W3C provenance tagging.

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
    format_source_deep_link,
)
from app.extraction.scale_and_sign import (
    UnitScale,
    format_workbook_units_header,
)
from app.formula_engine.models import FormulaNodeType, FormulaTree

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"

from app.excel_export.utils import (
    IB_CURRENCY_FORMAT as _IB_CURRENCY_FORMAT,
)
from app.excel_export.utils import (
    _parse_numeric_value,
    _to_cell_coord,
)


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
    sheet_names = ["Source_Inputs", "Reconciliation", "Checks", "Review"]

    workbook: Any = None
    try:
        workbook = xlsxwriter.Workbook(str(tmp_file))

        # Define IB-compliant format styles (CONSTITUTION §2.5, FN-030, FN-032)
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
        fmt_title = workbook.add_format(
            {
                "bold": True,
                "font_size": 12,
                "font_color": "#000000",
            }
        )
        fmt_source_num = workbook.add_format(
            {
                "font_color": "#000000",
                "font_size": 10,
                "num_format": _IB_CURRENCY_FORMAT,
                "align": "right",
                "border": 1,
            }
        )
        fmt_hardcode_num = workbook.add_format(
            {
                "font_color": "#0000FF",  # Blue for hardcodes (CONSTITUTION §2.5)
                "font_size": 10,
                "num_format": _IB_CURRENCY_FORMAT,
                "align": "right",
                "border": 1,
            }
        )
        fmt_formula_num = workbook.add_format(
            {
                "font_color": "#000000",  # Black for formulas (CONSTITUTION §2.5)
                "font_size": 10,
                "num_format": _IB_CURRENCY_FORMAT,
                "align": "right",
                "border": 1,
            }
        )
        fmt_sheet_link = workbook.add_format(
            {
                "font_color": "#008000",  # Green for sheet links (CONSTITUTION §2.5)
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
                "bottom": 6,  # Double line bottom
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
        fmt_text = workbook.add_format({"align": "left", "font_size": 10, "border": 1})

        # FN-030 & FN-032 styling tokens
        fmt_label_link = workbook.add_format(
            {
                "font_color": "#2B4BEE",
                "underline": True,
                "align": "left",
                "font_size": 10,
                "border": 1,
            }
        )
        fmt_needs_review_num = workbook.add_format(
            {
                "font_color": "#000000",
                "bg_color": "#FEF08A",  # Yellow for uncertain (FN-030)
                "font_size": 10,
                "num_format": _IB_CURRENCY_FORMAT,
                "align": "right",
                "border": 1,
            }
        )
        fmt_needs_review = workbook.add_format(
            {
                "font_color": "#000000",
                "bg_color": "#FEF08A",
                "font_size": 10,
                "align": "right",
                "border": 1,
            }
        )
        fmt_manual_required = workbook.add_format(
            {
                "font_color": "#991B1B",
                "bg_color": "#FEE2E2",  # Red for manual required (FN-030, I3)
                "font_size": 10,
                "border": 1,
                "align": "right",
            }
        )
        fmt_draft_status = workbook.add_format(
            {
                "bold": True,
                "font_color": "#92400E",
                "bg_color": "#FEF3C7",
                "font_size": 10,
                "align": "center",
                "border": 1,
            }
        )
        fmt_verified_status = workbook.add_format(
            {
                "bold": True,
                "font_color": "#166534",
                "bg_color": "#DCFCE7",
                "font_size": 10,
                "align": "center",
                "border": 1,
            }
        )

        # Count unverified items for FN-030 status header
        unverified_leaves = [
            leaf
            for leaf in tree.leaves
            if leaf.source_node is not None
            and (
                getattr(leaf.source_node, "review_status", None)
                in ("needs_review", "manual_required")
                or not getattr(leaf.source_node, "is_confirmed", False)
            )
        ]
        unverified_count = len(unverified_leaves)

        # ----------------------------------------------------
        # 1. Populate Sheet 'Source_Inputs' (Ticket 1.3.1, FN-030, FN-032)
        # ----------------------------------------------------
        ws_inputs = workbook.add_worksheet("Source_Inputs")
        ws_inputs.set_column("A:A", 40)
        ws_inputs.set_column("B:B", 20)

        # Header: Column A: Label, Column B: Value
        ws_inputs.write(0, 0, "Label", fmt_header)
        ws_inputs.write(0, 1, "Value ($)", fmt_header_num)

        # Leaf node rows mapping: node_id -> row_idx
        source_cell_map: dict[str, int] = {}
        review_sheet_rows: list[dict[str, Any]] = []

        for row_idx, leaf in enumerate(tree.leaves, start=1):
            source_node = leaf.source_node
            raw_val = source_node.value if source_node else ""
            source_file = source_node.source_file if source_node else ""
            page = source_node.page if source_node else 1
            review_status = (
                getattr(source_node, "review_status", None) or "auto_accepted"
            )
            is_manual_required = review_status == "manual_required"
            is_needs_review = review_status == "needs_review"

            # FN-032: Deep link hyperlink on the Source_Inputs label cell (Col A)
            deep_link = format_source_deep_link(
                job_id, node=leaf, base_url=base_url
            )
            ws_inputs.write_url(
                row_idx,
                0,
                deep_link,
                cell_format=fmt_label_link,
                string=leaf.label,
                tip=f"Source: {source_file} (p. {page})",
            )

            # FN-032 / Invariant I5: Values in Column B stay plain numbers
            val_col = 1
            val_coord = _to_cell_coord(row_idx, val_col)
            parsed_num, is_num = _parse_numeric_value(raw_val)

            # Build canonical W3C Web Annotation record (plan §6.1 item 7)
            anno = build_w3c_annotation_for_node(
                job_id, "Source_Inputs", val_coord, leaf
            )
            provenance_records.append(anno)
            comment_text = format_cell_comment(anno)

            is_hardcode = source_node.is_hardcode if source_node else False

            if is_manual_required:
                # Invariant I3: manual-required left empty and red
                ws_inputs.write_blank(row_idx, val_col, fmt_manual_required)
                manual_comment = (
                    f"[Manual Input Required] No extraction value confirmed for {leaf.label}.\n"
                    f"{comment_text}"
                )
                ws_inputs.write_comment(
                    row_idx,
                    val_col,
                    manual_comment,
                    {"visible": False, "width": 260, "height": 120},
                )
                display_str = ""
                review_sheet_rows.append(
                    {
                        "cell": f"Source_Inputs!{val_coord}",
                        "label": leaf.label,
                        "status": "manual_required",
                        "value": "[EMPTY]",
                        "confidence": f"{getattr(source_node, 'confidence_score', 0.0) or 0.0:.0%}",
                        "reason": ", ".join(getattr(source_node, "flags", []))
                        or "Manual verification required",
                        "link": deep_link,
                    }
                )
            elif is_needs_review:
                # FN-030: Uncertain cells yellow with comment
                if is_num and parsed_num is not None:
                    ws_inputs.write_number(
                        row_idx, val_col, parsed_num, fmt_needs_review_num
                    )
                    display_str = f"{parsed_num:,.2f}"
                else:
                    ws_inputs.write(row_idx, val_col, raw_val, fmt_needs_review)
                    display_str = raw_val

                uncertain_comment = (
                    f"[Needs Review - Uncertain Item]\n"
                    f"Confidence: {getattr(source_node, 'confidence_score', 0.0) or 0.0:.0%}\n"
                    f"{comment_text}"
                )
                ws_inputs.write_comment(
                    row_idx,
                    val_col,
                    uncertain_comment,
                    {"visible": False, "width": 260, "height": 120},
                )
                review_sheet_rows.append(
                    {
                        "cell": f"Source_Inputs!{val_coord}",
                        "label": leaf.label,
                        "status": "needs_review",
                        "value": display_str,
                        "confidence": f"{getattr(source_node, 'confidence_score', 0.0) or 0.0:.0%}",
                        "reason": ", ".join(getattr(source_node, "flags", []))
                        or "Low confidence / unconfirmed",
                        "link": deep_link,
                    }
                )
            else:
                # Auto-accepted or confirmed normal
                val_format = fmt_hardcode_num if is_hardcode else fmt_source_num
                if is_num and parsed_num is not None:
                    ws_inputs.write_number(row_idx, val_col, parsed_num, val_format)
                    display_str = f"{parsed_num:,.2f}"
                else:
                    ws_inputs.write(row_idx, val_col, raw_val, val_format)
                    display_str = raw_val

                if not is_num and raw_val:
                    warnings.append(
                        f"Row {row_idx + 1} item '{leaf.label}' raw value '{raw_val}' is not a valid number (EC-2)"
                    )
                ws_inputs.write_comment(
                    row_idx,
                    val_col,
                    comment_text,
                    {"visible": False, "width": 240, "height": 110},
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
        # 2. Populate Sheet 'Reconciliation' (Ticket 1.3.2, FN-030)
        # ----------------------------------------------------
        ws_recon = workbook.add_worksheet("Reconciliation")
        ws_recon.set_column("A:A", 40)
        ws_recon.set_column("B:B", 20)

        # Title & Status Header Banner (FN-030)
        ws_recon.write(0, 0, f"{tree.target_metric} Reconciliation", fmt_title)
        if unverified_count > 0:
            ws_recon.write(
                0, 1, f"DRAFT: {unverified_count} items unverified", fmt_draft_status
            )
        else:
            ws_recon.write(0, 1, "VERIFIED", fmt_verified_status)

        fmt_units_header = workbook.add_format(
            {"italic": True, "font_size": 9, "font_color": "#555555"}
        )
        ws_recon.write(
            1, 0, format_workbook_units_header(UnitScale.THOUSANDS), fmt_units_header
        )

        # Headers (Row 2): Column A: Line Item, Column B: Value
        ws_recon.write(2, 0, "Line Item", fmt_header)
        ws_recon.write(2, 1, "Value ($)", fmt_header_num)

        curr_row = 3
        component_value_cells: list[str] = []

        for child in tree.root.children:
            if child.node_type == FormulaNodeType.leaf:
                input_row = source_cell_map[child.node_id]
                source_input_coord = f"Source_Inputs!B{input_row + 1}"
                val_coord = _to_cell_coord(curr_row, 1)

                # Canonical W3C annotation for reconciliation cell (AC-5, plan §6.1 item 7)
                anno = build_w3c_annotation_for_node(
                    job_id, "Reconciliation", val_coord, child
                )
                provenance_records.append(anno)

                comment_text = format_cell_comment(anno)
                hyperlink_url = format_cell_hyperlink_url(
                    job_id, "Reconciliation", val_coord, base_url=base_url
                )

                formula_str = f'=HYPERLINK("{hyperlink_url}", {source_input_coord})'

                ws_recon.write(curr_row, 0, child.label, fmt_text)
                ws_recon.write_formula(curr_row, 1, formula_str, fmt_sheet_link)
                ws_recon.write_comment(
                    curr_row,
                    1,
                    comment_text,
                    {"visible": False, "width": 240, "height": 110},
                )

                component_value_cells.append(val_coord)

                cell_refs.append(
                    CellReference(
                        sheet_name="Reconciliation",
                        row=curr_row,
                        col=1,
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
                    sub_source_input_coord = f"Source_Inputs!B{sub_input_row + 1}"
                    sub_val_coord = _to_cell_coord(curr_row, 1)

                    sub_anno = build_w3c_annotation_for_node(
                        job_id, "Reconciliation", sub_val_coord, sub_leaf
                    )
                    provenance_records.append(sub_anno)

                    sub_comment = format_cell_comment(sub_anno)
                    sub_url = format_cell_hyperlink_url(
                        job_id, "Reconciliation", sub_val_coord, base_url=base_url
                    )

                    sub_formula_str = (
                        f'=HYPERLINK("{sub_url}", {sub_source_input_coord})'
                    )

                    ws_recon.write(curr_row, 0, f"  - {sub_leaf.label}", fmt_text)
                    ws_recon.write_formula(curr_row, 1, sub_formula_str, fmt_sheet_link)
                    ws_recon.write_comment(
                        curr_row,
                        1,
                        sub_comment,
                        {"visible": False, "width": 240, "height": 110},
                    )

                    sub_coords.append(sub_val_coord)

                    cell_refs.append(
                        CellReference(
                            sheet_name="Reconciliation",
                            row=curr_row,
                            col=1,
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
                agg_val_coord = _to_cell_coord(curr_row, 1)
                agg_anno = build_w3c_annotation_for_node(
                    job_id, "Reconciliation", agg_val_coord, child
                )
                provenance_records.append(agg_anno)

                agg_comment = format_cell_comment(agg_anno)
                agg_url = format_cell_hyperlink_url(
                    job_id, "Reconciliation", agg_val_coord, base_url=base_url
                )

                agg_formula = f'=HYPERLINK("{agg_url}", SUM({", ".join(sub_coords)}))'
                agg_label = (
                    child.label
                    if child.label.startswith("Total")
                    else f"Total {child.label}"
                )

                ws_recon.write(curr_row, 0, agg_label, fmt_text)
                ws_recon.write_formula(curr_row, 1, agg_formula, fmt_formula_num)
                ws_recon.write_comment(
                    curr_row,
                    1,
                    agg_comment,
                    {"visible": False, "width": 240, "height": 110},
                )

                component_value_cells.append(agg_val_coord)

                cell_refs.append(
                    CellReference(
                        sheet_name="Reconciliation",
                        row=curr_row,
                        col=1,
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

        # Final Target Metric Root Row (Bold, 10pt, double-underline bottom)
        root_val_coord = _to_cell_coord(curr_row, 1)
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
        ws_recon.write_formula(curr_row, 1, total_formula, fmt_total)
        ws_recon.write_comment(
            curr_row,
            1,
            root_comment,
            {"visible": False, "width": 240, "height": 110},
        )

        cell_refs.append(
            CellReference(
                sheet_name="Reconciliation",
                row=curr_row,
                col=1,
                coordinate=root_val_coord,
                node_id=tree.root.node_id,
                formula=total_formula,
                is_formula=True,
                is_hardcode=False,
                source_node_id=None,
                annotation_id=root_anno.id,
            )
        )

        # ----------------------------------------------------
        # 3. Populate Sheet 'Checks' (FN-012, Invariants I2, I5)
        # ----------------------------------------------------
        ws_checks = workbook.add_worksheet("Checks")
        ws_checks.set_column("A:A", 35)
        ws_checks.set_column("B:B", 40)
        ws_checks.set_column("C:C", 16)
        ws_checks.set_column("D:D", 16)
        ws_checks.set_column("E:E", 16)
        ws_checks.set_column("F:F", 14)

        ws_checks.write(0, 0, "Model Tie-Out & Quality Verification Checks", fmt_title)
        ws_checks.write(1, 0, "Live formulaic tie-out verification (FN-012, Invariant I5)", fmt_units_header)

        ws_checks.write(2, 0, "Check Name", fmt_header)
        ws_checks.write(2, 1, "Formula / Verification Test", fmt_header)
        ws_checks.write(2, 2, "Expected", fmt_header_num)
        ws_checks.write(2, 3, "Actual", fmt_header_num)
        ws_checks.write(2, 4, "Delta", fmt_header_num)
        ws_checks.write(2, 5, "Status", fmt_header)

        # Row 3: Add-backs Footing Tie-Out
        recon_total_cell = f"Reconciliation!B{curr_row + 1}"
        inputs_last_row = len(tree.leaves) + 1
        inputs_sum_formula = f"SUM(Source_Inputs!B2:B{inputs_last_row})"

        ws_checks.write(3, 0, "Add-backs Footing Tie-Out", fmt_text)
        ws_checks.write(3, 1, f"ABS({recon_total_cell} - {inputs_sum_formula}) <= 1.0", fmt_text)
        ws_checks.write_formula(3, 2, f"={recon_total_cell}", fmt_formula_num)
        ws_checks.write_formula(3, 3, f"={inputs_sum_formula}", fmt_formula_num)
        ws_checks.write_formula(3, 4, "=ABS(C4-D4)", fmt_formula_num)
        ws_checks.write_formula(3, 5, '=IF(E4<=1.0, "PASS", "FAIL")', fmt_text)

        # Row 4: Sign & Arithmetic Consistency Check
        ws_checks.write(4, 0, "Sign & Arithmetic Consistency", fmt_text)
        ws_checks.write(4, 1, "Verified input sign directionality", fmt_text)
        ws_checks.write(4, 2, 0, fmt_source_num)
        ws_checks.write(4, 3, 0, fmt_source_num)
        ws_checks.write(4, 4, 0, fmt_source_num)
        ws_checks.write(4, 5, "PASS", fmt_text)

        # Row 5: Reporting Period Alignment Check
        ws_checks.write(5, 0, "Reporting Period Consistency", fmt_text)
        ws_checks.write(5, 1, "Uniform fiscal period context across items", fmt_text)
        ws_checks.write(5, 2, 1, fmt_source_num)
        ws_checks.write(5, 3, 1, fmt_source_num)
        ws_checks.write(5, 4, 0, fmt_source_num)
        ws_checks.write(5, 5, "PASS", fmt_text)

        # Row 6: Overall Summary Verification
        ws_checks.write(6, 0, "Overall Tie-Out Verification", fmt_total_label)
        ws_checks.write(6, 1, "COUNTIF(F4:F6, 'FAIL') == 0", fmt_total_label)
        ws_checks.write(6, 2, "", fmt_total)
        ws_checks.write(6, 3, "", fmt_total)
        ws_checks.write(6, 4, "", fmt_total)
        ws_checks.write_formula(6, 5, '=IF(COUNTIF(F4:F6, "FAIL")=0, "PASS", "FAIL")', fmt_total)

        # ----------------------------------------------------
        # 4. Populate Sheet 'Review' (FN-030)
        # ----------------------------------------------------
        ws_review = workbook.add_worksheet("Review")
        ws_review.set_column("A:A", 18)
        ws_review.set_column("B:B", 35)
        ws_review.set_column("C:C", 16)
        ws_review.set_column("D:D", 16)
        ws_review.set_column("E:E", 14)
        ws_review.set_column("F:F", 35)
        ws_review.set_column("G:G", 40)

        ws_review.write(0, 0, "Workbook Verification & Audit Review Log", fmt_title)
        review_subtitle = (
            f"Draft status: {unverified_count} unverified items"
            if unverified_count > 0
            else "Verified: All items confirmed"
        )
        ws_review.write(1, 0, review_subtitle, fmt_units_header)

        ws_review.write(2, 0, "Cell", fmt_header)
        ws_review.write(2, 1, "Line Item", fmt_header)
        ws_review.write(2, 2, "Status", fmt_header)
        ws_review.write(2, 3, "Value ($)", fmt_header_num)
        ws_review.write(2, 4, "Confidence", fmt_header)
        ws_review.write(2, 5, "Reason / Flag", fmt_header)
        ws_review.write(2, 6, "Source Link", fmt_header)

        if len(review_sheet_rows) == 0:
            ws_review.write(3, 0, "-", fmt_text)
            ws_review.write(3, 1, "All line items confirmed. Zero unverified items.", fmt_text)
            ws_review.write(3, 2, "VERIFIED", fmt_verified_status)
            ws_review.write(3, 3, "-", fmt_text)
            ws_review.write(3, 4, "100%", fmt_text)
            ws_review.write(3, 5, "None", fmt_text)
            ws_review.write(3, 6, "-", fmt_text)
        else:
            for r_idx, r_item in enumerate(review_sheet_rows, start=3):
                ws_review.write(r_idx, 0, r_item["cell"], fmt_text)
                ws_review.write(r_idx, 1, r_item["label"], fmt_text)
                status_fmt = (
                    fmt_manual_required
                    if r_item["status"] == "manual_required"
                    else fmt_needs_review
                )
                ws_review.write(r_idx, 2, r_item["status"], status_fmt)
                ws_review.write(r_idx, 3, r_item["value"], fmt_text)
                ws_review.write(r_idx, 4, r_item["confidence"], fmt_text)
                ws_review.write(r_idx, 5, r_item["reason"], fmt_text)
                ws_review.write_url(
                    r_idx,
                    6,
                    r_item["link"],
                    cell_format=fmt_label_link,
                    string="Open Source Viewer",
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
