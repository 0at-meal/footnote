"""
P0-05: auto-draft each gold release's headline bridge and verify it.

For every release in the P0-03 manifest this tool:

1. reads the saved exhibit and the approved table (``eval/gold/issuers.yaml``);
2. extracts the headline Adjusted EBITDA bridge: every period column, the GAAP
   starting line, adjustments, subtotals and the headline total;
3. runs two independent checks per period:
   (a) **sum tie-out**: start + adjustments (contribution = sign x value) equals
       the stated total within max(1, ceil(n/2)) units of the reported scale;
   (b) **GAAP anchor**: the starting line equals the XBRL ``companyfacts`` value
       for the same CIK, period end, duration and unit;
4. writes ``eval/gold/drafts/<accession>.json``: draft labels in the P0-04 shape,
   check results, and an exception list for the owner (P0-06).

A value gets ``verified_by="tieout"`` only when *both* checks pass for its
period; otherwise ``verified_by`` is null and the period appears as an exception.
Drafts are inputs to P0-05b / P0-06; they are not gold labels until promoted.

Usage (from ``backend/``, with ``SEC_USER_AGENT`` set for the XBRL fetch)::

    python -m tools.gold.draft
"""

from __future__ import annotations

import argparse
import gzip
import itertools
import json
import math
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from app.extraction.html.models import HtmlCell, HtmlTable
from app.extraction.html.table_parser import extract_html_tables
from app.extraction.scale_and_sign import (
    UnitScale,
    detect_scale_from_caption,
    parse_raw_numeric,
)
from app.ingestion.edgar.client import EdgarClient
from bs4 import BeautifulSoup
from pydantic import ValidationError

from tools.gold.labels import GoldRelease, LineRole, Scale
from tools.gold.patterns import GAAP_START, NOT_A_TOTAL, SUBTRACT_DIRECTIVE

GOLD_DIR = Path(__file__).resolve().parents[3] / "eval" / "gold"
DRAFTS_DIR = GOLD_DIR / "drafts"
LABELER = "extractor (tools.gold.draft)"

DASHES = {"—", "–", "-", "--"}
_TABLE_NOTE = re.compile(r"^table\s+\S+$", re.IGNORECASE)
_SCALE_QUOTE = re.compile(
    r"\(?[^()]{0,60}\bin (?:thousands|millions|billions)\b[^()]{0,60}\)?",
    re.IGNORECASE,
)
_MONTHS_BY_WORD: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"\b(?:three|3)[- ]months?\b"), 3),
    (re.compile(r"\b(?:six|6)[- ]months?\b"), 6),
    (re.compile(r"\b(?:nine|9)[- ]months?\b"), 9),
    (re.compile(r"\b(?:twelve|12)[- ]months?\b"), 12),
    (re.compile(r"\b(?:thirteen|13)[- ]weeks?\b"), 3),
    (re.compile(r"\b(?:twenty[- ]six|26)[- ]weeks?\b"), 6),
    (re.compile(r"\b(?:thirty[- ]nine|39)[- ]weeks?\b"), 9),
    (re.compile(r"\b(?:fifty[- ](?:two|three)|5[23])[- ]weeks?\b"), 12),
    (re.compile(r"\bquarters? ended\b"), 3),
    (re.compile(r"\b(?:fiscal )?years? ended\b"), 12),
]
_DATE = re.compile(r"\b([A-Z][a-z]{2,8})\.?\s+(\d{1,2}),?\s+(\d{4})\b")
_DURATION_DAYS = {3: (80, 100), 6: (170, 195), 9: (260, 285), 12: (350, 380)}
_SCALE_TO_LABEL = {
    UnitScale.UNITS: Scale.units,
    UnitScale.THOUSANDS: Scale.thousands,
    UnitScale.MILLIONS: Scale.millions,
    UnitScale.BILLIONS: Scale.billions,
}


# ---------------------------------------------------------------- table model


@dataclass
class Row:
    idx: int
    label: str
    value_cells: list[HtmlCell]
    # Text of the label-only row directly above (not a "Heading:"), for labels
    # that wrap across two rows.
    wrapped_prefix: str = ""


def _span(cell: HtmlCell) -> tuple[int, int]:
    return cell.col_idx, cell.col_idx + cell.colspan


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _is_value_cell(cell: HtmlCell) -> bool:
    return cell.numeric_value is not None or cell.text.strip() in DASHES


_OPEN_PAREN_NUMBER = re.compile(r"^\(\s*\$?\s*([\d,]+(?:\.\d+)?)$")
_YEAR = re.compile(r"^(?:19|20)\d{2}$")


