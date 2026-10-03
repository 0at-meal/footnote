"""
HTML Table Parser for SEC EDGAR filings (FN-021).

Handles:
- colspan and rowspan grid reconstruction.
- Split currency cells ($ in adjacent column).
- Negative numbers in accounting parentheses: (123) -> -123.
- Footnote marker stripping from numeric values.
- Multi-column period alignment (assigning fiscal period to each column).
- Canonical W3C XPath generation for cell provenance.
"""

import logging
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from app.extraction.html.models import HtmlCell, HtmlTable

logger = logging.getLogger(__name__)

# Patterns for period detection
PERIOD_PATTERNS = [
    re.compile(r"(three\s+months\s+ended\s+[a-z]+\s+\d{1,2},\s+\d{4})", re.IGNORECASE),
    re.compile(r"(six\s+months\s+ended\s+[a-z]+\s+\d{1,2},\s+\d{4})", re.IGNORECASE),
    re.compile(r"(nine\s+months\s+ended\s+[a-z]+\s+\d{1,2},\s+\d{4})", re.IGNORECASE),
    re.compile(r"(twelve\s+months\s+ended\s+[a-z]+\s+\d{1,2},\s+\d{4})", re.IGNORECASE),
    re.compile(r"(year\s+ended\s+[a-z]+\s+\d{1,2},\s+\d{4})", re.IGNORECASE),
    re.compile(r"([a-z]+\s+\d{1,2},\s+\d{4})", re.IGNORECASE),
    re.compile(r"\b(Q[1-4]\s+(?:FY)?\d{2,4})\b", re.IGNORECASE),
    re.compile(r"\b(20\d{2}|19\d{2})\b"),
]

# Patterns for accounting parentheses
PARENTHESES_PATTERN = re.compile(r"^\s*\(\s*([0-9,]+(?:\.[0-9]+)?)\s*\)\s*$")
CLEAN_NUM_PATTERN = re.compile(r"^\s*([0-9,]+(?:\.[0-9]+)?)\s*$")
FOOTNOTE_REF_PATTERN = re.compile(r"\s*(?:\([a-z0-9]\)|\[[a-z0-9]\]|\*+)\s*$", re.IGNORECASE)


def parse_numeric_cell(text: str) -> tuple[float | None, str]:
    """
    Parses a string into a float and cleaned representation.
    Handles parentheses for negative values: (123) -> -123.0
    Strips currency symbols ($) and footnote markers.
    """
    raw = text.strip()
    if not raw or raw in {"—", "-", "–", "--", "N/A", "n/a", "None"}:
        return None, raw

    # Strip footnote references at end
    cleaned = FOOTNOTE_REF_PATTERN.sub("", raw).strip()
    # Strip currency symbol
    cleaned = cleaned.replace("$", "").replace("€", "").replace("£", "").strip()

    # Check parentheses
    paren_match = PARENTHESES_PATTERN.match(cleaned)
    if paren_match:
        val_str = paren_match.group(1).replace(",", "")
        try:
            return -float(val_str), f"-{val_str}"
        except ValueError:
            return None, raw

    # Normal number
    clean_match = CLEAN_NUM_PATTERN.match(cleaned)
    if clean_match:
        val_str = clean_match.group(1).replace(",", "")
        try:
            return float(val_str), val_str
        except ValueError:
            return None, raw

    return None, raw


def get_element_xpath(element: Tag) -> str:
    """Computes a canonical 1-indexed XPath for a BeautifulSoup element."""
    path_components: list[str] = []
    current: Any = element
    while current is not None and getattr(current, "name", None) not in [None, "[document]", "html"]:
        parent = current.parent
        if parent is None:
            break
        # Count preceding siblings of the same tag name
        siblings = [s for s in parent.children if getattr(s, "name", None) == current.name]
        if len(siblings) > 1:
            idx = siblings.index(current) + 1
            path_components.append(f"{current.name}[{idx}]")
        else:
            path_components.append(current.name)
        current = parent
    
    path_components.append("html")
    path_components.reverse()
    return "/" + "/".join(path_components)


