"""
Extractor for 8-K EX-99.1 earnings press releases.

Only HTML exhibits are supported. PDF and image exhibits are logged and
return no records (the PDF pipeline was removed; see git tag v0-extraction).
Guidance reconciliations are tagged with a "Guidance > " label prefix.
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
            )
            records = result.records
        else:
            logger.warning("Unsupported exhibit format %s for %s", fmt, filename)
            records = []

        # Tag guidance records
        for r in records:
            if is_guidance_text(r.label) and "guidance" not in r.label.lower():
                r.label = f"Guidance > {r.label}"

        return records