def merge_split_parentheses(cells: list[HtmlCell]) -> list[HtmlCell]:
    """
    EDGAR tables often split an accounting negative across cells: ``"(7"`` then
    ``")"``. Merge such pairs into one negative value cell and drop the ``")"``.
    """
    ordered = sorted(cells, key=lambda c: c.col_idx)
    out: list[HtmlCell] = []
    skip: set[int] = set()
    for i, cell in enumerate(ordered):
        if i in skip:
            continue
        match = _OPEN_PAREN_NUMBER.match(cell.text.strip())
        nxt = next(
            (j for j in range(i + 1, len(ordered)) if ordered[j].text.strip()), None
        )
        if match and nxt is not None and ordered[nxt].text.strip().startswith(")"):
            number = match.group(1)
            out.append(
                cell.model_copy(
                    update={
                        "text": f"({number})",
                        "numeric_value": -float(number.replace(",", "")),
                    }
                )
            )
            skip.add(nxt)
            continue
        out.append(cell)
    return out


def build_rows(table: HtmlTable) -> list[Row]:
    """
    One Row per table row. The label is the text of every non-value cell left of
    the first value cell (so indented labels in later columns are kept); "$"
    cells are dropped and split parentheses are merged.
    """
    by_row: dict[int, list[HtmlCell]] = {}
    for cell in table.cells:
        by_row.setdefault(cell.row_idx, []).append(cell)
    rows: list[Row] = []
    for idx in sorted(by_row):
        cells = merge_split_parentheses(by_row[idx])
        values = [c for c in cells if _is_value_cell(c)]
        first = min((c.col_idx for c in values), default=10**9)
        label = " ".join(
            c.text.strip()
            for c in cells
            if c.col_idx < first and c.text.strip() not in {"", "$"}
        )
        rows.append(
            Row(idx=idx, label=re.sub(r"\s+", " ", label).strip(), value_cells=values)
        )
    for prev, row in itertools.pairwise(rows):
        if (
            row.idx == prev.idx + 1
            and row.value_cells
            and not prev.value_cells
            and prev.label
            and not prev.label.endswith(":")
        ):
            row.wrapped_prefix = prev.label
    return rows


# ------------------------------------------------------------------- periods


@dataclass
class PeriodColumn:
    span: tuple[int, int]
    header: str
    months: int | None
    end_date: date | None

    @property
    def period_id(self) -> str | None:
        if self.months is None or self.end_date is None:
            return None
        return f"{self.months}M-{self.end_date.isoformat()}"


_QUARTER = re.compile(r"\b(?:([1-4])Q\s?'?(\d{2}|\d{4})|Q([1-4])\s?'?(\d{2}|\d{4}))\b")
_QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


def parse_period(
    header: str, fiscal_year_end: str = ""
) -> tuple[int | None, date | None]:
    """
    (months, end date) from a column header. Handles "Three Months Ended June 30,
    2026", week-based periods, and, for calendar fiscal years only, quarter
    notation such as "1Q26" / "Q2 2026" (QTD = 3 months, YTD = quarter x 3).
    """
    text = header.lower()
    months = next((m for pat, m in _MONTHS_BY_WORD if pat.search(text)), None)
    end: date | None = None
    for match in _DATE.finditer(header):
        stamp = f"{match.group(1)} {match.group(2)} {match.group(3)}"
        for fmt in ("%B %d %Y", "%b %d %Y"):
            try:
                end = datetime.strptime(stamp, fmt).date()  # noqa: DTZ007
                break
            except ValueError:
                continue
    quarter = _QUARTER.search(header)
    if end is None and quarter and fiscal_year_end == "1231":
        q = int(quarter.group(1) or quarter.group(3))
        yy = quarter.group(2) or quarter.group(4)
        year = int(yy) if len(yy) == 4 else 2000 + int(yy)
        month, day = _QUARTER_END[q]
        end = date(year, month, day)
        if months is None:
            months = q * 3 if "ytd" in text else 3
    return months, end


