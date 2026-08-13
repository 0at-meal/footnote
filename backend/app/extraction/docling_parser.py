"""
Docling structural PDF parser for Feature 2, Step 1.

Scope:
    Runs Docling's layout parser on a local PDF file and extracts raw table cells
    with hierarchical header labels, 1-indexed page numbers, and Docling bounding boxes.

Isolation (CONSTITUTION §3.8, §3.2):
    This module must NEVER import from classification/, formula_engine/, excel_export/,
    or audit_report/.
"""

import logging
import os
from pathlib import Path
from typing import Any

# Disable PyTorch Inductor compilation to prevent missing MSVC cl.exe compiler errors on Windows
os.environ["TORCH_COMPILE_DISABLE"] = "1"
os.environ["TORCHINDUCTOR_DISABLE"] = "1"

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

from app.extraction.models import DoclingBbox, DoclingItem

logger = logging.getLogger(__name__)


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
        raise DoclingParseError(f"Docling conversion failed for {source_file}: {err}") from err

    items: list[DoclingItem] = []

    try:
        for table_idx, table in enumerate(doc.tables):
            table_data = getattr(table, "data", None)
            if table_data is None:
                continue

            table_cells: list[Any] = getattr(table_data, "table_cells", [])

            if not table_cells:
                continue

            # Identify header text by column and row indices
            col_headers: dict[int, list[str]] = {}
            row_headers: dict[int, list[str]] = {}

            for cell in table_cells:
                try:
                    cell_text = (cell.text or "").strip()
                    if not cell_text:
                        continue

                    is_col_header = getattr(cell, "column_header", False)
                    is_row_header = getattr(cell, "row_header", False) or getattr(cell, "row_section_header", False)

                    col_idx = getattr(cell, "start_col_offset_idx", 0)
                    row_idx = getattr(cell, "start_row_offset_idx", 0)

                    if is_col_header:
                        col_headers.setdefault(col_idx, []).append(cell_text)
                    if is_row_header:
                        row_headers.setdefault(row_idx, []).append(cell_text)
                except Exception as header_err:  # noqa: BLE001 — malformed cell skipped; does not abort header scan
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

                    # Assemble structural label path
                    label_parts: list[str] = []

                    # Add row section/headers for this row
                    if row_idx in row_headers and not getattr(cell, "row_header", False):
                        label_parts.extend(row_headers[row_idx])

                    # Add column headers for this column
                    if col_idx in col_headers and not getattr(cell, "column_header", False):
                        label_parts.extend(col_headers[col_idx])

                    label = " / ".join(label_parts) if label_parts else cell_text

                    # Extract page number and bbox from provenance
                    prov_list = getattr(cell, "prov", [])
                    page_no = 1
                    bbox_obj = DoclingBbox(x0=0.0, y0=0.0, x1=0.0, y1=0.0)

                    if prov_list:
                        prov = prov_list[0]
                        page_no = getattr(prov, "page_no", 1)
                        raw_bbox = getattr(prov, "bbox", None)
                        if raw_bbox is not None:
                            # Extract l, t, r, b or x0, y0, x1, y1
                            x0 = float(getattr(raw_bbox, "l", getattr(raw_bbox, "x0", 0.0)))
                            y0 = float(getattr(raw_bbox, "t", getattr(raw_bbox, "y0", 0.0)))
                            x1 = float(getattr(raw_bbox, "r", getattr(raw_bbox, "x1", 0.0)))
                            y1 = float(getattr(raw_bbox, "b", getattr(raw_bbox, "y1", 0.0)))
                            bbox_obj = DoclingBbox(x0=x0, y0=y0, x1=x1, y1=y1)

                    item = DoclingItem(
                        value=cell_text,
                        label=label,
                        page=page_no,
                        bbox=bbox_obj,
                        source_file=source_file,
                    )
                    items.append(item)

                except Exception as cell_err:  # noqa: BLE001 — Docling cell attrs raise any exception type; broad catch is intentional
                    # A single bad cell is logged and skipped — it must not abort
                    # the entire job (spec AC-6, AC-7: single-item failure ≠ job failure).
                    logger.warning(
                        "Skipping malformed cell in table %d of %s: %s",
                        table_idx,
                        source_file,
                        cell_err,
                    )
                    continue

    except Exception as err:
        logger.error("Failed parsing table structures in %s: %s", source_file, err)
        raise DoclingParseError(f"Table structure extraction failed for {source_file}: {err}") from err

    # Deterministic sorting by page, then bbox y0, x0 (NFR1)
    items.sort(key=lambda item: (item.page, item.bbox.y0, item.bbox.x0))
    return items
