"""
Extractor for 8-K EX-99.1 Press Releases (FN-022).

Handles:
- HTML extraction via HtmlExtractor.
- Routing of PDF/image exhibits to fallback parser.
- Extraction and segregation of quarterly vs YTD and guidance reconciliations.
"""

import logging

from app.extraction.html.extractor import HtmlExtractor
from app.extraction.html.models import HtmlExtractionResult
from app.extraction.models import ExtractedRecord
from app.ingestion.exhibit_99.detector import (
    classify_exhibit_format,
    is_guidance_text,
)
from app.ingestion.exhibit_99.models import ExhibitFormat

logger = logging.getLogger(__name__)


class Exhibit99Extractor:
    """
    Extracts reconciliation records from 8-K EX-99.1 press releases.
    """

    def __init__(self, html_extractor: HtmlExtractor | None = None) -> None:
        self.html_extractor = html_extractor or HtmlExtractor()

    def extract_from_content(
        self,
        content: bytes | str,
        filename: str,
        accession: str,
        url: str | None = None,
        target_metric: str = "Adjusted EBITDA",
        cik: str | None = None,
    ) -> list[ExtractedRecord]:
        """
        Extracts records from an EX-99.1 document, routing by format.
        """
        fmt = classify_exhibit_format(filename)

        if fmt == ExhibitFormat.HTML:
            html_str = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content
            result: HtmlExtractionResult = self.html_extractor.extract(
                html_content=html_str,
                accession=accession,
                document_name=filename,
                url=url,
                target_metric=target_metric,
                cik=cik,
            )
            records = result.records
        elif fmt == ExhibitFormat.PDF:
            # Route to PDF fallback
            # Note: docling_parser expects a file path
            import tempfile
            from pathlib import Path

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                if isinstance(content, str):
                    tmp.write(content.encode("utf-8"))
                else:
                    tmp.write(content)
                tmp_path = Path(tmp.name)

            try:
                from app.extraction.assembler import assemble_records
                from app.extraction.coordinate_normalizer import normalize_coordinates
                from app.extraction.docling_parser import parse_pdf

                docling_items = parse_pdf(
                    pdf_path=tmp_path,
                    source_file=filename,
                    target_metric=target_metric,
                )
                normalized = normalize_coordinates(tmp_path, docling_items)
                records = assemble_records(normalized)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
        else:
            logger.warning("Unsupported exhibit format %s for %s", fmt, filename)
            records = []

        # Tag guidance records
        for r in records:
            if is_guidance_text(r.label) and "guidance" not in r.label.lower():
                r.label = f"Guidance > {r.label}"

        return records