def period_columns(
    table: HtmlTable, start: Row, fiscal_year_end: str = ""
) -> list[PeriodColumn]:
    """Period columns from the start row's numeric cells and the headers above."""
    numeric = sorted(
        (c for c in start.value_cells if c.numeric_value is not None),
        key=lambda c: c.col_idx,
    )
    start_cells = [c for c in table.cells if c.row_idx == start.idx]
    value_area = min(
        (c.col_idx for c in start_cells if c.text.strip() == "$" or _is_value_cell(c)),
        default=0,
    )
    # A labelled row with values above the start row (e.g. a memo "Income
    # before income taxes" line) is data, not header; year rows are header.
    labelled = {
        c.row_idx for c in table.cells if c.col_idx < value_area and c.text.strip()
    }
    data_rows = {
        c.row_idx
        for c in table.cells
        if c.row_idx in labelled
        and c.col_idx >= value_area
        and (_is_value_cell(c) or _OPEN_PAREN_NUMBER.match(c.text.strip()))
        and not _YEAR.match(c.text.strip())
    }
    header_cells = [
        c
        for c in table.cells
        if c.row_idx < start.idx
        and c.row_idx not in data_rows
        and c.col_idx >= value_area
        and c.text.strip()
        and c.text.strip() != "$"
        and not _TABLE_NOTE.match(c.text.strip())
    ]
    out: list[PeriodColumn] = []
    for cell in numeric:
        parts = [
            h.text.strip()
            for h in sorted(header_cells, key=lambda h: (h.row_idx, h.col_idx))
            if _overlaps(_span(h), _span(cell))
        ]
        header = re.sub(r"\s+", " ", " ".join(parts)).strip()
        months, end = parse_period(header, fiscal_year_end)
        out.append(
            PeriodColumn(span=_span(cell), header=header, months=months, end_date=end)
        )
    return out


# ------------------------------------------------------------------- bridge


@dataclass
class DraftLine:
    row_idx: int
    label: str
    role: LineRole
    sign: int
    raw: list[str | None]  # per period column; None = no cell found
    values: list[Decimal | None]


@dataclass
class SumCheck:
    period_id: str
    expected: Decimal
    computed: Decimal
    tolerance: Decimal
    lines_summed: int
    passed: bool


@dataclass
class Draft:
    accession: str
    lines: list[DraftLine] = field(default_factory=list)
    periods: list[PeriodColumn] = field(default_factory=list)
    scale: UnitScale = UnitScale.UNKNOWN
    scale_quote: str = ""
    sum_checks: list[SumCheck] = field(default_factory=list)
    anchor_checks: list[dict[str, Any]] = field(default_factory=list)
    exceptions: list[str] = field(default_factory=list)
    direction: int = 1
    notes: list[str] = field(default_factory=list)


def to_decimal(raw: str) -> Decimal | None:
    if raw.strip() in DASHES:
        return None
    parsed = parse_raw_numeric(raw.strip())
    if parsed is None:
        return None
    d = Decimal(str(parsed))
    return d.quantize(Decimal(1)) if d == d.to_integral_value() else d.normalize()


def _decimals(raw: str) -> int:
    m = re.search(r"\.(\d+)", raw)
    return len(m.group(1)) if m else 0


def _cells_by_column(row: Row, columns: list[PeriodColumn]) -> list[HtmlCell | None]:
    out: list[HtmlCell | None] = []
    for col in columns:
        hits = [c for c in row.value_cells if _overlaps(_span(c), col.span)]
        out.append(hits[0] if len(hits) == 1 else None)
    return out


def tolerance(n_lines: int, unit: Decimal) -> Decimal:
    return max(1, math.ceil(n_lines / 2)) * unit


_NOT_GAAP_START = re.compile(r"^\s*(?:adjusted|non-gaap|pro forma)\b", re.IGNORECASE)


@dataclass
class Solution:
    direction: int
    roles: list[LineRole]  # one per body line
    running: list[Decimal]
    summed: list[int]
    passes: int


def solve(
    start: DraftLine,
    body: list[DraftLine | None],
    total: DraftLine,
    units: list[Decimal],
    direction: int,
) -> Solution:
    """
    Walk the bridge once for one direction. ``direction=+1`` means adjustments
    are added to the starting line (net income -> EBITDA); ``-1`` means the table
    shows items with income-statement signs and the bridge subtracts them.
    ``None`` in ``body`` is a heading row ("Adjustments:") that starts a new
    block. A row equal to the running sum, or to the sum of the current block
    (>= 2 rows), is a subtotal and is not summed.
    """
    n = len(units)
    running = [v or Decimal(0) for v in start.values]
    summed = [1 if v is not None else 0 for v in start.values]
    block = [Decimal(0)] * n
    block_count = 0
    roles: list[LineRole] = []

    def close_all(
        values: list[Decimal | None], targets: list[Decimal], k: list[int]
    ) -> bool:
        present = [(i, v) for i, v in enumerate(values) if v is not None]
        return bool(present) and all(
            abs(v - targets[i]) <= tolerance(k[i], units[i]) for i, v in present
        )

    for line in body:
        if line is None:
            block, block_count = [Decimal(0)] * n, 0
            continue
        if close_all(line.values, running, summed) or (
            block_count >= 2 and close_all(line.values, block, [block_count] * n)
        ):
            roles.append(LineRole.subtotal)
            block, block_count = [Decimal(0)] * n, 0
            continue
        roles.append(LineRole.adjustment)
        for i, v in enumerate(line.values):
            if v is None:
                continue
            c = direction * line.sign * v
            running[i] += c
            block[i] += c
            summed[i] += 1
        block_count += 1

    passes = sum(
        1
        for i, t in enumerate(total.values)
        if t is not None and abs(running[i] - t) <= tolerance(summed[i], units[i])
    )
    return Solution(direction, roles, running, summed, passes)


