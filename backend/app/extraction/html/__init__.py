"""
HTML / iXBRL Extraction Package (FN-021).
"""

from app.extraction.html.detector import (
    detect_reconciliation_tables,
    score_reconciliation_table,
)
from app.extraction.html.extractor import HtmlExtractor
from app.extraction.html.ixbrl_parser import parse_ixbrl_facts
from app.extraction.html.models import (
    HtmlCell,
    HtmlExtractionResult,
    HtmlTable,
    IxbrlFact,
)
from app.extraction.html.table_parser import extract_html_tables, parse_numeric_cell

__all__ = [
    "HtmlCell",
    "HtmlExtractionResult",
    "HtmlExtractor",
    "HtmlTable",
    "IxbrlFact",
    "detect_reconciliation_tables",
    "extract_html_tables",
    "parse_ixbrl_facts",
    "parse_numeric_cell",
    "score_reconciliation_table",
]
