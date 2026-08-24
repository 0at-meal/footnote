"""
6-Tab Multi-Statement Excel Compiler (Phase C).

Unifies single-year and multi-year financial modeling into a 6-sheet workbook:
1. Executive_Summary (KPIs & cross-sheet links)
2. Income_Statement (GAAP/IFRS Revenue -> Net Income DAG)
3. EBITDA_Bridge (Cross-sheet EBIT -> Adjusted EBITDA reconciliation)
4. Cash_Flow (Operating CF, CapEx, FCFF, Financing)
5. Balance_Sheet (Assets, Liabilities, Equity, Net Debt)
6. Audit_Trail (Cell-level provenance audit log)

Enforces CONSTITUTION:
- § 1.1: mypy --strict compliance
- § 1.5: Zero numeric literals in derived/formula cells
- § 2.5: IB formatting: blue = hardcode, black = formula, green = cross-sheet link
- § 4.2: xlsxwriter only, fresh workbook generation from scratch
- § 6.4: Cell comments with W3C Web Annotation provenance attached
"""

import logging
import os
from pathlib import Path

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
from app.formula_engine.models import (
    ComprehensiveModelTree,
)
from app.ingestion.models import CompanyRecord, JobRecord

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"
_IB_CURRENCY_FORMAT: str = '$#,##0;($#,##0);"-"'
_PERCENT_FORMAT: str = "0.0%"
_INTEGER_FORMAT: str = "#,##0"