def extract_bridge(
    table: HtmlTable, metric_label: str, draft: Draft, fiscal_year_end: str = ""
) -> None:
    """
    Choose the starting line, direction and (at most one) inferred sign that make
    the bridge tie out, then record lines, roles and sum checks on ``draft``.

    Candidates for the starting line are every GAAP-start row above the total
    (excluding adjusted / non-GAAP / noncontrolling-interest rows); each is
    solved in both directions. If no candidate ties out in every period, a
    single-line sign flip is tried; one that makes every period tie out is
    applied and reported in ``draft.notes`` for owner review.
    """
    rows = build_rows(table)
    data = [r for r in rows if r.value_cells and r.label]
    total = _find_total(data, metric_label, draft)
    if total is None:
        return
    for r in data:
        # A starting label that wraps: "Net income attributable to Community
        # Health" / "Systems, Inc. stockholders" (values on the second row).
        joined = f"{r.wrapped_prefix} {r.label}".strip()
        if (
            r.wrapped_prefix
            and not GAAP_START.search(r.label)
            and GAAP_START.search(joined)
        ):
            r.label = joined
    starts = [
        r
        for r in data
        if r.idx < total.idx
        and GAAP_START.search(r.label)
        and not _NOT_GAAP_START.search(r.label)
        and not _NCI.search(r.label)
    ]
    if not starts:
        draft.exceptions.append("no GAAP starting line found")
        return

    attempts = [
        _attempt(table, rows, start, total, fiscal_year_end) for start in starts[:4]
    ]
    best = max(attempts, key=lambda a: (a.solution.passes, -a.order))
    draft.periods = best.periods
    draft.direction = best.solution.direction
    draft.exceptions.extend(best.exceptions)
    draft.notes.extend(best.notes)

    draft.lines.append(best.start)
    lines = [ln for ln in best.body if ln is not None]
    for line, role in zip(lines, best.solution.roles, strict=True):
        line.role = role
        if role is not LineRole.adjustment:
            line.sign = 1
        draft.lines.append(line)
    draft.lines.append(best.total)

    for i, col in enumerate(draft.periods):
        expected = best.total.values[i]
        if expected is None or col.period_id is None:
            continue
        tol = tolerance(best.solution.summed[i], best.units[i])
        computed = best.solution.running[i]
        ok = abs(computed - expected) <= tol
        draft.sum_checks.append(
            SumCheck(
                col.period_id, expected, computed, tol, best.solution.summed[i], ok
            )
        )
        if not ok:
            draft.exceptions.append(
                f"sum tie-out failed for {col.period_id}: lines sum to {computed}, "
                f"total is {expected} (tolerance {tol})"
            )


_NCI = re.compile(r"non-?controlling", re.IGNORECASE)


def _find_total(data: list[Row], metric_label: str, draft: Draft) -> Row | None:
    total = next((r for r in reversed(data) if r.label == metric_label), None)
    if total is None:
        candidates = [
            r
            for r in data
            if "ebitda" in r.label.lower() and not NOT_A_TOTAL.search(r.label)
        ]
        total = candidates[-1] if candidates else None
        if total is not None:
            draft.exceptions.append(
                f"headline label {metric_label!r} not found; used {total.label!r}"
            )
    if total is None:
        draft.exceptions.append("no EBITDA total found")
    return total


@dataclass
class Attempt:
    order: int
    periods: list[PeriodColumn]
    start: DraftLine
    body: list[DraftLine | None]
    total: DraftLine
    units: list[Decimal]
    solution: Solution
    exceptions: list[str]
    notes: list[str]


