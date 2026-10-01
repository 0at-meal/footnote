"""
Reconciliation Table Detector for HTML Filings (FN-021).

Ports deterministic reconciliation detection heuristics (keywords + structure)
to HTML tables extracted from SEC EDGAR.
"""

import logging

from app.extraction.html.models import HtmlTable

logger = logging.getLogger(__name__)

RECON_KEYWORDS = [
    "reconciliation",
    "non-gaap",
    "non gaap",
    "adjusted ebitda",
    "ebitda",
    "constant currency",
    "free cash flow",
]

EXCLUDED_TITLES = [
    "comprehensive income",
    "stockholders' equity",
    "shareholders' equity",
    "statement of equity",
    "equity (deficit)",
]

GAAP_START_TERMS = [
    "net income",
    "net loss",
    "operating income",
    "income from operations",
    "income before taxes",
]

ADJUSTMENT_TERMS = [
    "depreciation",
    "amortization",
    "interest expense",
    "income tax",
    "stock-based compensation",
    "share-based compensation",
    "restructuring",
    "impairment",
    "acquisition-related",
    "litigation",
]

NON_GAAP_END_TERMS = [
    "adjusted ebitda",
    "ebitda",
    "adjusted net income",
    "non-gaap net income",
    "free cash flow",
    "adjusted operating income",
]


def score_reconciliation_table(
    table: HtmlTable,
    target_metric: str = "Adjusted EBITDA",
    workflow_pack: str = "non_gaap_bridge",
) -> float:
    """
    Scores how likely an HTML table is to be a non-GAAP reconciliation table.
    Score ranges from 0.0 to 1.0+.
    """
    title_lower = table.title.lower()

    # Exclusions
    if any(ex in title_lower for ex in EXCLUDED_TITLES) and not any(kw in title_lower for kw in RECON_KEYWORDS):
        return 0.0

    score = 0.0

    # 1. Title keyword matching
    if target_metric and target_metric.lower() in title_lower:
        score += 0.5
    if any(kw in title_lower for kw in RECON_KEYWORDS):
        score += 0.4

    # 2. Structural checks on row labels
    row_texts = [lbl.lower() for lbl in table.row_headers.values()]

    # Check start term (Net income / Net loss)
    has_start = any(any(st in r for st in GAAP_START_TERMS) for r in row_texts[:4])
    if has_start:
        score += 0.25

    # Check adjustment terms
    adj_count = sum(1 for term in ADJUSTMENT_TERMS if any(term in r for r in row_texts))
    if adj_count >= 2:
        score += 0.3
    elif adj_count == 1:
        score += 0.15

    # Check ending non-GAAP metric
    has_end = any(any(en in r for en in NON_GAAP_END_TERMS) for r in row_texts[-4:])
    if has_end:
        score += 0.35

    # Check if target metric appears in row headers
    if target_metric and any(target_metric.lower() in r for r in row_texts):
        score += 0.4

    # Penalty for tables with no numeric values
    has_numbers = any(c.numeric_value is not None for c in table.cells)
    if not has_numbers:
        return 0.0

    return score


def detect_reconciliation_tables(
    tables: list[HtmlTable],
    target_metric: str = "Adjusted EBITDA",
    workflow_pack: str = "non_gaap_bridge",
    threshold: float = 0.5,
) -> list[HtmlTable]:
    """
    Filters and ranks tables that represent non-GAAP reconciliations.
    """
    candidate_tables: list[HtmlTable] = []
    for table in tables:
        score = score_reconciliation_table(table, target_metric=target_metric, workflow_pack=workflow_pack)
        table.reconciliation_score = score
        if score >= threshold:
            table.is_reconciliation = True
            candidate_tables.append(table)

    # Sort descending by score
    candidate_tables.sort(key=lambda t: t.reconciliation_score, reverse=True)
    return candidate_tables
