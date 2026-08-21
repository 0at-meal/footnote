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
from pathlib import Path
import re
from typing import Any

# Disable PyTorch Inductor compilation to prevent missing MSVC cl.exe compiler errors on Windows
os.environ["TORCH_COMPILE_DISABLE"] = "1"
os.environ["TORCHINDUCTOR_DISABLE"] = "1"

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
    if not has_digit:
        if cleaned.lower() not in _FINANCIAL_PLACEHOLDERS:
            return True

    return False


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
    except Exception:  # noqa: BLE001
        pass

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
    except Exception:  # noqa: BLE001
        pass

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
        except Exception:  # noqa: BLE001
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
                    kw in lower for kw in ["reconciliation", "non-gaap", "adjusted ebitda"]
                ):
                    return text
        except Exception:  # noqa: BLE001
            continue

    return f"Table {table_idx + 1}"


class DoclingParseError(Exception):
    """Raised when an unrecoverable structural parse error occurs during extraction."""


def parse_pdf(pdf_path: Path, source_file: str) -> list[DoclingItem]:
    """
    Parse a local PDF filing using Docling and extract raw table cell items.

    Args:
        pdf_path: Absolute or relative Path to the stored PDF file on disk.
        source_file: Original filename string stored in the job record (UTF-8, EC-8).

    Returns:
        List of DoclingItem objects ordered deterministically by page, row, col (NFR1).

    Raises:
        DoclingParseError: If the file cannot be parsed or table structures are invalid.
        FileNotFoundError: If pdf_path does not exist on disk.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found at path: {pdf_path}")

    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

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
    except Exception as err:
        logger.error("Docling failed to convert PDF %s: %s", pdf_path, err)
        raise DoclingParseError(
            f"Docling conversion failed for {source_file}: {err}"
        ) from err

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

            # Identify header text by column and row indices
            col_headers: dict[int, list[str]] = {}
            row_headers: dict[int, list[str]] = {}

            for cell in table_cells:
                try:
                    cell_text = (cell.text or "").strip()
                    if not cell_text:
                        continue

                    is_col_header = getattr(cell, "column_header", False)
                    is_row_header = getattr(cell, "row_header", False) or getattr(
                        cell, "row_section_header", False
                    )

                    col_idx = getattr(cell, "start_col_offset_idx", 0)
                    row_idx = getattr(cell, "start_row_offset_idx", 0)

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

                    is_header = (
                        getattr(cell, "column_header", False)
                        or getattr(cell, "row_header", False)
                        or getattr(cell, "row_section_header", False)
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
                        x0 = float(
                            getattr(raw_bbox, "l", getattr(raw_bbox, "x0", 0.0))
                        )
                        y0 = float(
                            getattr(raw_bbox, "t", getattr(raw_bbox, "y0", 0.0))
                        )
                        x1 = float(
                            getattr(raw_bbox, "r", getattr(raw_bbox, "x1", 0.0))
                        )
                        y1 = float(
                            getattr(raw_bbox, "b", getattr(raw_bbox, "y1", 0.0))
                        )
                        bbox_obj = DoclingBbox(x0=x0, y0=y0, x1=x1, y1=y1)

                    item = DoclingItem(
                        value=cell_text,
                        label=label,
                        page=page_no,
                        bbox=bbox_obj,
                        source_file=source_file,
                        table_name=table_title,
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