def _attempt(
    table: HtmlTable,
    rows: list[Row],
    start: Row,
    total: Row,
    fiscal_year_end: str,
) -> Attempt:
    exceptions: list[str] = []
    notes: list[str] = []
    periods = period_columns(table, start, fiscal_year_end)
    _fill_periods_from_table_header(table, start, periods)
    for col in periods:
        if col.period_id is None:
            exceptions.append(f"unresolved period header: {col.header!r}")
    units = [Decimal(1)] * len(periods)

    def line_from(row: Row, role: LineRole) -> DraftLine:
        cells = _cells_by_column(row, periods)
        raw = [c.text.strip() if c else None for c in cells]
        values = [to_decimal(r) if r is not None else None for r in raw]
        for i, r in enumerate(raw):
            if r is None:
                exceptions.append(f"row {row.label!r}: no value for column {i}")
            elif r not in DASHES and values[i] is None:
                exceptions.append(f"row {row.label!r}: unparseable value {r!r}")
            else:
                units[i] = min(units[i], Decimal(1).scaleb(-_decimals(r)))
        sign = -1 if SUBTRACT_DIRECTIVE.search(row.label) else 1
        return DraftLine(row.idx, row.label, role, sign, raw, values)

    first = line_from(start, LineRole.gaap_start)
    body: list[DraftLine | None] = []
    for row in rows:
        if row.idx <= start.idx or row.idx >= total.idx:
            continue
        if not row.value_cells:
            if row.label:
                body.append(None)
            continue
        body.append(line_from(row, LineRole.adjustment))
    last = line_from(total, LineRole.total)
    wanted = sum(1 for v in last.values if v is not None)

    best = max(
        (solve(first, body, last, units, d) for d in (1, -1)),
        key=lambda s: (s.passes, s.direction == 1),
    )
    if best.passes < wanted:
        repaired = _single_sign_repair(first, body, last, units, best.direction, wanted)
        if repaired is not None:
            flipped, solution = repaired
            notes.append(
                f"sign inferred by tie-out: {flipped.label!r} is deducted in every "
                "period although shown without a 'Less:' directive (confirm in P0-06)"
            )
            best = solution
    for item in body:
        if item is not None:
            item.sign = best.direction * item.sign
    return Attempt(
        order=start.idx,
        periods=periods,
        start=first,
        body=body,
        total=last,
        units=units,
        solution=best,
        exceptions=exceptions,
        notes=notes,
    )


def _single_sign_repair(
    start: DraftLine,
    body: list[DraftLine | None],
    total: DraftLine,
    units: list[Decimal],
    direction: int,
    wanted: int,
) -> tuple[DraftLine, Solution] | None:
    """The unique adjustment whose sign flip makes every period tie out, if any."""
    fixes: list[tuple[DraftLine, Solution]] = []
    for line in body:
        if line is None:
            continue
        line.sign = -line.sign
        solution = solve(start, body, total, units, direction)
        if solution.passes == wanted:
            fixes.append((line, solution))
        line.sign = -line.sign
    if len(fixes) != 1:
        return None
    line, solution = fixes[0]
    line.sign = -line.sign
    return line, solution


def _fill_periods_from_table_header(
    table: HtmlTable, start: Row, periods: list[PeriodColumn]
) -> None:
    """
    Fallback when column headers do not all resolve on their own: year-only cells
    ("2026") or full dates under period phrases ("Three Months Ended March 31,")
    whose HTML spans are misaligned with the value columns. A partial resolution
    is itself a sign of misalignment (a misaligned span can give a column the
    wrong phrase), so *every* column is reassigned: the k period-phrase cells of
    the header, left to right, go to the n columns in equal groups (n must be a
    multiple of k). Months come from the phrase; the end date from the column's
    own header when it is a full date, else the phrase's month/day plus the
    column's year. Nothing changes unless every column can be assigned; the
    anchor checks then validate the result.
    """
    if not periods or all(c.period_id is not None for c in periods):
        return
    phrase_cells = sorted(
        (
            c
            for c in table.cells
            if c.row_idx < start.idx
            and len(c.text.strip()) < 60
            and any(pat.search(c.text.lower()) for pat, _ in _MONTHS_BY_WORD)
        ),
        key=lambda c: (c.row_idx, c.col_idx),
    )
    k, n = len(phrase_cells), len(periods)
    if k == 0 or n % k:
        return
    group = n // k
    assigned: list[tuple[int, date, str]] = []
    for i, col in enumerate(periods):
        phrase = phrase_cells[i // group].text.strip()
        months = next(m for pat, m in _MONTHS_BY_WORD if pat.search(phrase.lower()))
        own_date = parse_period(col.header)[1]
        year = re.search(r"\b(20\d{2})\b", col.header)
        day = _MONTH_DAY.search(phrase)
        if own_date is not None:
            end: date | None = own_date
            label = f"{phrase} {own_date.isoformat()}"
        elif day is not None and year is not None:
            end = parse_period(f"{day.group(0)} {year.group(1)}")[1]
            label = f"{phrase} {year.group(1)}"
        else:
            return
        if end is None:
            return
        assigned.append((months, end, label))
    for col, (months, end, label) in zip(periods, assigned, strict=True):
        col.months, col.end_date = months, end
        col.header = f"{label} (assigned by column order)"


_MONTH_DAY = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+\d{1,2}\b"
)


