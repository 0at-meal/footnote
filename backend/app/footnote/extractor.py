"""
Debt Schedule Footnote Extractor (Feature 8, Step E).

Pure deterministic parser for SEC Note 8 (Debt Schedule and Credit Facilities).
Extracts tranches, principal amounts, interest rates, maturities, and seniority.

Adheres to:
- CONSTITUTION §1.1: mypy --strict compliance.
- CONSTITUTION §1.2: Pure arithmetic and regex parsing; no numeric hallucinations.
- CONSTITUTION §2.3: Preserves source PDF coordinates and page provenance.
"""

import hashlib
import re
from collections.abc import Sequence

from app.extraction.models import ExtractedRecord, ScoredRecord
from app.footnote.models import (
    DebtSchedule,
    DebtTranche,
    LeaseCommitmentYear,
    LeaseSchedule,
)

_FIXED_RATE_REGEX = re.compile(r"(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)
_FLOATING_RATE_REGEX = re.compile(
    r"(SOFR|LIBOR|EURIBOR|PRIME|BSBY)\s*(?:\+|\-)\s*(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_MATURITY_YEAR_REGEX = re.compile(
    r"(?:due|matur\w*|expir\w*)?\s*(?:(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+)?\b(20[2-9]\d)\b",
    re.IGNORECASE,
)
_DEBT_TABLE_REGEX = re.compile(
    r"(note\s+(?:8|\d+)[.:\s-]*)?(debt|credit\s+facilities|financing\s+arrangements|long-term\s+debt|borrowings|senior\s+notes|notes\s+payable|debt\s+obligations|outstanding\s+debt)",
    re.IGNORECASE,
)
_TOTAL_DEBT_LABEL_REGEX = re.compile(
    r"\b(total\s+(?:long-term\s+)?debt|total\s+borrowings|total\s+notes|total\s+credit\s+facilities|total\s+debt\s+obligations|total\s+carrying\s+value)\b",
    re.IGNORECASE,
)
_LEASE_TABLE_REGEX = re.compile(
    r"(note\s+(?:12|\d+)[.:\s-]*)?(lease|leases|undiscounted\s+lease\s+liabilities|future\s+minimum\s+lease\s+payments|maturity\s+of\s+lease\s+liabilities|lease\s+commitments)",
    re.IGNORECASE,
)
_DISCOUNT_RATE_REGEX = re.compile(
    r"(?:weighted[\s-]average\s+discount\s+rate|discount\s+rate)",
    re.IGNORECASE,
)
_YEAR_ROW_REGEX = re.compile(
    r"\b(20[2-9]\d|thereafter|after\s+20[2-9]\d)\b",
    re.IGNORECASE,
)
_TOTAL_LEASE_ROW_REGEX = re.compile(
    r"\b(total\s+(?:undiscounted\s+)?lease\s+(?:payments|commitments|liabilities)|total\s+future\s+minimum\s+lease\s+payments)\b",
    re.IGNORECASE,
)


def parse_rate_from_text(
    text: str,
) -> tuple[float | None, str, bool, float | None, str | None]:
    """
    Parse coupon rate, floating spread, and benchmark from text.

    Returns:
        (interest_rate, rate_text, is_floating, spread, benchmark)
    """
    clean = text.strip()
    if not clean:
        return None, "", False, None, None

    # Check floating rate first (e.g. SOFR + 2.50%)
    float_match = _FLOATING_RATE_REGEX.search(clean)
    if float_match:
        benchmark = float_match.group(1).upper()
        spread_val = float(float_match.group(2))
        return None, clean, True, spread_val, benchmark

    # Check fixed rate (e.g. 5.250%)
    fixed_match = _FIXED_RATE_REGEX.search(clean)
    if fixed_match:
        rate_val = float(fixed_match.group(1))
        return rate_val, f"{rate_val:.3f}%", False, None, None

    return None, clean, False, None, None


def parse_maturity_from_text(text: str) -> int | None:
    """
    Extract 4-digit maturity year (2020-2099) from label or text.
    """
    match = _MATURITY_YEAR_REGEX.search(text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def parse_principal_amount(value_str: str) -> tuple[float | None, str]:
    """
    Parse numeric monetary principal amount from string.
    """
    cleaned = value_str.strip().replace("$", "").replace(",", "").replace(" ", "")
    if not cleaned:
        return None, value_str

    # Handle negative / parentheses e.g. (100.0)
    is_negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        is_negative = True
        cleaned = cleaned[1:-1]
    elif cleaned.startswith("-"):
        is_negative = True
        cleaned = cleaned[1:]

    try:
        val = float(cleaned)
        if is_negative:
            val = -val
        return val, value_str.strip()
    except ValueError:
        return None, value_str.strip()


def determine_seniority(text: str) -> str:
    """
    Classify seniority / security hierarchy from instrument name text.
    """
    t_lower = text.lower()
    if "subordinated" in t_lower or "junior" in t_lower:
        return "Subordinated"
    if "secured" in t_lower or "term loan" in t_lower or "credit facility" in t_lower:
        return "Senior Secured"
    if "senior" in t_lower or "notes" in t_lower or "debentures" in t_lower:
        return "Senior"
    return "Senior"


def extract_debt_tranches(
    records: Sequence[ScoredRecord | ExtractedRecord],
) -> list[DebtTranche]:
    """
    Extract debt instrument tranches from debt footnote records.
    """
    tranches: list[DebtTranche] = []

    for r in records:
        rec = r.record if isinstance(r, ScoredRecord) else r
        table_name = getattr(r, "table_name", None) or ""
        footnote_type = getattr(r, "footnote_type", None) or getattr(
            rec, "footnote_type", None
        )

        is_debt = (
            footnote_type == "debt"
            or bool(_DEBT_TABLE_REGEX.search(table_name))
            or bool(_DEBT_TABLE_REGEX.search(rec.label))
        )
        if not is_debt:
            continue

        # Suppress summary/total lines from individual tranches
        if _TOTAL_DEBT_LABEL_REGEX.search(rec.label):
            continue

        principal_val, principal_txt = parse_principal_amount(rec.value)
        if principal_val is None or principal_val <= 0:
            continue

        rate_val, rate_txt, is_floating, spread, benchmark = parse_rate_from_text(
            rec.label
        )
        maturity_yr = parse_maturity_from_text(rec.label)
        seniority = determine_seniority(rec.label)

        # Deterministic ID based on instrument name and page
        id_hash = hashlib.sha256(
            f"{rec.label}:{rec.page}:{rec.value}".encode()
        ).hexdigest()[:12]

        tranche = DebtTranche(
            id=f"debt-{id_hash}",
            instrument_name=rec.label,
            principal_amount=principal_val,
            principal_text=principal_txt,
            interest_rate=rate_val,
            rate_text=rate_txt,
            maturity_year=maturity_yr,
            senior_subordinated=seniority,
            is_floating=is_floating,
            spread=spread,
            benchmark=benchmark,
            page=rec.page,
            bbox=rec.bbox,
        )
        tranches.append(tranche)

    return tranches


def compile_debt_schedule(
    job_id: str,
    records: Sequence[ScoredRecord | ExtractedRecord],
    company_id: str | None = None,
    filing_year: int | None = None,
) -> DebtSchedule:
    """
    Compile a complete DebtSchedule model from extracted records.
    """
    tranches = extract_debt_tranches(records)

    total_debt: float | None = None
    weighted_avg_rate: float | None = None

    valid_principals = [
        t.principal_amount for t in tranches if t.principal_amount is not None
    ]
    if valid_principals:
        total_debt = round(sum(valid_principals), 2)

    # Compute weighted average rate: sum(rate * principal) / sum(principal)
    rated_tranches = [
        t
        for t in tranches
        if t.interest_rate is not None and t.principal_amount is not None
    ]
    if rated_tranches:
        rated_principal_sum = sum(
            t.principal_amount for t in rated_tranches if t.principal_amount is not None
        )
        if rated_principal_sum > 0:
            rate_weight_sum = sum(
                (t.interest_rate or 0.0) * (t.principal_amount or 0.0)
                for t in rated_tranches
            )
            weighted_avg_rate = round(rate_weight_sum / rated_principal_sum, 3)

    return DebtSchedule(
        job_id=job_id,
        company_id=company_id,
        filing_year=filing_year,
        footnote_title="Note 8. Debt and Credit Facilities",
        tranches=tranches,
        total_debt=total_debt,
        weighted_avg_rate=weighted_avg_rate,
        is_confirmed=False,
    )


def extract_lease_schedule(
    records: Sequence[ScoredRecord | ExtractedRecord],
    job_id: str,
    company_id: str | None = None,
    filing_year: int | None = None,
) -> LeaseSchedule | None:
    """
    Extract ASC 842 lease commitment waterfall and discount rates.
    """
    year_map: dict[str, LeaseCommitmentYear] = {}
    operating_discount_rate: float | None = None
    finance_discount_rate: float | None = None
    has_any_lease_data = False

    for r in records:
        rec = r.record if isinstance(r, ScoredRecord) else r
        table_name = getattr(r, "table_name", None) or ""
        footnote_type = getattr(r, "footnote_type", None) or getattr(
            rec, "footnote_type", None
        )

        is_lease = (
            footnote_type == "lease"
            or bool(_LEASE_TABLE_REGEX.search(table_name))
            or bool(_LEASE_TABLE_REGEX.search(rec.label))
        )
        if not is_lease:
            continue

        has_any_lease_data = True
        label_lower = rec.label.lower()

        # Check discount rate row
        if _DISCOUNT_RATE_REGEX.search(label_lower):
            rate_val, _, _, _, _ = parse_rate_from_text(rec.value)
            if rate_val is None:
                amt, _ = parse_principal_amount(rec.value)
                if amt is not None:
                    rate_val = amt
            if rate_val is not None:
                if "finance" in label_lower:
                    finance_discount_rate = rate_val
                else:
                    operating_discount_rate = rate_val
            continue

        # Suppress total lines from individual year waterfall rows
        if _TOTAL_LEASE_ROW_REGEX.search(label_lower):
            continue

        # Match year / commitment row
        year_match = _YEAR_ROW_REGEX.search(rec.label)
        if year_match:
            year_label = year_match.group(1).title()
            amt, _ = parse_principal_amount(rec.value)
            if amt is None:
                continue

            if year_label not in year_map:
                year_map[year_label] = LeaseCommitmentYear(
                    year_label=year_label,
                    page=rec.page,
                    bbox=rec.bbox,
                )

            entry = year_map[year_label]
            if "finance" in label_lower:
                entry.finance_amount = amt
            else:
                entry.operating_amount = amt

            # Recompute total
            op = entry.operating_amount or 0.0
            fin = entry.finance_amount or 0.0
            entry.total_amount = round(op + fin, 2)

    if not has_any_lease_data or not year_map:
        return None

    # Sort years: 2025, 2026, 2027... Thereafter at the end
    def _year_sort_key(y: str) -> tuple[int, str]:
        if y.lower().startswith("there") or y.lower().startswith("after"):
            return (9999, y)
        try:
            return (int(y), y)
        except ValueError:
            return (9000, y)

    sorted_years = sorted(year_map.keys(), key=_year_sort_key)
    years_list = [year_map[y] for y in sorted_years]

    op_total_vals = [
        y.operating_amount for y in years_list if y.operating_amount is not None
    ]
    fin_total_vals = [
        y.finance_amount for y in years_list if y.finance_amount is not None
    ]

    operating_total = round(sum(op_total_vals), 2) if op_total_vals else None
    finance_total = round(sum(fin_total_vals), 2) if fin_total_vals else None

    return LeaseSchedule(
        job_id=job_id,
        company_id=company_id,
        filing_year=filing_year,
        footnote_title="Note 12. Leases (ASC 842)",
        years=years_list,
        operating_total=operating_total,
        finance_total=finance_total,
        operating_discount_rate=operating_discount_rate,
        finance_discount_rate=finance_discount_rate,
        is_confirmed=False,
    )
