"""
PDF Report Renderer for the Audit Report Stage (Feature 8 Step 2).

Renders a structured, human-readable compliance PDF document using ReportLab.

Enforces:
- CONSTITUTION §1.1 (mypy --strict), §4.4 (local rendering only), §6.5 (zero external data egress).
- spec.md §2 (Layout & Sections), AC-1, AC-2, AC-4, AC-5, AC-7, AC-8, AC-10.
- EC-1, EC-2, EC-3, EC-4, EC-5, EC-7, EC-8.
"""

import html
import io
import logging
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.audit_report.models import CompiledAuditDataset

logger = logging.getLogger(__name__)


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas that computes the total page count and renders dynamic running headers
    and 'Page X of Y' footers across all pages (spec §2, AC-4, EC-5).
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int) -> None:
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#475569"))

        # Page dimensions for landscape letter (792 x 612)
        page_w, page_h = 792.0, 612.0
        margin = 36.0

        # Running Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(
                margin,
                page_h - 24.0,
                "Footnote — Compliance & Provenance Audit Report",
            )
            self.drawRightString(
                page_w - margin,
                page_h - 24.0,
                "Confidential / Model Governance",
            )
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(margin, page_h - 28.0, page_w - margin, page_h - 28.0)

        # Running Footer (all pages)
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(margin, 30.0, page_w - margin, 30.0)

        self.drawString(
            margin,
            18.0,
            "Deterministic Provenance Audit • Footnote Engine",
        )
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(page_w - margin, 18.0, page_text)

        self.restoreState()


def _sanitize(text: str | None) -> str:
    """Escape HTML characters to prevent XML parsing errors in ReportLab Paragraphs (EC-8)."""
    if text is None:
        return ""
    return html.escape(str(text))


