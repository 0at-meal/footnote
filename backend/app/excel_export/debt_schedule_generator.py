"""
Capital Structure & Debt Sizing Excel Generator (Workflow Pack 2 / Step 14).

Generates a deterministic 2-tab workbook:
- Debt_Tranches: Note 8 tranches, stated rates, spreads, maturity years, and principal amounts with dynamic sum formula.
- Lease_Waterfall: Note 12 / ASC 842 undiscounted lease commitments across future periods with dynamic sum formula.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import xlsxwriter

from app.excel_export.models import (
    BoundingBoxCoordinates,
    CellReference,
    W3CAnnotationRecord,
    W3CBody,
    W3CRefinedBy,
    W3CSelector,
    W3CTarget,
    WorkbookGenerationResult,
)
from app.excel_export.provenance import format_cell_comment, format_cell_hyperlink_url
from app.excel_export.utils import (
    IB_CURRENCY_FORMAT,
    to_cell_coord,
)
from app.footnote.models import DebtSchedule, LeaseSchedule

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"


def generate_capital_structure_workbook(
    debt_schedule: DebtSchedule,
    lease_schedule: LeaseSchedule,
    job_id: str,
    output_dir: Path | None = None,
    base_url: str = "http://localhost:8000",
) -> WorkbookGenerationResult:
    """
    Serializes DebtSchedule and LeaseSchedule into a clean, deterministic 2-tab Excel model.
    """
    target_dir = (output_dir or _DEFAULT_DATA_DIR) / "models"
    target_dir.mkdir(parents=True, exist_ok=True)

    dest_file = target_dir / f"{job_id}_model.xlsx"
    tmp_file = target_dir / f"{job_id}_model.xlsx.tmp"

    has_debt = bool(debt_schedule.tranches)
    has_leases = bool(lease_schedule.years)

    if not has_debt and not has_leases:
        return WorkbookGenerationResult(
            job_id=job_id,
            file_path=str(dest_file),
            target_metric="Capital Structure",
            sheet_names=[],
            total_cells_generated=0,
            formula_cells_count=0,
            source_cells_count=0,
            cell_references=[],
            provenance_records=[],
            warnings=["No Note 8 debt tranches or ASC 842 lease commitments found in filing."],
            is_success=False,
            error_detail="No Note 8 debt tranches or ASC 842 lease commitments found in filing.",
        )

    cell_refs: list[CellReference] = []
    provenance_records: list[W3CAnnotationRecord] = []
    warnings: list[str] = []
    sheet_names = ["Debt_Tranches", "Lease_Waterfall"]

    workbook: Any = None
    try:
        workbook = xlsxwriter.Workbook(str(tmp_file))

        # IB Styles (CONSTITUTION §2.5)
        fmt_title = workbook.add_format({
            "bold": True,
            "font_size": 12,
            "font_color": "#000000",
        })
        fmt_header = workbook.add_format({
            "bold": True,
            "bg_color": "#F2F2F2",
            "border": 1,
            "font_size": 10,
            "align": "left",
            "valign": "vcenter",
        })
        fmt_header_num = workbook.add_format({
            "bold": True,
            "bg_color": "#F2F2F2",
            "border": 1,
            "font_size": 10,
            "align": "right",
            "valign": "vcenter",
        })
        fmt_text = workbook.add_format({
            "font_size": 10,
            "border": 1,
            "align": "left",
        })
        fmt_center = workbook.add_format({
            "font_size": 10,
            "border": 1,
            "align": "center",
        })
        fmt_hardcode_num = workbook.add_format({
            "font_color": "#0000FF",  # Blue for hardcodes
            "font_size": 10,
            "num_format": IB_CURRENCY_FORMAT,
            "align": "right",
            "border": 1,
        })
        fmt_total_label = workbook.add_format({
            "bold": True,
            "font_size": 10,
            "top": 1,
            "bottom": 6,  # Double bottom border
            "align": "left",
        })
        fmt_total_formula = workbook.add_format({
            "bold": True,
            "font_color": "#000000",  # Black for formula totals
            "font_size": 10,
            "num_format": IB_CURRENCY_FORMAT,
            "top": 1,
            "bottom": 6,  # Double bottom border
            "align": "right",
        })

        # =====================================================================
        # Sheet 1: Debt_Tranches
        # =====================================================================
        ws_debt = workbook.add_worksheet("Debt_Tranches")
        ws_debt.set_column("A:A", 36)
        ws_debt.set_column("B:B", 16)
        ws_debt.set_column("C:C", 16)
        ws_debt.set_column("D:D", 18)
        ws_debt.set_column("E:E", 14)
        ws_debt.set_column("F:F", 22)

        ws_debt.write(0, 0, "Note 8: Debt Tranches & Credit Facilities Schedule", fmt_title)

        headers_debt = [
            ("Tranche / Facility Name", fmt_header),
            ("Seniority", fmt_header),
            ("Stated Rate", fmt_header),
            ("Benchmark / Spread", fmt_header),
            ("Maturity Year", fmt_header),
            ("Principal Amount ($M)", fmt_header_num),
        ]
        for col_idx, (hdr_text, style) in enumerate(headers_debt):
            ws_debt.write(2, col_idx, hdr_text, style)

        debt_start_row = 3
        curr_row = debt_start_row

        for tranche in debt_schedule.tranches:
            ws_debt.write(curr_row, 0, tranche.instrument_name, fmt_text)
            ws_debt.write(curr_row, 1, tranche.senior_subordinated, fmt_center)

            rate_display = (
                f"{tranche.interest_rate:.2f}%"
                if tranche.interest_rate is not None
                else (tranche.rate_text or "—")
            )
            ws_debt.write(curr_row, 2, rate_display, fmt_center)

            spread_display = "—"
            if tranche.is_floating:
                bm = tranche.benchmark or "SOFR"
                sp = f"+{tranche.spread:.2f}%" if tranche.spread is not None else ""
                spread_display = f"{bm} {sp}".strip()
            ws_debt.write(curr_row, 3, spread_display, fmt_center)

            mat_display = str(tranche.maturity_year) if tranche.maturity_year else "—"
            ws_debt.write(curr_row, 4, mat_display, fmt_center)

            principal_val = tranche.principal_amount if tranche.principal_amount is not None else 0.0
            val_coord = to_cell_coord(curr_row, 5)
            ws_debt.write_number(curr_row, 5, principal_val, fmt_hardcode_num)

            # Build W3C Provenance annotation for tranche principal
            bbox_dict = tranche.bbox or {}
            coords = BoundingBoxCoordinates(
                x0=float(bbox_dict.get("x0", 0.0)),
                y0=float(bbox_dict.get("y0", 0.0)),
                x1=float(bbox_dict.get("x1", 0.0)),
                y1=float(bbox_dict.get("y1", 0.0)),
            )
            selector = W3CSelector(
                page=tranche.page,
                value=f"xywh=percent:{int(coords.x0)},{int(coords.y0)},{int(coords.x1-coords.x0)},{int(coords.y1-coords.y0)}",
                refinedBy=W3CRefinedBy(coordinates=coords),
            )
            target = W3CTarget(source=f"{job_id}.pdf", selector=selector)
            body = W3CBody(
                value=str(principal_val),
                label=tranche.instrument_name,
                original_label=tranche.principal_text or tranche.instrument_name,
            )
            anno = W3CAnnotationRecord(
                id=f"urn:footnote:provenance:{job_id}:debt_{tranche.id}",
                job_id=job_id,
                sheet_name="Debt_Tranches",
                cell_coord=val_coord,
                node_id=tranche.id,
                is_formula=False,
                body=body,
                target=target,
            )
            provenance_records.append(anno)

            comment_text = format_cell_comment(anno)
            hyperlink_url = format_cell_hyperlink_url(
                job_id=job_id,
                sheet_name="Debt_Tranches",
                cell_coord=val_coord,
                base_url=base_url,
            )
            ws_debt.write_comment(curr_row, 5, comment_text, {"visible": False})
            ws_debt.write_url(
                curr_row,
                5,
                hyperlink_url,
                fmt_hardcode_num,
                string=None,
                tip=f"Source: Note 8 (p. {tranche.page})",
            )

            cell_refs.append(
                CellReference(
                    sheet_name="Debt_Tranches",
                    row=curr_row,
                    col=5,
                    coordinate=val_coord,
                    node_id=tranche.id,
                    formula=None,
                    is_formula=False,
                    is_hardcode=True,
                    source_node_id=None,
                    annotation_id=anno.id,
                )
            )
            curr_row += 1

        # Total Debt Row
        if curr_row > debt_start_row:
            ws_debt.write(curr_row, 0, "Total Debt Obligations", fmt_total_label)
            for c in range(1, 5):
                ws_debt.write(curr_row, c, "", fmt_total_label)

            total_formula = f"=SUM(F{debt_start_row + 1}:F{curr_row})"
            total_coord = to_cell_coord(curr_row, 5)
            ws_debt.write_formula(curr_row, 5, total_formula, fmt_total_formula)

            total_anno = W3CAnnotationRecord(
                id=f"urn:footnote:provenance:{job_id}:Debt_Tranches:{total_coord}",
                job_id=job_id,
                sheet_name="Debt_Tranches",
                cell_coord=total_coord,
                node_id="debt_total",
                is_formula=True,
                body=W3CBody(
                    value=total_formula,
                    label="Total Debt Obligations",
                    original_label="Total Debt Obligations",
                ),
                target=W3CTarget(source="model_derived", selector=None),
            )
            provenance_records.append(total_anno)

            cell_refs.append(
                CellReference(
                    sheet_name="Debt_Tranches",
                    row=curr_row,
                    col=5,
                    coordinate=total_coord,
                    node_id="debt_total",
                    formula=total_formula,
                    is_formula=True,
                    is_hardcode=False,
                    source_node_id=None,
                    annotation_id=total_anno.id,
                )
            )

        # =====================================================================
        # Sheet 2: Lease_Waterfall
        # =====================================================================
        ws_lease = workbook.add_worksheet("Lease_Waterfall")
        ws_lease.set_column("A:A", 28)
        ws_lease.set_column("B:B", 24)
        ws_lease.set_column("C:C", 24)
        ws_lease.set_column("D:D", 26)

        ws_lease.write(0, 0, "Note 12 / ASC 842 Undiscounted Lease Commitments", fmt_title)

        headers_lease = [
            ("Period / Fiscal Year", fmt_header),
            ("Operating Leases ($M)", fmt_header_num),
            ("Finance Leases ($M)", fmt_header_num),
            ("Total Lease Commitments ($M)", fmt_header_num),
        ]
        for col_idx, (hdr_text, style) in enumerate(headers_lease):
            ws_lease.write(2, col_idx, hdr_text, style)

        lease_start_row = 3
        curr_lease_row = lease_start_row

        for year in lease_schedule.years:
            ws_lease.write(curr_lease_row, 0, year.year_label, fmt_text)

            op_val = year.operating_amount if year.operating_amount is not None else 0.0
            fin_val = year.finance_amount if year.finance_amount is not None else 0.0

            ws_lease.write_number(curr_lease_row, 1, op_val, fmt_hardcode_num)
            ws_lease.write_number(curr_lease_row, 2, fin_val, fmt_hardcode_num)

            # Formula for row total: =B{r}+C{r}
            row_num = curr_lease_row + 1
            row_total_formula = f"=B{row_num}+C{row_num}"
            row_total_coord = to_cell_coord(curr_lease_row, 3)
            ws_lease.write_formula(curr_lease_row, 3, row_total_formula, fmt_hardcode_num)

            # Add provenance for total
            bbox_dict = year.bbox or {}
            coords = BoundingBoxCoordinates(
                x0=float(bbox_dict.get("x0", 0.0)),
                y0=float(bbox_dict.get("y0", 0.0)),
                x1=float(bbox_dict.get("x1", 0.0)),
                y1=float(bbox_dict.get("y1", 0.0)),
            )
            selector = W3CSelector(
                page=year.page,
                value=f"xywh=percent:{int(coords.x0)},{int(coords.y0)},{int(coords.x1-coords.x0)},{int(coords.y1-coords.y0)}",
                refinedBy=W3CRefinedBy(coordinates=coords),
            )
            target = W3CTarget(source=f"{job_id}.pdf", selector=selector)
            body = W3CBody(
                value=str(year.total_amount or (op_val + fin_val)),
                label=f"Lease Commitment {year.year_label}",
                original_label=f"Commitment {year.year_label}",
            )
            anno = W3CAnnotationRecord(
                id=f"urn:footnote:provenance:{job_id}:lease_{year.year_label}",
                job_id=job_id,
                sheet_name="Lease_Waterfall",
                cell_coord=row_total_coord,
                node_id=f"lease_{year.year_label}",
                is_formula=True,
                body=body,
                target=target,
            )
            provenance_records.append(anno)

            cell_refs.append(
                CellReference(
                    sheet_name="Lease_Waterfall",
                    row=curr_lease_row,
                    col=3,
                    coordinate=row_total_coord,
                    node_id=f"lease_{year.year_label}",
                    formula=row_total_formula,
                    is_formula=True,
                    is_hardcode=False,
                    source_node_id=None,
                    annotation_id=anno.id,
                )
            )
            curr_lease_row += 1

        # Total Leases Row
        if curr_lease_row > lease_start_row:
            ws_lease.write(curr_lease_row, 0, "Total Undiscounted Commitments", fmt_total_label)

            op_total_formula = f"=SUM(B{lease_start_row + 1}:B{curr_lease_row})"
            fin_total_formula = f"=SUM(C{lease_start_row + 1}:C{curr_lease_row})"
            grand_total_formula = f"=SUM(D{lease_start_row + 1}:D{curr_lease_row})"

            ws_lease.write_formula(curr_lease_row, 1, op_total_formula, fmt_total_formula)
            ws_lease.write_formula(curr_lease_row, 2, fin_total_formula, fmt_total_formula)
            ws_lease.write_formula(curr_lease_row, 3, grand_total_formula, fmt_total_formula)

            lease_total_coord = to_cell_coord(curr_lease_row, 3)
            lease_total_anno = W3CAnnotationRecord(
                id=f"urn:footnote:provenance:{job_id}:Lease_Waterfall:{lease_total_coord}",
                job_id=job_id,
                sheet_name="Lease_Waterfall",
                cell_coord=lease_total_coord,
                node_id="lease_total",
                is_formula=True,
                body=W3CBody(
                    value=grand_total_formula,
                    label="Total Undiscounted Lease Commitments",
                    original_label="Total Lease Commitments",
                ),
                target=W3CTarget(source="model_derived", selector=None),
            )
            provenance_records.append(lease_total_anno)

            cell_refs.append(
                CellReference(
                    sheet_name="Lease_Waterfall",
                    row=curr_lease_row,
                    col=3,
                    coordinate=lease_total_coord,
                    node_id="lease_total",
                    formula=grand_total_formula,
                    is_formula=True,
                    is_hardcode=False,
                    source_node_id=None,
                    annotation_id=lease_total_anno.id,
                )
            )

        workbook.close()
        workbook = None

        # Atomic rename (CONSTITUTION §1.9)
        os.replace(tmp_file, dest_file)

        formula_count = sum(1 for c in cell_refs if c.is_formula)
        source_count = sum(1 for c in cell_refs if not c.is_formula)

        return WorkbookGenerationResult(
            job_id=job_id,
            file_path=str(dest_file),
            target_metric="Capital Structure",
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
        logger.error("Failed to generate capital structure workbook for job %s: %s", job_id, err)
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
            target_metric="Capital Structure",
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
