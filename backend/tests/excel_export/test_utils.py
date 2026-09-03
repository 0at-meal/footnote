"""
Unit tests for shared Excel export utilities (Step 8).
"""

from app.excel_export.utils import (
    col_to_letter,
    parse_numeric_value,
    to_cell_coord,
)
from app.extraction.docling_parser import is_table_relevant_for_pack


def test_parse_numeric_value_handles_formats() -> None:
    """Tests currency, commas, negative parens, and percentages."""
    assert parse_numeric_value("$1,234.56") == 1234.56
    assert parse_numeric_value("(1,234.56)") == -1234.56
    assert parse_numeric_value("($500)") == -500.0
    assert parse_numeric_value("45.2%") == 45.2
    assert parse_numeric_value("-") is None
    assert parse_numeric_value("invalid") is None
    assert parse_numeric_value(42) == 42.0
    assert parse_numeric_value(None) is None


def test_col_to_letter_and_to_cell_coord() -> None:
    """Tests 0-indexed column conversions to Excel letters and A1 coords."""
    assert col_to_letter(0) == "A"
    assert col_to_letter(25) == "Z"
    assert col_to_letter(26) == "AA"
    assert col_to_letter(27) == "AB"

    assert to_cell_coord(0, 0) == "A1"
    assert to_cell_coord(3, 2) == "C4"
    assert to_cell_coord(9, 5) == "F10"


def test_is_table_relevant_for_pack() -> None:
    """Step 7: Bounded extraction table routing per workflow pack."""
    # Non-GAAP Bridge
    assert is_table_relevant_for_pack("Reconciliation of Non-GAAP Net Income", "non_gaap_bridge")
    assert is_table_relevant_for_pack("Adjusted EBITDA Bridge", "non_gaap_bridge")
    assert not is_table_relevant_for_pack("Consolidated Balance Sheets", "non_gaap_bridge")

    # Capital Structure & Debt Sizing
    assert is_table_relevant_for_pack("Note 8 - Debt and Credit Facilities", "capital_structure")
    assert is_table_relevant_for_pack("Operating Leases and Commitments", "capital_structure")
    assert not is_table_relevant_for_pack("Statement of Operations", "capital_structure")

    # Cash Conversion
    assert is_table_relevant_for_pack("Consolidated Statement of Cash Flows", "cash_conversion")
    assert is_table_relevant_for_pack("Working Capital Changes", "cash_conversion")
    assert not is_table_relevant_for_pack("Executive Compensation Summary", "cash_conversion")
