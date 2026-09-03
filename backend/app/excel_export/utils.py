"""
Shared Excel export utility functions (Step 8).

Provides deduplicated numeric parsing, coordinate conversions, and format strings.
"""

from __future__ import annotations

from typing import Any

# Standard IB currency number format with 2 decimals
IB_CURRENCY_FORMAT = '$#,##0.00;($#,##0.00);"-"'

# Standard IB currency number format without decimals (integers)
IB_INTEGER_CURRENCY_FORMAT = '$#,##0;($#,##0);"-"'


def parse_numeric_value(raw_val: Any) -> float | None:
    """
    Parses a raw value (str, int, float) into a float, supporting commas,
    currency signs, percentage signs, and parentheses for negatives.
    Returns None if parsing fails.
    """
    if raw_val is None:
        return None
    if isinstance(raw_val, (int, float)):
        return float(raw_val)

    s = str(raw_val).strip()
    if not s or s in ("-", "—", "N/A", "n/a"):
        return None

    is_negative = False
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1].strip()

    cleaned = s.replace(",", "").replace("$", "").replace("%", "").strip()
    try:
        val = float(cleaned)
        return -val if is_negative else val
    except ValueError:
        return None


def _parse_numeric_value(raw_val: str) -> tuple[float | None, bool]:
    """
    Parses a raw string value into a float, supporting commas, parentheses for negatives.

    Returns:
        (parsed_float_or_None, is_valid_number)
    """
    val = parse_numeric_value(raw_val)
    if val is not None:
        return val, True
    return None, False


def col_to_letter(col_idx: int) -> str:
    """Converts 0-indexed column number to Excel column letter (0 -> 'A', 5 -> 'F', 26 -> 'AA')."""
    result = ""
    col = col_idx
    while col >= 0:
        result = chr(ord("A") + (col % 26)) + result
        col = (col // 26) - 1
    return result


def _col_to_letter(col_idx: int) -> str:
    """Alias for col_to_letter."""
    return col_to_letter(col_idx)


def to_cell_coord(row_idx: int, col_idx: int) -> str:
    """Converts 0-indexed (row, col) to A1-style coordinate (e.g. (1, 5) -> 'F2')."""
    return f"{col_to_letter(col_idx)}{row_idx + 1}"


def _to_cell_coord(row_idx: int, col_idx: int) -> str:
    """Alias for to_cell_coord."""
    return to_cell_coord(row_idx, col_idx)