def _parse_numeric_value(raw_val: str) -> tuple[float | None, bool]:
    """
    Parses a raw extracted string value into a float, supporting commas and parentheses.
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
    """Converts 0-indexed (row, col) to Excel A1-style coordinate (e.g. 'B4')."""
    return f"{_col_to_letter(col_idx)}{row_idx + 1}"


def generate_multi_statement_workbook(
    company: CompanyRecord | None,
    year_trees: list[tuple[JobRecord, ComprehensiveModelTree]],
    output_dir: Path | None = None,
) -> WorkbookGenerationResult:
    """
    Generates a 6-tab multi-statement workbook with live cross-sheet formulas
    and cell-level provenance metadata.
    """
    base_dir = output_dir or _DEFAULT_DATA_DIR
    models_dir = base_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    if not year_trees:
        return WorkbookGenerationResult(
            job_id="none",
            file_path="",
            target_metric="Full Model",
            is_success=False,
            error_detail="No statement trees provided for workbook generation.",
        )

    # Sort year trees chronologically by filing_year ascending
    sorted_years = sorted(
        year_trees, key=lambda yt: (yt[0].filing_year or 0, yt[0].submitted_at)
    )
    primary_job = sorted_years[0][0]
    primary_job_id = primary_job.job_id

    # Determine workbook file path
    is_multi_year = len(sorted_years) > 1
    company_name = company.name if company else "Financial_Model"
    clean_company_slug = "".join(c if c.isalnum() else "_" for c in company_name).strip(
        "_"
    )

    if is_multi_year and company:
        dest_filename = f"company_{company.company_id}_full_model.xlsx"
    elif is_multi_year:
        dest_filename = f"{clean_company_slug}_multi_year_model.xlsx"
    else:
        dest_filename = f"{primary_job_id}_model.xlsx"

    dest_path = models_dir / dest_filename
    tmp_path = models_dir / f"{dest_filename}.tmp"

    sheet_names = [
        "Executive_Summary",
        "Income_Statement",
        "EBITDA_Bridge",
        "Cash_Flow",
        "Balance_Sheet",
        "Audit_Trail",
    ]

    cell_references: list[CellReference] = []
    provenance_records: list[W3CAnnotationRecord] = []
    warnings: list[str] = []
    total_cells = 0
    formula_cells = 0
    source_cells = 0

    try:
        workbook = xlsxwriter.Workbook(str(tmp_path))

        # --- FORMATS (CONSTITUTION § 2.5) ---
        fmt_title = workbook.add_format(
            {
                "bold": True,
                "font_size": 14,
                "font_name": "Calibri",
                "font_color": "#1E293B",
            }
        )
        fmt_section = workbook.add_format(
            {
                "bold": True,
                "font_size": 11,
                "font_name": "Calibri",
                "font_color": "#0F172A",
                "bg_color": "#F1F5F9",
                "bottom": 1,
            }
        )
        fmt_header_col = workbook.add_format(
            {
                "bold": True,
                "font_size": 11,
                "font_name": "Calibri",
                "font_color": "#FFFFFF",
                "bg_color": "#1E293B",
                "align": "center",
                "bottom": 2,
            }
        )
        fmt_header_label = workbook.add_format(
            {
                "bold": True,
                "font_size": 11,
                "font_name": "Calibri",
                "font_color": "#FFFFFF",
                "bg_color": "#1E293B",
                "align": "left",
                "bottom": 2,
            }
        )
        fmt_label = workbook.add_format(
            {
                "font_name": "Calibri",
                "font_size": 11,
                "font_color": "#1E293B",
            }
        )
        fmt_label_indent = workbook.add_format(
            {
                "font_name": "Calibri",
                "font_size": 11,
                "font_color": "#475569",
                "indent": 1,
            }
        )
        fmt_hardcode = workbook.add_format(
            {
                "font_name": "Calibri",
                "font_size": 11,
                "font_color": "#0000FF",  # IB Blue for hardcoded source items (CONSTITUTION § 2.5)
                "num_format": _IB_CURRENCY_FORMAT,
                "align": "right",
            }
        )
        fmt_formula = workbook.add_format(
            {
                "font_name": "Calibri",
                "font_size": 11,
                "font_color": "#000000",  # IB Black for standard formula cells
                "num_format": _IB_CURRENCY_FORMAT,
                "align": "right",
            }
        )
        fmt_link = workbook.add_format(
            {
                "font_name": "Calibri",
                "font_size": 11,
                "font_color": "#15803D",  # IB Green for cross-sheet links
                "num_format": _IB_CURRENCY_FORMAT,
                "align": "right",
            }
        )
        fmt_percent_link = workbook.add_format(
            {
                "font_name": "Calibri",
                "font_size": 11,
                "font_color": "#15803D",
                "num_format": _PERCENT_FORMAT,
                "align": "right",
            }
        )

        fmt_total = workbook.add_format(
            {
                "bold": True,
                "font_name": "Calibri",
                "font_size": 11,
                "font_color": "#000000",
                "num_format": _IB_CURRENCY_FORMAT,
                "align": "right",
                "top": 1,
                "bottom": 6,  # Double-underline (CONSTITUTION § 2.5)
            }
        )
        fmt_total_label = workbook.add_format(
            {
                "bold": True,
                "font_name": "Calibri",
                "font_size": 11,
                "font_color": "#000000",
                "top": 1,
                "bottom": 6,
            }
        )
        fmt_audit_header = workbook.add_format(
            {
                "bold": True,
                "font_size": 10,
                "font_name": "Calibri",
                "font_color": "#FFFFFF",
                "bg_color": "#334155",
                "bottom": 2,
            }
        )
        fmt_audit_cell = workbook.add_format(
            {
                "font_name": "Calibri",
                "font_size": 9,
                "font_color": "#334155",
            }
        )

        # Create worksheets
        ws_summary = workbook.add_worksheet("Executive_Summary")
        ws_is = workbook.add_worksheet("Income_Statement")
        ws_bridge = workbook.add_worksheet("EBITDA_Bridge")
        ws_cf = workbook.add_worksheet("Cash_Flow")
        ws_bs = workbook.add_worksheet("Balance_Sheet")
        ws_audit = workbook.add_worksheet("Audit_Trail")

        # Set column widths
        for ws in [ws_summary, ws_is, ws_bridge, ws_cf, ws_bs]:
            ws.set_column(0, 0, 38)
            for y_idx in range(len(sorted_years)):
                ws.set_column(y_idx + 1, y_idx + 1, 18)

        ws_audit.set_column(0, 0, 18)  # Sheet
        ws_audit.set_column(1, 1, 10)  # Cell
        ws_audit.set_column(2, 2, 32)  # Label
        ws_audit.set_column(3, 3, 16)  # Value
        ws_audit.set_column(4, 4, 25)  # Source File
        ws_audit.set_column(5, 5, 8)  # Page
        ws_audit.set_column(6, 6, 32)  # BBox
        ws_audit.set_column(7, 7, 36)  # Job ID

        # Write column headers on financial statement sheets
        for ws, title_text in [
            (ws_summary, f"{company_name} — Executive Summary"),
            (ws_is, f"{company_name} — Consolidated Statements of Income"),
            (ws_bridge, f"{company_name} — Non-GAAP EBITDA Reconciliation Bridge"),
            (ws_cf, f"{company_name} — Consolidated Statements of Cash Flows"),
            (ws_bs, f"{company_name} — Consolidated Balance Sheets"),
        ]:
            ws.write(0, 0, title_text, fmt_title)
            ws.write(2, 0, "Line Item", fmt_header_label)
            for y_idx, (job, _) in enumerate(sorted_years):
                year_label = (
                    f"FY{job.filing_year}" if job.filing_year else f"Period {y_idx + 1}"
                )
                ws.write(2, y_idx + 1, year_label, fmt_header_col)

        # Coordinate maps for cross-sheet references: map[(sheet_name, canonical_name, year_idx)] -> cell_coord
        cell_coord_map: dict[tuple[str, str, int], str] = {}

        # -------------------------------------------------------------
        # TAB 2: INCOME STATEMENT
        # -------------------------------------------------------------
        is_structure = [
            ("Revenue", False, False, False),
            ("Cost of Revenue", False, False, False),
            ("Gross Profit", True, True, False),  # Formula row: Rev - COGS
            ("Operating Expenses", False, False, True),  # Section header
            ("Research & Development", False, False, False),
            ("Sales & Marketing", False, False, False),
            ("General & Administrative", False, False, False),
            ("Total Operating Expenses", True, True, False),  # Formula row: SUM(OpEx)
            ("Operating Income", True, True, False),  # Formula row: GP - OpEx
            ("Non-Operating & Taxes", False, False, True),  # Section header
            ("Interest Income", False, False, False),
            ("Interest Expense", False, False, False),
            ("Other Income / Expense Net", False, False, False),
            ("Income Before Income Taxes", True, False, False),
            ("Provision for Income Taxes", False, False, False),
            ("Net Income", True, True, False),  # Formula row: EBT - Tax
            ("Diluted EPS", False, False, False),
        ]

        curr_row = 3
        for item_label, is_calc, is_total, is_section in is_structure:
            if is_section:
                ws_is.write(curr_row, 0, item_label, fmt_section)
                for y_idx in range(len(sorted_years)):
                    ws_is.write_blank(curr_row, y_idx + 1, None, fmt_section)
                curr_row += 1
                continue

            lbl_format = fmt_total_label if is_total else fmt_label
            ws_is.write(curr_row, 0, item_label, lbl_format)

            for y_idx, (job, comp_tree) in enumerate(sorted_years):
                coord = _to_cell_coord(curr_row, y_idx + 1)
                cell_coord_map[("Income_Statement", item_label, y_idx)] = coord
                col_letter = _col_to_letter(y_idx + 1)

                is_tree = comp_tree.income_statement_tree
                leaf_node = None
                if is_tree:
                    for leaf in is_tree.leaves:
                        if (
                            leaf.source_node
                            and leaf.source_node.normalized_label == item_label
                        ):
                            leaf_node = leaf
                            break

                if item_label == "Gross Profit":
                    rev_coord = cell_coord_map.get(
                        ("Income_Statement", "Revenue", y_idx), f"{col_letter}4"
                    )
                    cogs_coord = cell_coord_map.get(
                        ("Income_Statement", "Cost of Revenue", y_idx), f"{col_letter}5"
                    )
                    formula = f"={rev_coord}-{cogs_coord}"
                    ws_is.write_formula(curr_row, y_idx + 1, formula, fmt_total)
                    formula_cells += 1
                    total_cells += 1
                    cell_references.append(
                        CellReference(
                            sheet_name="Income_Statement",
                            row=curr_row,
                            col=y_idx + 1,
                            coordinate=coord,
                            formula=formula,
                            is_formula=True,
                        )
                    )
                elif item_label == "Total Operating Expenses":
                    rd_coord = cell_coord_map.get(
                        ("Income_Statement", "Research & Development", y_idx),
                        f"{col_letter}8",
                    )
                    ga_coord = cell_coord_map.get(
                        ("Income_Statement", "General & Administrative", y_idx),
                        f"{col_letter}10",
                    )
                    formula = f"=SUM({rd_coord}:{ga_coord})"
                    ws_is.write_formula(curr_row, y_idx + 1, formula, fmt_total)
                    formula_cells += 1
                    total_cells += 1
                    cell_references.append(
                        CellReference(
                            sheet_name="Income_Statement",
                            row=curr_row,
                            col=y_idx + 1,
                            coordinate=coord,
                            formula=formula,
                            is_formula=True,
                        )
                    )
                elif item_label == "Operating Income":
                    gp_coord = cell_coord_map.get(
                        ("Income_Statement", "Gross Profit", y_idx), f"{col_letter}6"
                    )
                    opex_coord = cell_coord_map.get(
                        ("Income_Statement", "Total Operating Expenses", y_idx),
                        f"{col_letter}11",
                    )
                    formula = f"={gp_coord}-{opex_coord}"
                    ws_is.write_formula(curr_row, y_idx + 1, formula, fmt_total)
                    formula_cells += 1
                    total_cells += 1
                    cell_references.append(
                        CellReference(
                            sheet_name="Income_Statement",
                            row=curr_row,
                            col=y_idx + 1,
                            coordinate=coord,
                            formula=formula,
                            is_formula=True,
                        )
                    )
                elif item_label == "Income Before Income Taxes":
                    ebit_coord = cell_coord_map.get(
                        ("Income_Statement", "Operating Income", y_idx),
                        f"{col_letter}12",
                    )
                    int_inc_coord = cell_coord_map.get(
                        ("Income_Statement", "Interest Income", y_idx),
                        f"{col_letter}14",
                    )
                    int_exp_coord = cell_coord_map.get(
                        ("Income_Statement", "Interest Expense", y_idx),
                        f"{col_letter}15",
                    )
                    other_coord = cell_coord_map.get(
                        ("Income_Statement", "Other Income / Expense Net", y_idx),
                        f"{col_letter}16",
                    )
                    formula = (
                        f"={ebit_coord}+{int_inc_coord}-{int_exp_coord}+{other_coord}"
                    )
                    ws_is.write_formula(curr_row, y_idx + 1, formula, fmt_formula)
                    formula_cells += 1
                    total_cells += 1
                    cell_references.append(
                        CellReference(
                            sheet_name="Income_Statement",
                            row=curr_row,
                            col=y_idx + 1,
                            coordinate=coord,
                            formula=formula,
                            is_formula=True,
                        )
                    )
                elif item_label == "Net Income":
                    ebt_coord = cell_coord_map.get(
                        ("Income_Statement", "Income Before Income Taxes", y_idx),
                        f"{col_letter}17",
                    )
                    tax_coord = cell_coord_map.get(
                        ("Income_Statement", "Provision for Income Taxes", y_idx),
                        f"{col_letter}18",
                    )
                    formula = f"={ebt_coord}-{tax_coord}"
                    ws_is.write_formula(curr_row, y_idx + 1, formula, fmt_total)
                    formula_cells += 1
                    total_cells += 1
                    cell_references.append(
                        CellReference(
                            sheet_name="Income_Statement",
                            row=curr_row,
                            col=y_idx + 1,
                            coordinate=coord,
                            formula=formula,
                            is_formula=True,
                        )
                    )
                else:
                    # Leaf value cell
                    if leaf_node and leaf_node.source_node:
                        num_val, valid = _parse_numeric_value(
                            leaf_node.source_node.value
                        )
                        val_to_write = num_val if valid else 0.0
                        ws_is.write_number(
                            curr_row, y_idx + 1, val_to_write, fmt_hardcode
                        )
                        # Attach provenance comment (CONSTITUTION § 6.4)
                        anno = build_w3c_annotation_for_node(
                            job_id=job.job_id,
                            sheet_name="Income_Statement",
                            cell_coord=coord,
                            node=leaf_node,
                        )
                        comment_text = format_cell_comment(anno)
                        ws_is.write_comment(
                            curr_row,
                            y_idx + 1,
                            comment_text,
                            {"x_scale": 1.4, "y_scale": 1.2},
                        )
                        provenance_records.append(anno)
                        source_cells += 1
                        total_cells += 1
                        cell_references.append(
                            CellReference(
                                sheet_name="Income_Statement",
                                row=curr_row,
                                col=y_idx + 1,
                                coordinate=coord,
                                is_hardcode=True,
                                source_node_id=leaf_node.source_node.node_id,
                                annotation_id=anno.id,
                            )
                        )
                    else:
                        ws_is.write_number(curr_row, y_idx + 1, 0.0, fmt_hardcode)
                        source_cells += 1
                        total_cells += 1
                        cell_references.append(
                            CellReference(
                                sheet_name="Income_Statement",
                                row=curr_row,
                                col=y_idx + 1,
                                coordinate=coord,
                                is_hardcode=True,
                            )
                        )

            curr_row += 1

        # -------------------------------------------------------------
        # TAB 3: EBITDA BRIDGE
        # -------------------------------------------------------------
        bridge_addback_labels = [
            "Stock-Based Compensation",
            "Amortization of Intangibles",
            "Restructuring Charges",
            "Litigation Charges",
            "Lease Adjustments",
            "Acquisition-Related Expenses",
            "Impairment of Assets",
            "Gain/Loss on Divestitures",
            "Foreign Currency Adjustments",
            "Other Non-Operating Expenses",
        ]

        ws_bridge.write(3, 0, "Operating Income (EBIT)", fmt_label)
        for y_idx in range(len(sorted_years)):
            ebit_is_coord = cell_coord_map.get(
                ("Income_Statement", "Operating Income", y_idx),
                f"{_col_to_letter(y_idx+1)}12",
            )
            cross_formula = f"='Income_Statement'!{ebit_is_coord}"
            ws_bridge.write_formula(3, y_idx + 1, cross_formula, fmt_link)
            bridge_ebit_coord = _to_cell_coord(3, y_idx + 1)
            cell_coord_map[("EBITDA_Bridge", "Operating Income", y_idx)] = (
                bridge_ebit_coord
            )
            formula_cells += 1
            total_cells += 1
            cell_references.append(
                CellReference(
                    sheet_name="EBITDA_Bridge",
                    row=3,
                    col=y_idx + 1,
                    coordinate=bridge_ebit_coord,
                    formula=cross_formula,
                    is_formula=True,
                )
            )

        ws_bridge.write(4, 0, "Non-GAAP Adjustments", fmt_section)
        for y_idx in range(len(sorted_years)):
            ws_bridge.write_blank(4, y_idx + 1, None, fmt_section)

        curr_b_row = 5
        for ab_label in bridge_addback_labels:
            ws_bridge.write(curr_b_row, 0, ab_label, fmt_label_indent)
            for y_idx, (job, comp_tree) in enumerate(sorted_years):
                coord = _to_cell_coord(curr_b_row, y_idx + 1)
                b_tree = comp_tree.ebitda_bridge_tree
                leaf_node = None
                if b_tree:
                    for leaf in b_tree.leaves:
                        if (
                            leaf.source_node
                            and leaf.source_node.normalized_label == ab_label
                        ):
                            leaf_node = leaf
                            break

                if leaf_node and leaf_node.source_node:
                    num_val, valid = _parse_numeric_value(leaf_node.source_node.value)
                    val_to_write = num_val if valid else 0.0
                    ws_bridge.write_number(
                        curr_b_row, y_idx + 1, val_to_write, fmt_hardcode
                    )
                    anno = build_w3c_annotation_for_node(
                        job_id=job.job_id,
                        sheet_name="EBITDA_Bridge",
                        cell_coord=coord,
                        node=leaf_node,
                    )
                    comment_text = format_cell_comment(anno)
                    ws_bridge.write_comment(
                        curr_b_row,
                        y_idx + 1,
                        comment_text,
                        {"x_scale": 1.4, "y_scale": 1.2},
                    )
                    provenance_records.append(anno)
                    source_cells += 1
                    total_cells += 1
                    cell_references.append(
                        CellReference(
                            sheet_name="EBITDA_Bridge",
                            row=curr_b_row,
                            col=y_idx + 1,
                            coordinate=coord,
                            is_hardcode=True,
                            source_node_id=leaf_node.source_node.node_id,
                            annotation_id=anno.id,
                        )
                    )
                else:
                    ws_bridge.write_number(curr_b_row, y_idx + 1, 0.0, fmt_hardcode)
                    source_cells += 1
                    total_cells += 1
                    cell_references.append(
                        CellReference(
                            sheet_name="EBITDA_Bridge",
                            row=curr_b_row,
                            col=y_idx + 1,
                            coordinate=coord,
                            is_hardcode=True,
                        )
                    )

            curr_b_row += 1

        # Adjusted EBITDA Total Row
        ws_bridge.write(curr_b_row, 0, "Adjusted EBITDA", fmt_total_label)
        for y_idx in range(len(sorted_years)):
            col_letter = _col_to_letter(y_idx + 1)
            coord = _to_cell_coord(curr_b_row, y_idx + 1)
            cell_coord_map[("EBITDA_Bridge", "Adjusted EBITDA", y_idx)] = coord
            formula = f"=SUM({col_letter}4:{col_letter}{curr_b_row})"
            ws_bridge.write_formula(curr_b_row, y_idx + 1, formula, fmt_total)
            formula_cells += 1
            total_cells += 1
            cell_references.append(
                CellReference(
                    sheet_name="EBITDA_Bridge",
                    row=curr_b_row,
                    col=y_idx + 1,
                    coordinate=coord,
                    formula=formula,
                    is_formula=True,
                )
            )

        # -------------------------------------------------------------
        # TAB 4: CASH FLOW
        # -------------------------------------------------------------
        cf_structure = [
            ("Cash Flows from Operating Activities", False, False, True),
            ("Net Income (CF)", False, False, False),
            ("Depreciation & Amortization (CF)", False, False, False),
            ("Stock-Based Compensation (CF)", False, False, False),
            ("Deferred Income Taxes (CF)", False, False, False),
            ("Other Non-Cash Items (CF)", False, False, False),
            ("Change in Working Capital", False, False, False),
            ("Cash Provided by Operating Activities", True, True, False),  # OCF Total
            ("Cash Flows from Investing Activities", False, False, True),
            ("Capital Expenditures", False, False, False),
            ("Purchases of Marketable Securities", False, False, False),
            ("Proceeds from Marketable Securities", False, False, False),
            ("Cash Used in Investing Activities", True, True, False),
            ("Free Cash Flow Calculation", False, False, True),
            ("Free Cash Flow", True, True, False),  # FCFF = OCF - CapEx
            ("Cash Flows from Financing Activities", False, False, True),
            ("Proceeds from / Repayments of Debt", False, False, False),
            ("Repurchases of Common Stock", False, False, False),
            ("Dividends Paid", False, False, False),
            ("Cash Used in Financing Activities", True, True, False),
        ]

        curr_cf_row = 3
        for item_label, is_calc, is_total, is_section in cf_structure:
            if is_section:
                ws_cf.write(curr_cf_row, 0, item_label, fmt_section)
                for y_idx in range(len(sorted_years)):
                    ws_cf.write_blank(curr_cf_row, y_idx + 1, None, fmt_section)
                curr_cf_row += 1
                continue

            lbl_format = fmt_total_label if is_total else fmt_label
            ws_cf.write(curr_cf_row, 0, item_label, lbl_format)

            for y_idx, (job, comp_tree) in enumerate(sorted_years):
                coord = _to_cell_coord(curr_cf_row, y_idx + 1)
                cell_coord_map[("Cash_Flow", item_label, y_idx)] = coord
                col_letter = _col_to_letter(y_idx + 1)
                cf_tree = comp_tree.cash_flow_tree

                leaf_node = None
                if cf_tree:
                    for leaf in cf_tree.leaves:
                        if (
                            leaf.source_node
                            and leaf.source_node.normalized_label == item_label
                        ):
                            leaf_node = leaf
                            break

                if item_label == "Cash Provided by Operating Activities":
                    formula = f"=SUM({col_letter}5:{col_letter}10)"
                    ws_cf.write_formula(curr_cf_row, y_idx + 1, formula, fmt_total)
                    formula_cells += 1
                    total_cells += 1
                    cell_references.append(
                        CellReference(
                            sheet_name="Cash_Flow",
                            row=curr_cf_row,
                            col=y_idx + 1,
                            coordinate=coord,
                            formula=formula,
                            is_formula=True,
                        )
                    )
                elif item_label == "Cash Used in Investing Activities":
                    formula = f"=SUM({col_letter}13:{col_letter}15)"
                    ws_cf.write_formula(curr_cf_row, y_idx + 1, formula, fmt_total)
                    formula_cells += 1
                    total_cells += 1
                    cell_references.append(
                        CellReference(
                            sheet_name="Cash_Flow",
                            row=curr_cf_row,
                            col=y_idx + 1,
                            coordinate=coord,
                            formula=formula,
                            is_formula=True,
                        )
                    )
                elif item_label == "Free Cash Flow":
                    ocf_coord = cell_coord_map.get(
                        ("Cash_Flow", "Cash Provided by Operating Activities", y_idx),
                        f"{col_letter}11",
                    )
                    capex_coord = cell_coord_map.get(
                        ("Cash_Flow", "Capital Expenditures", y_idx), f"{col_letter}13"
                    )
                    formula = f"={ocf_coord}-{capex_coord}"
                    ws_cf.write_formula(curr_cf_row, y_idx + 1, formula, fmt_total)
                    formula_cells += 1
                    total_cells += 1
                    cell_references.append(
                        CellReference(
                            sheet_name="Cash_Flow",
                            row=curr_cf_row,
                            col=y_idx + 1,
                            coordinate=coord,
                            formula=formula,
                            is_formula=True,
                        )
                    )
                elif item_label == "Cash Used in Financing Activities":
                    formula = f"=SUM({col_letter}19:{col_letter}21)"
                    ws_cf.write_formula(curr_cf_row, y_idx + 1, formula, fmt_total)
                    formula_cells += 1
                    total_cells += 1
                    cell_references.append(
                        CellReference(
                            sheet_name="Cash_Flow",
                            row=curr_cf_row,
                            col=y_idx + 1,
                            coordinate=coord,
                            formula=formula,
                            is_formula=True,
                        )
                    )
                else:
                    if leaf_node and leaf_node.source_node:
                        num_val, valid = _parse_numeric_value(
                            leaf_node.source_node.value
                        )
                        val_to_write = num_val if valid else 0.0
                        ws_cf.write_number(
                            curr_cf_row, y_idx + 1, val_to_write, fmt_hardcode
                        )
                        anno = build_w3c_annotation_for_node(
                            job_id=job.job_id,
                            sheet_name="Cash_Flow",
                            cell_coord=coord,
                            node=leaf_node,
                        )
                        comment_text = format_cell_comment(anno)
                        ws_cf.write_comment(
                            curr_cf_row,
                            y_idx + 1,
                            comment_text,
                            {"x_scale": 1.4, "y_scale": 1.2},
                        )
                        provenance_records.append(anno)
                        source_cells += 1
                        total_cells += 1
                        cell_references.append(
                            CellReference(
                                sheet_name="Cash_Flow",
                                row=curr_cf_row,
                                col=y_idx + 1,
                                coordinate=coord,
                                is_hardcode=True,
                                source_node_id=leaf_node.source_node.node_id,
                                annotation_id=anno.id,
                            )
                        )
                    else:
                        ws_cf.write_number(curr_cf_row, y_idx + 1, 0.0, fmt_hardcode)
                        source_cells += 1
                        total_cells += 1
                        cell_references.append(
                            CellReference(
                                sheet_name="Cash_Flow",
                                row=curr_cf_row,
                                col=y_idx + 1,
                                coordinate=coord,
                                is_hardcode=True,
                            )
                        )

            curr_cf_row += 1

        # -------------------------------------------------------------
        # TAB 5: BALANCE SHEET
        # -------------------------------------------------------------
        bs_structure = [
            ("Current Assets", False, False, True),
            ("Cash and Cash Equivalents", False, False, False),
            ("Short-Term Investments", False, False, False),
            ("Accounts Receivable", False, False, False),
            ("Inventory", False, False, False),
            ("Other Current Assets", False, False, False),
            ("Total Current Assets", True, True, False),
            ("Non-Current Assets", False, False, True),
            ("Property, Plant and Equipment, Net", False, False, False),
            ("Goodwill", False, False, False),
            ("Intangible Assets, Net", False, False, False),
            ("Total Assets", True, True, False),
            ("Current Liabilities", False, False, True),
            ("Accounts Payable", False, False, False),
            ("Accrued Expenses and Other Current Liabilities", False, False, False),
            ("Short-Term Debt", False, False, False),
            ("Total Current Liabilities", True, True, False),
            ("Long-Term Liabilities", False, False, True),
            ("Long-Term Debt", False, False, False),
            ("Total Liabilities", True, True, False),
            ("Stockholders' Equity", False, False, True),
            ("Retained Earnings", False, False, False),
            ("Total Stockholders' Equity", True, True, False),
            ("Total Liabilities & Stockholders' Equity", True, True, False),
            ("Net Debt Analysis", False, False, True),
            (
                "Net Debt",
                True,
                True,
                False,
            ),  # Formula: (ST Debt + LT Debt) - (Cash + ST Inv)
        ]

        curr_bs_row = 3
        for item_label, is_calc, is_total, is_section in bs_structure:
            if is_section:
                ws_bs.write(curr_bs_row, 0, item_label, fmt_section)
                for y_idx in range(len(sorted_years)):
                    ws_bs.write_blank(curr_bs_row, y_idx + 1, None, fmt_section)
                curr_bs_row += 1
                continue

            lbl_format = fmt_total_label if is_total else fmt_label
            ws_bs.write(curr_bs_row, 0, item_label, lbl_format)

            for y_idx, (job, comp_tree) in enumerate(sorted_years):
                coord = _to_cell_coord(curr_bs_row, y_idx + 1)
                cell_coord_map[("Balance_Sheet", item_label, y_idx)] = coord
                col_letter = _col_to_letter(y_idx + 1)
                bs_tree = comp_tree.balance_sheet_tree

                leaf_node = None
                if bs_tree:
                    for leaf in bs_tree.leaves:
                        if (
                            leaf.source_node
                            and leaf.source_node.normalized_label == item_label
                        ):
                            leaf_node = leaf
                            break

                if item_label == "Total Current Assets":
                    formula = f"=SUM({col_letter}5:{col_letter}9)"
                    ws_bs.write_formula(curr_bs_row, y_idx + 1, formula, fmt_total)
                    formula_cells += 1
                    total_cells += 1
                    cell_references.append(
                        CellReference(
                            sheet_name="Balance_Sheet",
                            row=curr_bs_row,
                            col=y_idx + 1,
                            coordinate=coord,
                            formula=formula,
                            is_formula=True,
                        )
                    )
                elif item_label == "Total Assets":
                    tca_coord = cell_coord_map.get(
                        ("Balance_Sheet", "Total Current Assets", y_idx),
                        f"{col_letter}10",
                    )
                    formula = f"={tca_coord}+SUM({col_letter}12:{col_letter}14)"
                    ws_bs.write_formula(curr_bs_row, y_idx + 1, formula, fmt_total)
                    formula_cells += 1
                    total_cells += 1
                    cell_references.append(
                        CellReference(
                            sheet_name="Balance_Sheet",
                            row=curr_bs_row,
                            col=y_idx + 1,
                            coordinate=coord,
                            formula=formula,
                            is_formula=True,
                        )
                    )
                elif item_label == "Total Current Liabilities":
                    formula = f"=SUM({col_letter}17:{col_letter}19)"
                    ws_bs.write_formula(curr_bs_row, y_idx + 1, formula, fmt_total)
                    formula_cells += 1
                    total_cells += 1
                    cell_references.append(
                        CellReference(
                            sheet_name="Balance_Sheet",
                            row=curr_bs_row,
                            col=y_idx + 1,
                            coordinate=coord,
                            formula=formula,
                            is_formula=True,
                        )
                    )
                elif item_label == "Total Liabilities":
                    tcl_coord = cell_coord_map.get(
                        ("Balance_Sheet", "Total Current Liabilities", y_idx),
                        f"{col_letter}20",
                    )
                    ltd_coord = cell_coord_map.get(
                        ("Balance_Sheet", "Long-Term Debt", y_idx), f"{col_letter}22"
                    )
                    formula = f"={tcl_coord}+{ltd_coord}"
                    ws_bs.write_formula(curr_bs_row, y_idx + 1, formula, fmt_total)
                    formula_cells += 1
                    total_cells += 1
                    cell_references.append(
                        CellReference(
                            sheet_name="Balance_Sheet",
                            row=curr_bs_row,
                            col=y_idx + 1,
                            coordinate=coord,
                            formula=formula,
                            is_formula=True,
                        )
                    )
                elif item_label == "Total Liabilities & Stockholders' Equity":
                    tot_liab = cell_coord_map.get(
                        ("Balance_Sheet", "Total Liabilities", y_idx), f"{col_letter}23"
                    )
                    tot_eq = cell_coord_map.get(
                        ("Balance_Sheet", "Total Stockholders' Equity", y_idx),
                        f"{col_letter}26",
                    )
                    formula = f"={tot_liab}+{tot_eq}"
                    ws_bs.write_formula(curr_bs_row, y_idx + 1, formula, fmt_total)
                    formula_cells += 1
                    total_cells += 1
                    cell_references.append(
                        CellReference(
                            sheet_name="Balance_Sheet",
                            row=curr_bs_row,
                            col=y_idx + 1,
                            coordinate=coord,
                            formula=formula,
                            is_formula=True,
                        )
                    )
                elif item_label == "Net Debt":
                    st_debt = cell_coord_map.get(
                        ("Balance_Sheet", "Short-Term Debt", y_idx), f"{col_letter}19"
                    )
                    lt_debt = cell_coord_map.get(
                        ("Balance_Sheet", "Long-Term Debt", y_idx), f"{col_letter}22"
                    )
                    cash = cell_coord_map.get(
                        ("Balance_Sheet", "Cash and Cash Equivalents", y_idx),
                        f"{col_letter}5",
                    )
                    st_inv = cell_coord_map.get(
                        ("Balance_Sheet", "Short-Term Investments", y_idx),
                        f"{col_letter}6",
                    )
                    formula = f"=({st_debt}+{lt_debt})-({cash}+{st_inv})"
                    ws_bs.write_formula(curr_bs_row, y_idx + 1, formula, fmt_total)
                    formula_cells += 1
                    total_cells += 1
                    cell_references.append(
                        CellReference(
                            sheet_name="Balance_Sheet",
                            row=curr_bs_row,
                            col=y_idx + 1,
                            coordinate=coord,
                            formula=formula,
                            is_formula=True,
                        )
                    )
                else:
                    if leaf_node and leaf_node.source_node:
                        num_val, valid = _parse_numeric_value(
                            leaf_node.source_node.value
                        )
                        val_to_write = num_val if valid else 0.0
                        ws_bs.write_number(
                            curr_bs_row, y_idx + 1, val_to_write, fmt_hardcode
                        )
                        anno = build_w3c_annotation_for_node(
                            job_id=job.job_id,
                            sheet_name="Balance_Sheet",
                            cell_coord=coord,
                            node=leaf_node,
                        )
                        comment_text = format_cell_comment(anno)
                        ws_bs.write_comment(
                            curr_bs_row,
                            y_idx + 1,
                            comment_text,
                            {"x_scale": 1.4, "y_scale": 1.2},
                        )
                        provenance_records.append(anno)
                        source_cells += 1
                        total_cells += 1
                        cell_references.append(
                            CellReference(
                                sheet_name="Balance_Sheet",
                                row=curr_bs_row,
                                col=y_idx + 1,
                                coordinate=coord,
                                is_hardcode=True,
                                source_node_id=leaf_node.source_node.node_id,
                                annotation_id=anno.id,
                            )
                        )
                    else:
                        ws_bs.write_number(curr_bs_row, y_idx + 1, 0.0, fmt_hardcode)
                        source_cells += 1
                        total_cells += 1
                        cell_references.append(
                            CellReference(
                                sheet_name="Balance_Sheet",
                                row=curr_bs_row,
                                col=y_idx + 1,
                                coordinate=coord,
                                is_hardcode=True,
                            )
                        )

            curr_bs_row += 1

        # -------------------------------------------------------------
        # TAB 1: EXECUTIVE SUMMARY (KPIs & Cross-Sheet Links)
        # -------------------------------------------------------------
        curr_s_row = 3
        # Summary items: (label, target_sheet, target_item, is_margin_calc, is_section)
        summary_kpis: list[tuple[str, str, str, bool, bool]] = [
            ("Financial Performance", "", "", False, True),
            ("Revenue", "Income_Statement", "Revenue", False, False),
            ("Gross Profit", "Income_Statement", "Gross Profit", False, False),
            ("Gross Margin %", "calc", "Gross Profit:Revenue", True, False),
            (
                "Operating Income (EBIT)",
                "Income_Statement",
                "Operating Income",
                False,
                False,
            ),
            ("Operating Margin %", "calc", "Operating Income:Revenue", True, False),
            ("Net Income", "Income_Statement", "Net Income", False, False),
            ("Net Margin %", "calc", "Net Income:Revenue", True, False),
            ("Cash & Valuation", "", "", False, True),
            ("Adjusted EBITDA", "EBITDA_Bridge", "Adjusted EBITDA", False, False),
            ("Free Cash Flow", "Cash_Flow", "Free Cash Flow", False, False),
            ("Net Debt", "Balance_Sheet", "Net Debt", False, False),
        ]

        for (
            kpi_label,
            target_sheet,
            target_item,
            is_margin_calc,
            is_section,
        ) in summary_kpis:
            if is_section:
                ws_summary.write(curr_s_row, 0, kpi_label, fmt_section)
                for y_idx in range(len(sorted_years)):
                    ws_summary.write_blank(curr_s_row, y_idx + 1, None, fmt_section)
                curr_s_row += 1
                continue

            ws_summary.write(curr_s_row, 0, kpi_label, fmt_label)

            for y_idx in range(len(sorted_years)):
                coord = _to_cell_coord(curr_s_row, y_idx + 1)
                col_letter = _col_to_letter(y_idx + 1)

                if is_margin_calc and ":" in target_item:
                    num_target, den_target = target_item.split(":", 1)
                    num_c = cell_coord_map.get(
                        ("Income_Statement", num_target, y_idx), f"{col_letter}6"
                    )
                    den_c = cell_coord_map.get(
                        ("Income_Statement", den_target, y_idx), f"{col_letter}4"
                    )
                    formula = f"='Income_Statement'!{num_c}/'Income_Statement'!{den_c}"
                    ws_summary.write_formula(
                        curr_s_row, y_idx + 1, formula, fmt_percent_link
                    )
                else:
                    target_coord = cell_coord_map.get(
                        (target_sheet, target_item, y_idx), f"{col_letter}4"
                    )
                    formula = f"='{target_sheet}'!{target_coord}"
                    ws_summary.write_formula(curr_s_row, y_idx + 1, formula, fmt_link)

                formula_cells += 1
                total_cells += 1
                cell_references.append(
                    CellReference(
                        sheet_name="Executive_Summary",
                        row=curr_s_row,
                        col=y_idx + 1,
                        coordinate=coord,
                        formula=formula,
                        is_formula=True,
                    )
                )

            curr_s_row += 1

        # -------------------------------------------------------------
        # TAB 6: AUDIT TRAIL
        # -------------------------------------------------------------
        ws_audit.write(0, 0, f"{company_name} — PDF Provenance Audit Trail", fmt_title)
        audit_headers = [
            "Sheet",
            "Cell",
            "Line Item",
            "Extracted Value",
            "Source Document",
            "Page",
            "Bounding Box (0-1000)",
            "Job ID",
        ]
        for col_idx, header_text in enumerate(audit_headers):
            ws_audit.write(2, col_idx, header_text, fmt_audit_header)

        for a_idx, anno in enumerate(provenance_records):
            row_idx = 3 + a_idx
            ws_audit.write(row_idx, 0, anno.sheet_name, fmt_audit_cell)
            ws_audit.write(row_idx, 1, anno.cell_coord, fmt_audit_cell)
            ws_audit.write(row_idx, 2, anno.body.label, fmt_audit_cell)
            ws_audit.write(row_idx, 3, anno.body.value, fmt_audit_cell)
            ws_audit.write(row_idx, 4, anno.target.source, fmt_audit_cell)
            page_num = anno.target.selector.page if anno.target.selector else 1
            ws_audit.write(row_idx, 5, page_num, fmt_audit_cell)
            bbox_str = (
                f"[{anno.target.selector.refinedBy.coordinates.x0:.1f}, {anno.target.selector.refinedBy.coordinates.y0:.1f}, {anno.target.selector.refinedBy.coordinates.x1:.1f}, {anno.target.selector.refinedBy.coordinates.y1:.1f}]"
                if anno.target.selector
                else "N/A"
            )
            ws_audit.write(row_idx, 6, bbox_str, fmt_audit_cell)
            ws_audit.write(row_idx, 7, anno.job_id, fmt_audit_cell)

        workbook.close()

        # Atomic replace (CONSTITUTION § 1.9)
        os.replace(tmp_path, dest_path)
        if not is_multi_year:
            try:
                import shutil

                shutil.copyfile(
                    dest_path, models_dir / f"{primary_job_id}_multi_statement.xlsx"
                )
            except OSError:
                pass
        logger.info(
            "Generated 6-tab multi-statement workbook at %s (%d total cells)",
            dest_path,
            total_cells,
        )

        return WorkbookGenerationResult(
            job_id=primary_job_id,
            file_path=str(dest_path),
            target_metric="Full Model",
            sheet_names=sheet_names,
            total_cells_generated=total_cells,
            formula_cells_count=formula_cells,
            source_cells_count=source_cells,
            cell_references=cell_references,
            provenance_records=provenance_records,
            warnings=warnings,
            is_success=True,
            error_detail=None,
        )
    except Exception as err:  # noqa: BLE001
        logger.error("Failed to generate multi-statement workbook: %s", err)
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        return WorkbookGenerationResult(
            job_id=primary_job_id,
            file_path="",
            target_metric="Full Model",
            sheet_names=[],
            total_cells_generated=0,
            is_success=False,
            error_detail=str(err),
        )
