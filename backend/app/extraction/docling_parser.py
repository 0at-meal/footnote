"""
Docling structural PDF parser for Feature 2, Step 1.

Scope:
    Runs Docling's layout parser on a local PDF file and extracts raw table cells
    with hierarchical header labels, 1-indexed page numbers, and Docling bounding boxes.

Footnote Handling (Spec EC-3):
    Cells containing footnote reference markers (e.g. (1), *, [a]) are extracted
    with their verbatim text/markers and flagged for human review via the confidence
    engine (confidence.py). Extraction of out-of-table footnote paragraphs and inter-record
    linking is deferred to downstream graph layers (Phase 3/4) to strictly maintain
    the frozen 5-field ExtractedRecord schema (CONSTITUTION §2.3, Spec AC-3).

Isolation (CONSTITUTION §3.8, §3.2):
    This module must NEVER import from classification/, formula_engine/, excel_export/,
    or audit_report/.
"""

import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

os.environ["TORCHDYNAMO_DISABLE"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

if TYPE_CHECKING:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
else:
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError:  # pragma: no cover

        class _FallbackInputFormat:
            PDF = "pdf"

        InputFormat = _FallbackInputFormat

        class _FallbackPdfPipelineOptions:
            do_ocr: bool = False
            generate_page_images: bool = False
            generate_picture_images: bool = False
            generate_table_images: bool = False

        PdfPipelineOptions = _FallbackPdfPipelineOptions

        class _FallbackPdfFormatOption:
            def __init__(self, pipeline_options: Any = None) -> None:
                self.pipeline_options = pipeline_options

        PdfFormatOption = _FallbackPdfFormatOption

        class _FallbackDocumentConverter:
            def __init__(self, format_options: Any = None) -> None:
                self.format_options = format_options

            def convert(self, path: str) -> Any:
                raise DoclingParseError("Docling library is not installed.")

        DocumentConverter = _FallbackDocumentConverter


from app.extraction.models import DoclingBbox, DoclingItem

logger = logging.getLogger(__name__)

# SEC boilerplate patterns (case-insensitive)
_SEC_BOILERPLATE_REGEX = re.compile(
    r"^(item\s+\d+[a-z]?\.?|part\s+[ivx]+|table\s+of\s+contents|management'?s?\s+discussion"
    r"|index\s+to\s+financial\s+statements|see\s+accompanying\s+notes|notes\s+to\s+consolidated\s+financial\s+statements)"
    r".*$",
    re.IGNORECASE,
)

# Currency and unit qualifier declarations (case-insensitive)
_UNIT_QUALIFIER_REGEX = re.compile(
    r"^(\(?\s*in\s+(thousands|millions|billions)(\s*,\s*except.*)?\)?|\(?\s*unaudited\s*\)?|\(?\s*audited\s*\)?|\(?\s*dollars\s+in\s+(thousands|millions)\s*\)?|\(?\s*in\s+usd\s*\)?|\(?\s*amounts\s+in\s+(thousands|millions)\s*\)?|\(?\s*\$\s*in\s+(thousands|millions)\s*\)?)$",
    re.IGNORECASE,
)

# Recognized non-numeric financial placeholders (e.g. dash or N/A)
_FINANCIAL_PLACEHOLDERS = {"—", "-", "–", "--", "n/a", "na", "none", "*", "•"}


def _is_noise_cell(cell_text: str, row_idx: int, col_idx: int) -> bool:
    """
    Identifies non-data noise cells that should be suppressed from extraction.

    Filters:
    1. SEC document boilerplate (e.g. 'Item 7.', 'PART I', 'Table of Contents').
    2. Currency and unit qualifier declarations (e.g. 'in millions', '(unaudited)').
    3. Cells containing zero numeric digits that are not valid financial placeholders.
    """
    cleaned = cell_text.strip()
    if not cleaned:
        return True

    # 1. SEC boilerplate
    if _SEC_BOILERPLATE_REGEX.search(cleaned):
        return True

    # 2. Currency and unit qualifier declarations
    if _UNIT_QUALIFIER_REGEX.search(cleaned):
        return True

    # 3. Non-digit cells that are not financial placeholders
    has_digit = bool(re.search(r"\d", cleaned))
    return not has_digit and cleaned.lower() not in _FINANCIAL_PLACEHOLDERS


def _extract_table_title(table: Any, table_idx: int, table_cells: list[Any]) -> str:
    """
    Extract the enclosing table or section title from a Docling table structure.
    """
    # Check table caption
    try:
        caption = getattr(table, "caption", None)
        if caption:
            if isinstance(caption, str) and caption.strip():
                return caption.strip()
            caption_text = getattr(caption, "text", None)
            if caption_text and isinstance(caption_text, str) and caption_text.strip():
                return caption_text.strip()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed reading table caption: %s", exc)

    # Check label or name
    try:
        label = getattr(table, "label", None)
        if (
            label
            and isinstance(label, str)
            and label.strip()
            and label.lower() not in ("table", "data_table")
        ):
            return label.strip()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed reading table label: %s", exc)

    # Check for title in row 0 cells or header cells
    for cell in table_cells:
        try:
            row_idx = getattr(cell, "start_row_offset_idx", 0)
            if row_idx == 0:
                text = (getattr(cell, "text", "") or "").strip()
                if text and len(text) > 3:
                    lower = text.lower()
                    if any(
                        kw in lower
                        for kw in [
                            "reconciliation",
                            "non-gaap",
                            "adjusted ebitda",
                            "ebitda",
                            "balance sheet",
                            "income statement",
                            "operations",
                            "cash flow",
                            "segment",
                            "schedule",
                        ]
                    ):
                        return text
        except Exception as exc:  # noqa: BLE001
            logger.debug("Skipping row 0 cell for title: %s", exc)
            continue

    # Check first row header or row section header
    for cell in table_cells:
        try:
            if getattr(cell, "row_section_header", False) or getattr(
                cell, "column_header", False
            ):
                text = (getattr(cell, "text", "") or "").strip()
                lower = text.lower()
                if any(
                    kw in lower
                    for kw in ["reconciliation", "non-gaap", "adjusted ebitda"]
                ):
                    return text
        except Exception as exc:  # noqa: BLE001
            logger.debug("Skipping header cell for title: %s", exc)
            continue

    return f"Table {table_idx + 1}"


def _is_reconciliation_table(
    table_title: str,
    target_metric: str = "",
    sample_text: str = "",
) -> bool:
    """
    Deterministically determines if a table is a reconciliation candidate table.

    Returns True if table_title or sample_text contains target_metric (case-insensitive, when non-empty)
    OR any of: non-gaap, reconciliation, adjusted, non gaap, bridge.
    """
    combined = f"{table_title} {sample_text}".lower().strip()
    if not combined:
        return False
    if target_metric and target_metric.strip().lower() in combined:
        return True
    reconciliation_keywords = (
        "non-gaap",
        "reconciliation",
        "adjusted",
        "non gaap",
        "bridge",
    )
    return any(kw in combined for kw in reconciliation_keywords)


def is_table_relevant_for_pack(
    table_title: str,
    workflow_pack: str = "non_gaap_bridge",
    target_metric: str = "",
    sample_text: str = "",
) -> bool:
    """
    Deterministically determines if a table is relevant for the selected workflow pack (Step 7).
    """
    combined = f"{table_title} {sample_text}".lower().strip()
    if not combined:
        return False

    if workflow_pack == "capital_structure":
        debt_keywords = (
            "debt",
            "credit facility",
            "credit facilities",
            "borrowings",
            "notes payable",
            "senior notes",
            "term loan",
            "revolving credit",
            "maturities",
            "leases",
            "lease obligations",
            "capital structure",
            "interest expense",
        )
        return any(kw in combined for kw in debt_keywords)

    if workflow_pack == "cash_conversion":
        cf_keywords = (
            "cash flow",
            "cash flows",
            "operating activities",
            "working capital",
            "capital expenditures",
            "capex",
            "free cash flow",
            "cash conversion",
        )
        return any(kw in combined for kw in cf_keywords)

    return _is_reconciliation_table(table_title, target_metric, sample_text)


class DoclingParseError(Exception):
    """Raised when an unrecoverable structural parse error occurs during extraction."""


def parse_pdf(
    pdf_path: Path,
    source_file: str,
    target_metric: str = "",
    workflow_pack: str = "non_gaap_bridge",
) -> list[DoclingItem]:
    """
    Parse a local PDF filing using Docling and extract raw table cell items.

    Args:
        pdf_path: Absolute or relative Path to the stored PDF file on disk.
        source_file: Original filename string stored in the job record (UTF-8, EC-8).
        target_metric: Optional target financial metric name to match in table titles.
        workflow_pack: Selected workflow pack for bounded extraction (Step 7).

    Returns:
        List of DoclingItem objects ordered deterministically by page, row, col (NFR1).

    Raises:
        DoclingParseError: If the file cannot be parsed or table structures are invalid.
        FileNotFoundError: If pdf_path does not exist on disk.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found at path: {pdf_path}")

    try:
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False
        pipeline_options.generate_page_images = False
        pipeline_options.generate_picture_images = False
        pipeline_options.generate_table_images = False
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
        result = converter.convert(str(pdf_path))
        doc = result.document
    except Exception as err:  # noqa: BLE001
        logger.warning(
            "Docling unavailable or failed for %s (%s). Using native PyMuPDF fallback.",
            pdf_path,
            err,
            exc_info=True,
        )
        return _parse_pdf_with_pymupdf(
            pdf_path,
            source_file,
            target_metric,
            workflow_pack=workflow_pack,
        )

    items: list[DoclingItem] = []

    try:
        for table_idx, table in enumerate(doc.tables):
            table_data = getattr(table, "data", None)
            if table_data is None:
                continue

            table_cells: list[Any] = getattr(table_data, "table_cells", [])

            if not table_cells:
                continue

            table_title = _extract_table_title(table, table_idx, table_cells)
            sample_parts: list[str] = []
            for c in table_cells[:16]:
                try:
                    txt = (getattr(c, "text", "") or "").strip()
                    if txt:
                        sample_parts.append(txt)
                except Exception:  # noqa: BLE001
                    continue
            sample_text = " ".join(sample_parts)
            is_reconciliation = is_table_relevant_for_pack(
                table_title, workflow_pack, target_metric, sample_text=sample_text
            )

            # Identify header text by column and row indices
            col_headers: dict[int, list[str]] = {}
            row_headers: dict[int, list[str]] = {}

            for cell in table_cells:
                try:
                    cell_text = (cell.text or "").strip()
                    if not cell_text:
                        continue

                    col_idx = getattr(cell, "start_col_offset_idx", 0)
                    row_idx = getattr(cell, "start_row_offset_idx", 0)
                    has_digit = bool(re.search(r"\d", cell_text))

                    is_col_header = getattr(cell, "column_header", False)
                    is_row_header = (
                        getattr(cell, "row_header", False)
                        or getattr(cell, "row_section_header", False)
                        or (col_idx == 0 and not has_digit)
                    )

                    if is_col_header:
                        col_headers.setdefault(col_idx, []).append(cell_text)
                    if is_row_header:
                        row_headers.setdefault(row_idx, []).append(cell_text)
                except Exception as header_err:  # noqa: BLE001
                    logger.warning(
                        "Skipping malformed cell during header scan in table %d of %s: %s",
                        table_idx,
                        source_file,
                        header_err,
                    )
                    continue

            # Process data cells
            for cell in table_cells:
                try:
                    cell_text = (cell.text or "").strip()
                    if not cell_text:
                        continue

                    col_idx = getattr(cell, "start_col_offset_idx", 0)
                    row_idx = getattr(cell, "start_row_offset_idx", 0)
                    has_digit = bool(re.search(r"\d", cell_text))

                    is_header = (
                        getattr(cell, "column_header", False)
                        or getattr(cell, "row_header", False)
                        or getattr(cell, "row_section_header", False)
                        or (col_idx == 0 and not has_digit)
                    )

                    # Header cells contribute to structural labels for data cells;
                    # they are not emitted as separate data values.
                    if is_header:
                        continue

                    row_idx = getattr(cell, "start_row_offset_idx", 0)
                    col_idx = getattr(cell, "start_col_offset_idx", 0)

                    # Pre-filter noise cells (Ticket 1.1)
                    if _is_noise_cell(cell_text, row_idx, col_idx):
                        continue

                    # Assemble structural label path
                    label_parts: list[str] = []

                    # Add row section/headers for this row
                    if row_idx in row_headers and not getattr(
                        cell, "row_header", False
                    ):
                        label_parts.extend(row_headers[row_idx])

                    # Add column headers for this column
                    if col_idx in col_headers and not getattr(
                        cell, "column_header", False
                    ):
                        label_parts.extend(col_headers[col_idx])

                    label = " / ".join(label_parts) if label_parts else cell_text

                    # Extract page number and bbox from provenance and cell attributes
                    cell_prov = getattr(cell, "prov", [])
                    table_prov = getattr(table, "prov", [])

                    page_no = 1
                    if cell_prov:
                        page_no = int(getattr(cell_prov[0], "page_no", 1))
                    elif table_prov:
                        page_no = int(getattr(table_prov[0], "page_no", 1))

                    raw_bbox = getattr(cell, "bbox", None)
                    if raw_bbox is None and cell_prov:
                        raw_bbox = getattr(cell_prov[0], "bbox", None)
                    if raw_bbox is None and table_prov:
                        raw_bbox = getattr(table_prov[0], "bbox", None)

                    bbox_obj = DoclingBbox(x0=0.0, y0=0.0, x1=0.0, y1=0.0)
                    if raw_bbox is not None:
                        # Extract l, t, r, b or x0, y0, x1, y1
                        x0 = float(getattr(raw_bbox, "l", getattr(raw_bbox, "x0", 0.0)))
                        y0 = float(getattr(raw_bbox, "t", getattr(raw_bbox, "y0", 0.0)))
                        x1 = float(getattr(raw_bbox, "r", getattr(raw_bbox, "x1", 0.0)))
                        y1 = float(getattr(raw_bbox, "b", getattr(raw_bbox, "y1", 0.0)))
                        bbox_obj = DoclingBbox(x0=x0, y0=y0, x1=x1, y1=y1)

                    _DEBT_TITLE_REGEX = re.compile(
                        r"(note\s+(?:8|\d+)[.:\s-]*)?(debt|credit\s+facilities|financing\s+arrangements|long-term\s+debt|borrowings|senior\s+notes|notes\s+payable|debt\s+obligations)",
                        re.IGNORECASE,
                    )
                    is_debt_footnote = bool(_DEBT_TITLE_REGEX.search(table_title))
                    footnote_type = "debt" if is_debt_footnote else None

                    item = DoclingItem(
                        value=cell_text,
                        label=label,
                        page=page_no,
                        bbox=bbox_obj,
                        source_file=source_file,
                        table_name=table_title,
                        is_reconciliation_candidate=is_reconciliation,
                        parser_used="docling",
                        footnote_type=footnote_type,
                    )
                    items.append(item)

                except Exception as cell_err:  # noqa: BLE001
                    # A single bad cell is captured as an error item (spec §6, AC-6, AC-7).
                    logger.warning(
                        "Error parsing cell in table %d of %s: %s",
                        table_idx,
                        source_file,
                        cell_err,
                    )
                    cell_val = ""
                    try:
                        cell_val = str(getattr(cell, "text", "") or "")
                    except Exception:  # noqa: BLE001
                        cell_val = ""

                    page_no = 1
                    try:
                        cell_prov = getattr(cell, "prov", [])
                        table_prov = getattr(table, "prov", [])
                        if cell_prov:
                            page_no = int(getattr(cell_prov[0], "page_no", 1))
                        elif table_prov:
                            page_no = int(getattr(table_prov[0], "page_no", 1))
                    except Exception:  # noqa: BLE001
                        page_no = 1

                    err_item = DoclingItem(
                        value=cell_val,
                        label="Error / Unparsed Cell",
                        page=page_no,
                        bbox=DoclingBbox(x0=0.0, y0=0.0, x1=0.0, y1=0.0),
                        source_file=source_file,
                        table_name=table_title,
                        is_error=True,
                        error_detail=str(cell_err),
                        is_reconciliation_candidate=is_reconciliation,
                        parser_used="docling",
                    )
                    items.append(err_item)

    except Exception as err:
        logger.error("Failed parsing table structures in %s: %s", source_file, err)
        raise DoclingParseError(
            f"Table structure extraction failed for {source_file}: {err}"
        ) from err

    # Deterministic sorting by page, then bbox y0, x0 (NFR1)
    items.sort(key=lambda item: (item.page, item.bbox.y0, item.bbox.x0))
    return items


def _parse_pdf_with_pymupdf(
    pdf_path: Path,
    source_file: str,
    target_metric: str = "Adjusted EBITDA",
    workflow_pack: str = "non_gaap_bridge",
) -> list[DoclingItem]:
    """
    Fast, robust native PyMuPDF table parser fallback (used when Docling is not installed or errors).
    """
    import fitz

    items: list[DoclingItem] = []
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as open_err:
        raise DoclingParseError(
            f"Could not open PDF with PyMuPDF: {open_err}"
        ) from open_err

    for page_idx, page in enumerate(doc):
        page_num = page_idx + 1
        try:
            tabs = page.find_tables()
        except Exception as tab_err:  # noqa: BLE001
            logger.warning(
                "PyMuPDF table detection failed on page %d: %s", page_num, tab_err
            )
            continue

        for table_idx, table in enumerate(tabs.tables):
            try:
                extracted = table.extract()
                if not extracted or len(extracted) < 2:
                    continue

                # Header row
                raw_headers = [str(c or "").strip() for c in extracted[0]]
                col_headers = raw_headers
                table_title = " / ".join([h for h in raw_headers if h])
                sample_text = " ".join(
                    [str(c or "") for row in extracted[:6] for c in row if c]
                )
                is_reconciliation = is_table_relevant_for_pack(
                    table_title, workflow_pack, target_metric, sample_text=sample_text
                )

                num_cols = getattr(table, "col_count", len(extracted[0]))

                # Process data rows
                for row_idx in range(1, len(extracted)):
                    row = extracted[row_idx]
                    row_label = str(row[0] or "").strip() if len(row) > 0 else ""

                    for col_idx in range(1, len(row)):
                        cell_text = str(row[col_idx] or "").strip()
                        if not cell_text:
                            continue

                        if _is_noise_cell(cell_text, row_idx, col_idx):
                            continue

                        col_header = (
                            col_headers[col_idx] if col_idx < len(col_headers) else ""
                        )
                        label_parts = [p for p in [row_label, col_header] if p]
                        label = (
                            " / ".join(label_parts)
                            if label_parts
                            else (row_label or cell_text)
                        )

                        # Cell bounding box fallback to whole table
                        cell_bbox = DoclingBbox(
                            x0=float(table.bbox[0]),
                            y0=float(table.bbox[1]),
                            x1=float(table.bbox[2]),
                            y1=float(table.bbox[3]),
                        )

                        # Prefer direct row/col cell access from PyMuPDF table.rows
                        if (
                            hasattr(table, "rows")
                            and table.rows
                            and row_idx < len(table.rows)
                            and hasattr(table.rows[row_idx], "cells")
                            and col_idx < len(table.rows[row_idx].cells)
                        ):
                            cb = table.rows[row_idx].cells[col_idx]
                            if isinstance(cb, (list, tuple)) and len(cb) >= 4:
                                cell_bbox = DoclingBbox(
                                    x0=float(cb[0]),
                                    y0=float(cb[1]),
                                    x1=float(cb[2]),
                                    y1=float(cb[3]),
                                )
                        elif (
                            hasattr(table, "cells")
                            and isinstance(table.cells, (list, tuple))
                            and table.cells
                        ):
                            flat_idx = (row_idx - 1) * num_cols + (col_idx - 1)
                            if flat_idx < len(table.cells):
                                cb = table.cells[flat_idx]
                                if isinstance(cb, (list, tuple)) and len(cb) >= 4:
                                    cell_bbox = DoclingBbox(
                                        x0=float(cb[0]),
                                        y0=float(cb[1]),
                                        x1=float(cb[2]),
                                        y1=float(cb[3]),
                                    )

                        _DEBT_TITLE_REGEX = re.compile(
                            r"(note\s+(?:8|\d+)[.:\s-]*)?(debt|credit\s+facilities|financing\s+arrangements|long-term\s+debt|borrowings|senior\s+notes|notes\s+payable|debt\s+obligations)",
                            re.IGNORECASE,
                        )
                        is_debt_footnote = bool(_DEBT_TITLE_REGEX.search(table_title))
                        footnote_type = "debt" if is_debt_footnote else None

                        items.append(
                            DoclingItem(
                                value=cell_text,
                                label=label,
                                page=page_num,
                                bbox=cell_bbox,
                                source_file=source_file,
                                table_name=table_title or None,
                                is_reconciliation_candidate=is_reconciliation,
                                parser_used="pymupdf",
                                footnote_type=footnote_type,
                            )
                        )
            except Exception as table_err:  # noqa: BLE001
                logger.warning(
                    "Error parsing table %d on page %d: %s",
                    table_idx,
                    page_num,
                    table_err,
                )
                continue

    items.sort(key=lambda item: (item.page, item.bbox.y0, item.bbox.x0))
    return items
