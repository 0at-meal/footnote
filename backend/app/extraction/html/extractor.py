"""
HTML / iXBRL Extractor for SEC EDGAR Filings (FN-021).

Coordinates:
1. iXBRL fact extraction (authoritative GAAP lines).
2. HTML table extraction with colspan/rowspan reconstruction and period binding.
3. Non-GAAP reconciliation table detection.
4. Construction of ExtractedRecord with HtmlLocator.
5. Invariant I3 compliance: explicit 'not_found' status if no reconciliation table exists.
"""

import logging
import time

from bs4 import BeautifulSoup

from app.extraction.html.detector import detect_reconciliation_tables
from app.extraction.html.ixbrl_parser import parse_ixbrl_facts
from app.extraction.html.models import (
    HtmlExtractionResult,
)
from app.extraction.html.table_parser import extract_html_tables
from app.extraction.locator import HtmlLocator, is_sec_archives_url, sec_archives_url
from app.extraction.models import ExtractedRecord

logger = logging.getLogger(__name__)


class HtmlExtractor:
    """
    Parser and extractor for SEC EDGAR HTML/iXBRL filings.
    """

    def __init__(self, parser_flavor: str = "lxml") -> None:
        self.parser_flavor = parser_flavor

    def extract(
        self,
        html_content: str | bytes,
        accession: str,
        document_name: str,
        url: str | None = None,
        target_metric: str = "Adjusted EBITDA",
        workflow_pack: str = "non_gaap_bridge",
        cik: str | None = None,
    ) -> HtmlExtractionResult:
        """
        Extracts records and authoritative facts from an HTML filing.

        Returns:
            HtmlExtractionResult with status 'success' or 'not_found' (Invariant I3).
        """
        start_time = time.monotonic()

        # Parse with BeautifulSoup (using lxml for high performance)
        try:
            soup = BeautifulSoup(html_content, self.parser_flavor)
        except Exception:  # noqa: BLE001
            soup = BeautifulSoup(html_content, "html.parser")

        # 1. Parse authoritative iXBRL facts
        facts = parse_ixbrl_facts(soup)

        # 2. Extract HTML tables
        tables = extract_html_tables(soup)

        # 3. Detect candidate reconciliation tables
        candidate_tables = detect_reconciliation_tables(
            tables,
            target_metric=target_metric,
            workflow_pack=workflow_pack,
        )

        elapsed = time.monotonic() - start_time

        # 4. Explicit 'not_found' handling per Invariant I3
        if not candidate_tables:
            return HtmlExtractionResult(
                status="not_found",
                not_found_reason=(
                    f"No non-GAAP reconciliation table matching '{target_metric}' "
                    f"found in document '{document_name}' across {len(tables)} tables scanned."
                ),
                records=[],
                ixbrl_facts=facts,
                tables_scanned=len(tables),
                duration_seconds=elapsed,
            )

        # 5. Build ExtractedRecord instances with HtmlLocator
        records: list[ExtractedRecord] = []
        # D9 / AUD-018: a CIK-qualified Archives URL, or none at all (the CIK-less form returned 404).
        base_url = url if is_sec_archives_url(url) else sec_archives_url(cik, accession, document_name)

        for table in candidate_tables:
            for cell in table.cells:
                # We only extract data cells (cells that have a numeric value)
                if cell.numeric_value is None:
                    continue

                row_label = table.row_headers.get(cell.row_idx, "").strip()
                if not row_label:
                    continue

                # Build hierarchical label
                components: list[str] = []
                if table.title and table.title not in row_label:
                    components.append(table.title)
                if cell.period:
                    components.append(cell.period)
                components.append(row_label)

                full_label = " > ".join(components)

                locator = HtmlLocator(
                    cik=cik,
                    accession=accession,
                    document=document_name,
                    element_path=cell.xpath,
                    char_range=cell.char_range,
                    url=base_url,
                )

                rec = ExtractedRecord(
                    value=cell.text.strip(),
                    label=full_label,
                    page=1,
                    bbox={"x0": 0.0, "y0": 0.0, "x1": 1000.0, "y1": 1000.0},
                    source_file=document_name,
                    locator=locator,
                    is_reconciliation_candidate=True,
                )
                records.append(rec)

        return HtmlExtractionResult(
            status="success",
            records=records,
            ixbrl_facts=facts,
            tables_scanned=len(tables),
            duration_seconds=elapsed,
        )