def render_audit_report_pdf(dataset: CompiledAuditDataset) -> bytes:
    """
    Renders a CompiledAuditDataset into a structured compliance-grade PDF document in memory.

    Args:
        dataset: The unified compiled audit dataset.

    Returns:
        Raw PDF bytes conforming to PDF-1.4 specification.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=36.0,
        rightMargin=36.0,
        topMargin=40.0,
        bottomMargin=40.0,
    )

    styles = getSampleStyleSheet()

    # Custom typography styles
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#475569"),
        spaceAfter=12,
    )
    section_heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1E293B"),
        spaceBefore=14,
        spaceAfter=6,
    )
    table_cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#1E293B"),
    )
    table_cell_bold = ParagraphStyle(
        "TableCellBold",
        parent=table_cell_style,
        fontName="Helvetica-Bold",
    )
    table_header_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        textColor=colors.white,
    )
    callout_style = ParagraphStyle(
        "CalloutText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#0F766E"),
    )
    badge_style = ParagraphStyle(
        "BadgeText",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=9,
        textColor=colors.HexColor("#1E293B"),
    )

    elements: list[Any] = []

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Header Banner & Title
    # ──────────────────────────────────────────────────────────────────────────
    meta = dataset.metadata
    elements.append(Paragraph("COMPLIANCE & PROVENANCE AUDIT REPORT", title_style))
    elements.append(
        Paragraph(
            f"<b>Target Metric:</b> {_sanitize(meta.target_metric)} &nbsp;|&nbsp; "
            f"<b>Entity:</b> {_sanitize(meta.entity)} &nbsp;|&nbsp; "
            f"<b>Filing:</b> {_sanitize(meta.filing_filename)} &nbsp;|&nbsp; "
            f"<b>Generated:</b> {_sanitize(meta.generated_at)}",
            subtitle_style,
        )
    )
    elements.append(
        HRFlowable(
            width="100%",
            thickness=1.5,
            color=colors.HexColor("#2563EB"),
            spaceBefore=0,
            spaceAfter=10,
        )
    )

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Executive Summary & Model Metadata (spec §2)
    # ──────────────────────────────────────────────────────────────────────────
    elements.append(
        Paragraph("1. Executive Summary & Model Metadata", section_heading_style)
    )

    summary_data = [
        [
            Paragraph("<b>Job ID</b>", table_cell_style),
            Paragraph(_sanitize(meta.job_id), table_cell_style),
            Paragraph("<b>Target Metric</b>", table_cell_style),
            Paragraph(_sanitize(meta.target_metric), table_cell_style),
        ],
        [
            Paragraph("<b>Entity Identifier</b>", table_cell_style),
            Paragraph(_sanitize(meta.entity), table_cell_style),
            Paragraph("<b>Filing Filename</b>", table_cell_style),
            Paragraph(_sanitize(meta.filing_filename), table_cell_style),
        ],
        [
            Paragraph("<b>Filing Year</b>", table_cell_style),
            Paragraph(
                str(meta.filing_year) if meta.filing_year else "N/A", table_cell_style
            ),
            Paragraph("<b>Generated Timestamp</b>", table_cell_style),
            Paragraph(_sanitize(meta.generated_at), table_cell_style),
        ],
        [
            Paragraph("<b>Total Model Cells</b>", table_cell_style),
            Paragraph(str(meta.total_cells), table_cell_bold),
            Paragraph("<b>Automated / Verified / Flagged</b>", table_cell_style),
            Paragraph(
                f"{meta.automated_count} auto / {meta.verified_count} verified / {meta.flagged_count} flagged",
                table_cell_style,
            ),
        ],
        [
            Paragraph("<b>Manual Overrides</b>", table_cell_style),
            Paragraph(
                (
                    f"<b>{meta.override_count}</b> override(s) recorded"
                    if meta.override_count > 0
                    else "<b>0</b> (100% automated extraction)"
                ),
                table_cell_style,
            ),
            Paragraph("<b>Verification Integrity</b>", table_cell_style),
            Paragraph(
                "100% Provenance Bound (W3C Web Annotation standard)",
                table_cell_style,
            ),
        ],
    ]

    summary_table = Table(
        summary_data,
        colWidths=[120.0, 240.0, 150.0, 210.0],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 1.0, colors.HexColor("#CBD5E1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        ),
    )
    elements.append(summary_table)
    elements.append(Spacer(1, 10))

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Model & Reconciliation Summary (spec §2)
    # ──────────────────────────────────────────────────────────────────────────
    elements.append(
        Paragraph("2. Financial Model & Reconciliation Summary", section_heading_style)
    )

    if dataset.reconciliation_summary:
        recon_headers = [
            Paragraph("Worksheet", table_header_style),
            Paragraph("Cell", table_header_style),
            Paragraph("Line Item Label", table_header_style),
            Paragraph("Taxonomy Label", table_header_style),
            Paragraph("Excel Formula / Calculation", table_header_style),
            Paragraph("Computed Value", table_header_style),
        ]
        recon_rows = [recon_headers]

        for recon_item in dataset.reconciliation_summary:
            formula_display = (
                _sanitize(recon_item.formula_expression)
                if recon_item.formula_expression
                else "[Direct Input]"
            )
            recon_rows.append(
                [
                    Paragraph(_sanitize(recon_item.sheet_name), table_cell_style),
                    Paragraph(_sanitize(recon_item.cell_coord), table_cell_bold),
                    Paragraph(_sanitize(recon_item.label), table_cell_style),
                    Paragraph(
                        _sanitize(recon_item.normalized_label or "—"), table_cell_style
                    ),
                    Paragraph(formula_display, table_cell_style),
                    Paragraph(
                        f"<b>{_sanitize(recon_item.computed_value)}</b>",
                        table_cell_style,
                    ),
                ]
            )

        recon_table = Table(
            recon_rows,
            colWidths=[80.0, 40.0, 180.0, 150.0, 180.0, 90.0],
            repeatRows=1,
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                    ("BOX", (0, 0), (-1, -1), 1.0, colors.HexColor("#CBD5E1")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#F8FAFC")],
                    ),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]
            ),
        )
        elements.append(recon_table)
    else:
        elements.append(
            Paragraph(
                "<i>No reconciliation summary items recorded.</i>", table_cell_style
            )
        )
    elements.append(Spacer(1, 10))

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Comprehensive Provenance Matrix (spec §2, AC-2, EC-3, EC-4, EC-5)
    # ──────────────────────────────────────────────────────────────────────────
    elements.append(
        Paragraph("3. Comprehensive Cell Provenance Matrix", section_heading_style)
    )

    prov_headers = [
        Paragraph("Cell Ref", table_header_style),
        Paragraph("Line Item Label", table_header_style),
        Paragraph("Normalized Label", table_header_style),
        Paragraph("Value", table_header_style),
        Paragraph(
            "Contributing Source Components (File, Page, Normalized BBox, Status)",
            table_header_style,
        ),
    ]
    prov_rows = [prov_headers]

    for prov_item in dataset.provenance_matrix:
        # Build contributing components description
        comp_paragraphs: list[str] = []
        if prov_item.components:
            for c in prov_item.components:
                bbox_str = f"[{c.bbox.get('x0', 0):.0f}, {c.bbox.get('y0', 0):.0f}, {c.bbox.get('x1', 0):.0f}, {c.bbox.get('y1', 0):.0f}]"
                status_color = (
                    "#15803D"
                    if c.review_status == "locked"
                    else ("#B91C1C" if c.review_status == "flagged" else "#475569")
                )
                comp_paragraphs.append(
                    f"&bull; <b>{_sanitize(c.source_file)}</b> (p. {c.page}, bbox: {bbox_str}) &mdash; "
                    f"val: <i>{_sanitize(c.value)}</i> &mdash; "
                    f"<font color='{status_color}'><b>[{_sanitize(c.review_status)}]</b></font>"
                )
        else:
            comp_paragraphs.append("&bull; <i>Direct calculation or manual entry</i>")

        comp_cell_content = "<br/>".join(comp_paragraphs)

        prov_rows.append(
            [
                Paragraph(
                    f"<b>{_sanitize(prov_item.sheet_name)}!{_sanitize(prov_item.cell_coord)}</b>",
                    table_cell_style,
                ),
                Paragraph(_sanitize(prov_item.label), table_cell_style),
                Paragraph(
                    _sanitize(prov_item.normalized_label or "—"), table_cell_style
                ),
                Paragraph(_sanitize(prov_item.computed_value), table_cell_bold),
                Paragraph(comp_cell_content, table_cell_style),
            ]
        )

    prov_table = Table(
        prov_rows,
        colWidths=[100.0, 140.0, 120.0, 80.0, 280.0],
        repeatRows=1,
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
                ("BOX", (0, 0), (-1, -1), 1.0, colors.HexColor("#CBD5E1")),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#F8FAFC")],
                ),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        ),
    )
    elements.append(prov_table)
    elements.append(Spacer(1, 10))

    # ──────────────────────────────────────────────────────────────────────────
    # 5. Manual Override & Exception Ledger (spec §3, AC-3, EC-1, EC-2)
    # ──────────────────────────────────────────────────────────────────────────
    elements.append(
        Paragraph("4. Manual Override & Exception Ledger", section_heading_style)
    )

    if dataset.has_manual_overrides and dataset.manual_overrides:
        override_summary_text = (
            f"<b>Manual Review Ledger:</b> A total of <b>{len(dataset.manual_overrides)}</b> human intervention(s) "
            "were applied during review and verified prior to model generation."
        )
        elements.append(
            Table(
                [[Paragraph(override_summary_text, table_cell_style)]],
                colWidths=[720.0],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF2F2")),
                        ("BOX", (0, 0), (-1, -1), 1.0, colors.HexColor("#FCA5A5")),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ]
                ),
            )
        )
        elements.append(Spacer(1, 4))

        override_headers = [
            Paragraph("Item ID / Ref", table_header_style),
            Paragraph("Category / Type", table_header_style),
            Paragraph("Source & Page", table_header_style),
            Paragraph("Original Value & Label", table_header_style),
            Paragraph("Confirmed Value & Label", table_header_style),
            Paragraph("Reason / Flags / Status", table_header_style),
        ]
        override_rows = [override_headers]

        for ov in dataset.manual_overrides:
            orig_desc = (
                f"val: <i>{_sanitize(ov.original_value or '[none]')}</i><br/>"
                f"lbl: {_sanitize(ov.original_label or '[none]')}"
            )
            final_desc = (
                f"val: <b>{_sanitize(ov.final_value)}</b><br/>"
                f"lbl: <b>{_sanitize(ov.final_label)}</b>"
            )
            type_label = ov.override_type.replace("_", " ").upper()
            flag_str = (
                f"<br/>flags: <i>{', '.join(_sanitize(f) for f in ov.flags)}</i>"
                if ov.flags
                else ""
            )
            err_desc = (
                _sanitize(ov.error_detail)
                if ov.error_detail
                else "Human edit during review"
            )

            override_rows.append(
                [
                    Paragraph(f"<b>{_sanitize(ov.item_id)}</b>", table_cell_style),
                    Paragraph(f"<b>[{_sanitize(type_label)}]</b>", badge_style),
                    Paragraph(
                        f"{_sanitize(ov.source_file)}<br/>(p. {ov.page})",
                        table_cell_style,
                    ),
                    Paragraph(orig_desc, table_cell_style),
                    Paragraph(final_desc, table_cell_style),
                    Paragraph(
                        f"<b>[{_sanitize(ov.review_status)}]</b><br/>{err_desc}{flag_str}",
                        table_cell_style,
                    ),
                ]
            )

        override_table = Table(
            override_rows,
            colWidths=[90.0, 110.0, 110.0, 130.0, 130.0, 150.0],
            repeatRows=1,
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#B91C1C")),
                    ("BOX", (0, 0), (-1, -1), 1.0, colors.HexColor("#CBD5E1")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#FEF2F2")],
                    ),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            ),
        )
        elements.append(override_table)
    else:
        # Explicit zero overrides statement (spec §3, AC-3, EC-1)
        clean_box_data = [
            [
                Paragraph(
                    "<b>Governance Verification:</b> Zero manual overrides — 100% of values are derived "
                    "from layout extraction and taxonomy-confirmed inputs.",
                    callout_style,
                )
            ]
        ]
        clean_table = Table(
            clean_box_data,
            colWidths=[720.0],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F0FDF4")),
                    ("BOX", (0, 0), (-1, -1), 1.0, colors.HexColor("#86EFAC")),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]
            ),
        )
        elements.append(clean_table)
    elements.append(Spacer(1, 10))

    # ──────────────────────────────────────────────────────────────────────────
    # 6. Classifier Governance Proof (spec §2, AC-7)
    # ──────────────────────────────────────────────────────────────────────────
    gov = dataset.classifier_governance
    elements.append(
        Paragraph("5. AI Classifier Governance Proof", section_heading_style)
    )

    gov_box_text = (
        f"<b>Audit Finding:</b> The Groq LLM classifier executed <b>{gov.total_calls}</b> taxonomic "
        f"classification call(s) (Matched: {gov.matched_count}, Unrecognized: {gov.pending_count}, Errors: {gov.error_count}). "
        "<b>Zero numeric values, formula operands, or calculations were produced or accepted from the classifier</b> "
        "(CONSTITUTION §1.2, §6.1, §6.2)."
    )
    gov_table = Table(
        [[Paragraph(gov_box_text, callout_style)]],
        colWidths=[720.0],
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F0FDFA")),
                ("BOX", (0, 0), (-1, -1), 1.0, colors.HexColor("#99F6E4")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        ),
    )
    elements.append(gov_table)

    if gov.entries:
        gov_rows = [
            [
                Paragraph("Index", table_header_style),
                Paragraph("Input Extracted Label", table_header_style),
                Paragraph("Structural Context", table_header_style),
                Paragraph("Classifier Output Label", table_header_style),
                Paragraph("Confidence", table_header_style),
                Paragraph("Taxonomy Status", table_header_style),
            ]
        ]
        # Show first 8 entries for audit verification
        for e in gov.entries[:8]:
            conf_str = f"{e.confidence:.2f}" if e.confidence is not None else "—"
            gov_rows.append(
                [
                    Paragraph(str(e.record_index), table_cell_style),
                    Paragraph(_sanitize(e.input_label), table_cell_style),
                    Paragraph(_sanitize(e.structural_context or "—"), table_cell_style),
                    Paragraph(_sanitize(e.output_label or "—"), table_cell_bold),
                    Paragraph(conf_str, table_cell_style),
                    Paragraph(f"<b>{_sanitize(e.taxonomy_status)}</b>", badge_style),
                ]
            )

        gov_entries_table = Table(
            gov_rows,
            colWidths=[40.0, 180.0, 160.0, 160.0, 70.0, 110.0],
            repeatRows=1,
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F766E")),
                    ("BOX", (0, 0), (-1, -1), 1.0, colors.HexColor("#CBD5E1")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#F8FAFC")],
                    ),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            ),
        )
        elements.append(Spacer(1, 4))
        elements.append(gov_entries_table)

    elements.append(Spacer(1, 10))

    # ──────────────────────────────────────────────────────────────────────────
    # 7. Cross-Year Definitional Consistency (Drift) (spec §2, AC-8, EC-7)
    # ──────────────────────────────────────────────────────────────────────────
    drift = dataset.drift_summary
    elements.append(
        KeepTogether(
            [
                Paragraph(
                    "6. Cross-Year Definitional Consistency & Drift",
                    section_heading_style,
                ),
                Table(
                    [
                        [
                            Paragraph(
                                f"<b>Drift Analysis:</b> {_sanitize(drift.summary_text)}",
                                table_cell_style,
                            )
                        ]
                    ],
                    colWidths=[720.0],
                    style=TableStyle(
                        [
                            (
                                "BACKGROUND",
                                (0, 0),
                                (-1, -1),
                                (
                                    colors.HexColor("#FEF3C7")
                                    if drift.has_discrepancy
                                    else colors.HexColor("#F8FAFC")
                                ),
                            ),
                            (
                                "BOX",
                                (0, 0),
                                (-1, -1),
                                1.0,
                                (
                                    colors.HexColor("#FCD34D")
                                    if drift.has_discrepancy
                                    else colors.HexColor("#CBD5E1")
                                ),
                            ),
                            ("TOPPADDING", (0, 0), (-1, -1), 6),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                            ("LEFTPADDING", (0, 0), (-1, -1), 10),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                        ]
                    ),
                ),
            ]
        )
    )

    # Build PDF using NumberedCanvas
    doc.build(elements, canvasmaker=NumberedCanvas)
    return buffer.getvalue()