# ---------------------------------------------------------------- scale


def detect_scale(
    table: HtmlTable, start_idx: int, preceding_text: str, draft: Draft
) -> None:
    header_text = " ".join(c.text for c in table.cells if c.row_idx < start_idx)
    for text in (header_text, preceding_text):
        res = detect_scale_from_caption(text)
        if res.scale is not UnitScale.UNKNOWN and not res.is_ambiguous:
            draft.scale = res.scale
            quote = _SCALE_QUOTE.search(text)
            draft.scale_quote = (
                re.sub(r"\s+", " ", quote.group(0)).strip() if quote else ""
            )
            return
    draft.exceptions.append("scale not found in table header or preceding text")


# ---------------------------------------------------------------- XBRL anchor


def anchor_concepts(label: str) -> list[str]:
    text = label.lower()
    if "available to" in text and "common" in text:
        return ["NetIncomeLossAvailableToCommonStockholdersBasic", "NetIncomeLoss"]
    if "attributable to" in text and "noncontrolling" not in text:
        return ["NetIncomeLoss"]
    if re.search(r"\bnet (?:\(loss\) )?(?:income|loss)\b", text):
        return ["ProfitLoss", "NetIncomeLoss"]
    if "operating" in text:
        return ["OperatingIncomeLoss"]
    if "before" in text:
        return [
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        ]
    return []