def extract_html_tables(soup: BeautifulSoup) -> list[HtmlTable]:
    """
    Extracts all HTML tables with resolved colspans, rowspans, and period alignment.
    """
    tables: list[HtmlTable] = []

    for table_idx, table_tag in enumerate(soup.find_all("table")):
        table_xpath = get_element_xpath(table_tag)

        # Build grid to handle colspan and rowspan
        rows = table_tag.find_all("tr")
        if not rows:
            continue

        grid: dict[tuple[int, int], HtmlCell] = {}
        max_cols = 0

        for r_idx, row in enumerate(rows):
            c_idx = 0
            # Find all td and th
            cells = row.find_all(["td", "th"])
            for cell_tag in cells:
                # Find the next free column in this row
                while (r_idx, c_idx) in grid:
                    c_idx += 1

                colspan = 1
                try:
                    cs = cell_tag.get("colspan")
                    if cs:
                        colspan = max(1, int(str(cs)))
                except (ValueError, TypeError):
                    colspan = 1

                rowspan = 1
                try:
                    rs = cell_tag.get("rowspan")
                    if rs:
                        rowspan = max(1, int(str(rs)))
                except (ValueError, TypeError):
                    rowspan = 1

                cell_text = cell_tag.get_text(separator=" ", strip=True)
                is_header = cell_tag.name == "th" or r_idx < 3

                # Compute numeric value if applicable
                num_val, cleaned_str = parse_numeric_cell(cell_text)

                cell_xpath = get_element_xpath(cell_tag)

                cell_obj = HtmlCell(
                    row_idx=r_idx,
                    col_idx=c_idx,
                    text=cell_text,
                    cleaned_value=cleaned_str,
                    numeric_value=num_val,
                    colspan=colspan,
                    rowspan=rowspan,
                    is_header=is_header,
                    xpath=cell_xpath,
                )

                # Fill grid for spans
                for dr in range(rowspan):
                    for dc in range(colspan):
                        grid[(r_idx + dr, c_idx + dc)] = cell_obj

                c_idx += colspan
                max_cols = max(max_cols, c_idx)

        num_rows = len(rows)

        # Detect column periods from header rows (rows 0 to min(3, num_rows - 1))
        col_periods: dict[int, str] = {}
        for c in range(max_cols):
            periods_found: list[str] = []
            for r in range(min(4, num_rows)):
                cell = grid.get((r, c))
                if cell and cell.text:
                    for pattern in PERIOD_PATTERNS:
                        match = pattern.search(cell.text)
                        if match:
                            periods_found.append(match.group(1))
                            break
            if periods_found:
                # Use the most specific period found
                col_periods[c] = periods_found[0]

        # Handle split currency columns: if col c has "$" and col c+1 has a number
        for r in range(num_rows):
            for c in range(max_cols - 1):
                cell_curr = grid.get((r, c))
                cell_val = grid.get((r, c + 1))
                if cell_curr and cell_val and cell_curr.text.strip() == "$" and cell_val.numeric_value is not None:
                    # Bind currency to cell_val
                    cell_val.cleaned_value = f"${cell_val.cleaned_value}"

        # Assign periods to cells
        row_headers: dict[int, str] = {}
        col_headers: dict[int, str] = col_periods

        table_cells: list[HtmlCell] = []
        for (r, c), cell in sorted(grid.items(), key=lambda item: (item[0][0], item[0][1])):
            # Only include the primary instance (top-left) of spanned cells
            if cell.row_idx == r and cell.col_idx == c:
                if c in col_periods:
                    cell.period = col_periods[c]
                table_cells.append(cell)
                # If column 0 or 1 contains row title
                if c <= 1 and cell.numeric_value is None and cell.text.strip() and (r not in row_headers or len(cell.text) > len(row_headers[r])):
                    row_headers[r] = cell.text.strip()

        # Find table title from preceding paragraph, caption, or first header
        title = ""
        caption = table_tag.find("caption")
        if caption and caption.get_text(strip=True):
            title = caption.get_text(strip=True)
        else:
            # Check preceding sibling tags (p, div, h1-h6)
            prev = table_tag.find_previous_sibling(["p", "div", "h1", "h2", "h3", "h4", "h5", "h6"])
            if prev and prev.get_text(strip=True):
                txt = prev.get_text(strip=True)
                if len(txt) < 200:
                    title = txt

        if not title:
            # Check row 0
            r0_cells = [grid.get((0, c)) for c in range(max_cols) if grid.get((0, c))]
            for cell_item in r0_cells:
                if cell_item and cell_item.text and len(cell_item.text) > 3 and cell_item.numeric_value is None:
                    title = cell_item.text
                    break

        html_table = HtmlTable(
            index=table_idx,
            title=title or f"Table {table_idx + 1}",
            xpath=table_xpath,
            cells=table_cells,
            row_headers=row_headers,
            col_headers=col_headers,
        )
        tables.append(html_table)

    return tables