def _usd_facts(facts: dict[str, Any], concept: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = (
        facts.get("facts", {})
        .get("us-gaap", {})
        .get(concept, {})
        .get("units", {})
        .get("USD", [])
    )
    return [f for f in items if "start" in f and "end" in f]


def _duration_days(fact: dict[str, Any]) -> int:
    return (date.fromisoformat(fact["end"]) - date.fromisoformat(fact["start"])).days


def _fact_for(
    items: list[dict[str, Any]], end: date, months: int, end_tolerance_days: int
) -> dict[str, Any] | None:
    """Latest-filed fact of ``months`` duration ending within the tolerance of ``end``."""
    lo, hi = _DURATION_DAYS[months]
    hits = [
        f
        for f in items
        if abs((date.fromisoformat(f["end"]) - end).days) <= end_tolerance_days
        and lo <= _duration_days(f) <= hi
    ]
    return max(hits, key=lambda f: f.get("filed", "")) if hits else None


def derived_ltm(
    facts: dict[str, Any], concepts: list[str], end: date
) -> list[tuple[str, Decimal, list[dict[str, Any]]]]:
    """
    Trailing-twelve-month value ending ``end`` per concept, derived as
    FY + YTD - prior-year YTD. 52/53-week years are handled by matching the
    prior-year YTD end within a week of ``end`` minus 364 days.
    """
    out: list[tuple[str, Decimal, list[dict[str, Any]]]] = []
    for concept in concepts:
        items = _usd_facts(facts, concept)
        fiscal_years = [
            f
            for f in items
            if date.fromisoformat(f["end"]) < end
            and (end - date.fromisoformat(f["end"])).days <= 300
            and 350 <= _duration_days(f) <= 380
        ]
        if not fiscal_years:
            continue
        fy = max(fiscal_years, key=lambda f: (f["end"], f.get("filed", "")))
        months = round((end - date.fromisoformat(fy["end"])).days / 30.44)
        if months not in (3, 6, 9):
            continue
        ytd = _fact_for(items, end, months, 3)
        prior = _fact_for(items, end - timedelta(days=364), months, 7)
        if ytd is None or prior is None:
            continue
        value = (
            Decimal(str(fy["val"]))
            + Decimal(str(ytd["val"]))
            - Decimal(str(prior["val"]))
        )
        out.append((concept, value, [fy, ytd, prior]))
    return out


def anchor_check(
    facts: dict[str, Any],
    label: str,
    period: PeriodColumn,
    value: Decimal,
    multiplier: int,
    unit: Decimal,
) -> dict[str, Any]:
    """Match the starting line against XBRL facts for the same period."""
    assert period.end_date is not None and period.months is not None
    lo, hi = _DURATION_DAYS[period.months]
    found: list[dict[str, Any]] = []
    for concept in anchor_concepts(label):
        for fact in (
            facts.get("facts", {})
            .get("us-gaap", {})
            .get(concept, {})
            .get("units", {})
            .get("USD", [])
        ):
            if fact.get("end") != period.end_date.isoformat() or "start" not in fact:
                continue
            days = (
                date.fromisoformat(fact["end"]) - date.fromisoformat(fact["start"])
            ).days
            if not lo <= days <= hi:
                continue
            found.append({"concept": concept, **fact})
    base = {
        "period_id": period.period_id,
        "label": label,
        "concepts": anchor_concepts(label),
    }
    if not found and period.months == 12:
        # Trailing twelve months ending mid-year have no direct XBRL fact; derive
        # them as prior fiscal year + current YTD - prior-year YTD (same concept).
        derived_all = derived_ltm(facts, anchor_concepts(label), period.end_date)
        for concept, derived, parts in derived_all:
            scaled_value = derived / multiplier
            if abs(scaled_value - value) <= unit:
                return {
                    **base,
                    "status": "pass",
                    "concept": concept,
                    "xbrl_value": str(scaled_value),
                    "derived": "fiscal year + current YTD - prior-year YTD",
                    "accn": [p.get("accn") for p in parts],
                }
        if derived_all:
            concept, derived, parts = derived_all[0]
            return {
                **base,
                "status": "mismatch",
                "concept": concept,
                "xbrl_value": str(derived / multiplier),
                "derived": "fiscal year + current YTD - prior-year YTD",
                "accn": [p.get("accn") for p in parts],
            }
    if not found:
        return {**base, "status": "unavailable"}
    scaled = [(f, Decimal(str(f["val"])) / multiplier) for f in found]
    matches = [(f, s) for f, s in scaled if abs(s - value) <= unit]
    if matches:
        f, s = max(matches, key=lambda m: m[0].get("filed", ""))
        return {
            **base,
            "status": "pass",
            "concept": f["concept"],
            "xbrl_value": str(s),
            "accn": f.get("accn"),
            "form": f.get("form"),
            "filed": f.get("filed"),
        }
    nearest_f, nearest_s = min(scaled, key=lambda m: abs(m[1] - value))
    return {
        **base,
        "status": "mismatch",
        "concept": nearest_f["concept"],
        "xbrl_value": str(nearest_s),
        "accn": nearest_f.get("accn"),
    }


def run_anchor(draft: Draft, facts: dict[str, Any]) -> None:
    start = draft.lines[0] if draft.lines else None
    if start is None or draft.scale is UnitScale.UNKNOWN:
        return
    for i, col in enumerate(draft.periods):
        value = start.values[i] if i < len(start.values) else None
        if col.period_id is None or col.months not in _DURATION_DAYS or value is None:
            continue
        unit = Decimal(1)
        raw = start.raw[i]
        if raw:
            unit = Decimal(1).scaleb(-_decimals(raw))
        result = anchor_check(facts, start.label, col, value, int(draft.scale), unit)
        draft.anchor_checks.append(result)
        if result["status"] != "pass":
            draft.exceptions.append(
                f"GAAP anchor {result['status']} for {col.period_id}: "
                f"{start.label!r} = {value} vs XBRL {result.get('xbrl_value', 'n/a')}"
            )


# ---------------------------------------------------------------- output


def verified_periods(draft: Draft) -> set[str]:
    sums = {c.period_id for c in draft.sum_checks if c.passed}
    anchors = {a["period_id"] for a in draft.anchor_checks if a["status"] == "pass"}
    return sums & anchors


def release_payload(
    draft: Draft, entry: dict[str, Any], table_index: int, today: date
) -> dict[str, Any]:
    ok = verified_periods(draft)
    periods = [
        {
            "period_id": c.period_id,
            "label_raw": c.header,
            "end_date": c.end_date.isoformat() if c.end_date else None,
            "months": c.months,
        }
        for c in draft.periods
    ]
    lines = []
    for order, line in enumerate(draft.lines):
        values = []
        for col, raw, value in zip(draft.periods, line.raw, line.values, strict=True):
            values.append(
                {
                    "period_id": col.period_id,
                    "value_raw": raw,
                    "value": None if value is None else str(value),
                    "verified_by": "tieout" if col.period_id in ok else None,
                    "labeler": LABELER,
                    "labeled_on": today.isoformat(),
                }
            )
        lines.append(
            {
                "row_order": order,
                "label_raw": line.label,
                "role": line.role.value,
                "sign": line.sign,
                "values": values,
            }
        )
    total = next((ln for ln in draft.lines if ln.role is LineRole.total), None)
    return {
        "schema_version": 1,
        "ticker": entry["ticker"],
        "cik": entry["cik"],
        "accession": entry["accession"],
        "exhibit": entry["exhibit"],
        "source_url": entry["url"],
        "sha256": entry["sha256"],
        "metric_label_raw": total.label if total else None,
        "scale": _SCALE_TO_LABEL[draft.scale].value
        if draft.scale in _SCALE_TO_LABEL
        else None,
        "scale_quote": draft.scale_quote,
        "table": {"table_index": table_index, "caption_raw": None},
        "periods": periods,
        "lines": lines,
    }


def schema_problems(payload: dict[str, Any]) -> list[str]:
    """Validate the draft against P0-04, treating null verified_by as pending."""
    probe = json.loads(json.dumps(payload))
    for line in probe.get("lines", []):
        for v in line["values"]:
            v["verified_by"] = v["verified_by"] or "tieout"
    try:
        GoldRelease.model_validate(probe)
    except ValidationError as exc:
        return [
            f"schema: {e['msg']} at {'.'.join(str(p) for p in e['loc'])}"
            for e in exc.errors()
        ]
    return []


def draft_release(
    entry: dict[str, Any],
    issuer_release: dict[str, Any],
    html: bytes,
    facts: dict[str, Any] | None,
    fiscal_year_end: str | None = None,
) -> tuple[dict[str, Any], Draft]:
    soup = BeautifulSoup(html, "lxml")
    table_index = int(issuer_release["table_index"])
    tables = {t.index: t for t in extract_html_tables(soup)}
    draft = Draft(accession=entry["accession"])
    table = tables.get(table_index)
    if table is None:
        draft.exceptions.append(f"table {table_index} not found")
        return {"exceptions": draft.exceptions}, draft

    extract_bridge(table, issuer_release["metric_label"], draft, fiscal_year_end or "")
    if draft.lines:
        tag = soup.find_all("table")[table_index]
        preceding = " ".join(
            s.strip()
            for s in list(tag.find_all_previous(string=True, limit=40))
            if s.strip()
        )
        detect_scale(table, draft.lines[0].row_idx, preceding, draft)
    if facts is not None:
        run_anchor(draft, facts)
    else:
        draft.exceptions.append("XBRL company facts unavailable")

    payload = release_payload(draft, entry, table_index, datetime.now(UTC).date())
    problems = schema_problems(payload)
    if problems:
        draft.exceptions.append(
            f"schema: {len(problems)} problem(s), first: {problems[0]}"
        )
    out = {
        "ticket": "P0-05",
        "generated_by": "tools.gold.draft",
        "generated_on": datetime.now(UTC).date().isoformat(),
        "status": "ok" if not draft.exceptions else "exceptions",
        "release": payload,
        "checks": {
            "direction": draft.direction,
            "sum": [
                {
                    "period_id": c.period_id,
                    "expected": str(c.expected),
                    "computed": str(c.computed),
                    "tolerance": str(c.tolerance),
                    "lines_summed": c.lines_summed,
                    "passed": c.passed,
                }
                for c in draft.sum_checks
            ],
            "anchor": draft.anchor_checks,
        },
        "exceptions": draft.exceptions,
        "notes": draft.notes,
    }
    return out, draft


def _issuer_releases(issuers: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for issuer in issuers["selected"]:
        for rel in issuer["releases"]:
            out[rel["accession"]] = {
                **rel,
                "fiscal_year_end": issuer.get("fiscal_year_end"),
            }
    return out


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-xbrl", action="store_true", help="skip the GAAP anchor fetch"
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    manifest = yaml.safe_load(
        (GOLD_DIR / "raw" / "manifest.yaml").read_text(encoding="utf-8")
    )
    issuers = _issuer_releases(
        yaml.safe_load((GOLD_DIR / "issuers.yaml").read_text(encoding="utf-8"))
    )
    client = None if args.no_xbrl else EdgarClient()
    facts_by_cik: dict[str, dict[str, Any]] = {}
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    clean = 0
    for entry in manifest["releases"]:
        html = gzip.decompress((GOLD_DIR / "raw" / entry["path"]).read_bytes())
        facts = None
        if client is not None:
            if entry["cik"] not in facts_by_cik:
                facts_by_cik[entry["cik"]] = client.get_company_facts(entry["cik"])
            facts = facts_by_cik[entry["cik"]]
        issuer_release = issuers[entry["accession"]]
        out, draft = draft_release(
            entry, issuer_release, html, facts, issuer_release["fiscal_year_end"]
        )
        (DRAFTS_DIR / f"{entry['accession']}.json").write_text(
            json.dumps(out, indent=2) + "\n", encoding="utf-8"
        )
        sums = sum(c.passed for c in draft.sum_checks)
        anchors = sum(a["status"] == "pass" for a in draft.anchor_checks)
        clean += not draft.exceptions
        print(
            f"{entry['ticker']:5} {entry['accession']} periods={len(draft.periods)} "
            f"lines={len(draft.lines)} sum={sums}/{len(draft.sum_checks)} "
            f"anchor={anchors}/{len(draft.anchor_checks)} exceptions={len(draft.exceptions)}"
        )
    print(f"{clean}/{len(manifest['releases'])} releases with no exceptions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
