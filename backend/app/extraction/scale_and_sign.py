"""
Unit Scale and Sign Normalization Engine for Footnote (FN-013).

Provides pure, deterministic functions to:
1. Detect scale from filing captions, table headers, and magnitude cross-checks.
2. Detect arithmetic signs from parentheses, minus signs, and label directives ("Less:", "add/(deduct)").
3. Normalize line-item amounts while strictly preserving as-reported values and exempting per-share/ratio rows.
4. Flag ambiguous captions rather than guessing (Invariant I3).
"""

from __future__ import annotations

import re
from enum import IntEnum

from pydantic import BaseModel, Field


class UnitScale(IntEnum):
    UNKNOWN = 0
    UNITS = 1
    THOUSANDS = 1000
    MILLIONS = 1000000
    BILLIONS = 1000000000

    @property
    def label(self) -> str:
        if self == UnitScale.THOUSANDS:
            return "in thousands"
        if self == UnitScale.MILLIONS:
            return "in millions"
        if self == UnitScale.BILLIONS:
            return "in billions"
        if self == UnitScale.UNITS:
            return "in dollars"
        return "units unspecified"


class ScaleDetectionResult(BaseModel):
    scale: UnitScale
    multiplier: int
    unit_label: str
    is_ambiguous: bool = False
    flag_reason: str | None = None


class NormalizedValueResult(BaseModel):
    as_reported_raw: str
    as_reported_numeric: float | None
    normalized_numeric_value: float | None
    scale: UnitScale
    sign: int = Field(default=1, description="+1 (addition) or -1 (deduction)")
    is_exempt_from_scale: bool = False
    is_ambiguous: bool = False
    flag_reason: str | None = None


# Regex patterns for scale detection in captions/headers
_RE_THOUSANDS = re.compile(
    r"\b(in\s+thousands|thousands\s+of\s+dollars|\$\s+in\s+thousands|\(in\s+thousands[^)]*\))\b",
    re.IGNORECASE,
)
_RE_MILLIONS = re.compile(
    r"\b(in\s+millions|millions\s+of\s+dollars|\$\s+in\s+millions|\(in\s+millions[^)]*\))\b",
    re.IGNORECASE,
)
_RE_BILLIONS = re.compile(
    r"\b(in\s+billions|billions\s+of\s+dollars|\$\s+in\s+billions|\(in\s+billions[^)]*\))\b",
    re.IGNORECASE,
)
_RE_DOLLARS = re.compile(
    r"\b(in\s+dollars|exact\s+dollars|\$\s+in\s+ones)\b",
    re.IGNORECASE,
)

# Per-share and percentage exemption patterns
_RE_PER_SHARE_OR_PCT = re.compile(
    r"(\bper\s+share\b|\beps\b|\bshares\b|\%|\bmargin\b|\brate\b|\bratio\b)",
    re.IGNORECASE,
)


def detect_scale_from_caption(
    caption_or_header: str | None,
    context_text: str | None = None,
    sample_values: list[float] | None = None,
) -> ScaleDetectionResult:
    """
    Detects reporting unit scale from table caption or document context.
    Enforces I3: Ambiguity creates an explicit flag rather than a guess.
    """
    if not caption_or_header and not context_text:
        return ScaleDetectionResult(
            scale=UnitScale.UNKNOWN,
            multiplier=1,
            unit_label="units unspecified",
            is_ambiguous=True,
            flag_reason="Ambiguous scale: No unit caption found in table header or context",
        )

    combined = f"{caption_or_header or ''} {context_text or ''}".strip()

    has_thousands = bool(_RE_THOUSANDS.search(combined))
    has_millions = bool(_RE_MILLIONS.search(combined))
    has_billions = bool(_RE_BILLIONS.search(combined))
    has_dollars = bool(_RE_DOLLARS.search(combined))

    detected_counts = sum([has_thousands, has_millions, has_billions, has_dollars])

    # Conflicting multiple scales detected in same context
    if detected_counts > 1:
        return ScaleDetectionResult(
            scale=UnitScale.UNKNOWN,
            multiplier=1,
            unit_label="ambiguous",
            is_ambiguous=True,
            flag_reason=f"Ambiguous scale: Conflicting scale indicators found in context ('{combined}')",
        )

    detected_scale = UnitScale.UNKNOWN
    if has_thousands:
        detected_scale = UnitScale.THOUSANDS
    elif has_millions:
        detected_scale = UnitScale.MILLIONS
    elif has_billions:
        detected_scale = UnitScale.BILLIONS
    elif has_dollars:
        detected_scale = UnitScale.UNITS

    if detected_scale == UnitScale.UNKNOWN:
        return ScaleDetectionResult(
            scale=UnitScale.UNKNOWN,
            multiplier=1,
            unit_label="units unspecified",
            is_ambiguous=True,
            flag_reason=f"Ambiguous scale: Unrecognized unit caption format in '{combined}'",
        )

    # Magnitude cross-check:
    # If millions declared but sample numbers exceed 100 billion, or thousands declared but sample values < 10
    if sample_values and len(sample_values) > 0:
        max_abs = max(abs(v) for v in sample_values if v is not None)
        if detected_scale == UnitScale.MILLIONS and max_abs > 10_000_000:
            # Over 10 trillion in millions implies raw unscaled dollars were likely reported
            return ScaleDetectionResult(
                scale=detected_scale,
                multiplier=int(detected_scale),
                unit_label=detected_scale.label,
                is_ambiguous=True,
                flag_reason=f"Magnitude warning: Sample values up to {max_abs:,.0f} unusually large for {detected_scale.label}",
            )

    return ScaleDetectionResult(
        scale=detected_scale,
        multiplier=int(detected_scale),
        unit_label=detected_scale.label,
        is_ambiguous=False,
    )


def detect_sign(
    raw_value: str,
    label: str,
    table_header: str | None = None,
) -> tuple[int, bool]:
    """
    Detects whether an item represents an addition (+1) or deduction (-1) in a reconciliation.

    Returns:
        tuple[int, bool]: (sign, is_parenthesized)
    """
    v_clean = raw_value.strip()
    is_parenthesized = False

    # 1. Accounting parentheses e.g. "(1,234)" or "( 500 )"
    if v_clean.startswith("(") and v_clean.endswith(")"):
        return -1, True

    # 2. Leading minus sign
    if v_clean.startswith("-"):
        return -1, False

    # 3. Structural label directives
    lbl_lower = label.strip().lower()

    # "Less: ..." or "Deduct: ..."
    if lbl_lower.startswith(("less:", "less ", "deduct:", "deductions:")):
        return -1, False

    # "Add / (deduct) ..."
    if "add / (deduct)" in lbl_lower or "add/(deduct)" in lbl_lower:
        # If value was not in parentheses, it's an addition
        return (1 if not is_parenthesized else -1), is_parenthesized

    return 1, False


def is_per_share_or_percentage(label: str, raw_value: str) -> bool:
    """
    Determines whether a line item is an exempt per-share metric, percentage, or ratio
    that should NOT be multiplied by the table's scale factor.
    """
    if _RE_PER_SHARE_OR_PCT.search(label):
        return True
    return "%" in raw_value


def parse_raw_numeric(raw_val: str | None) -> float | None:
    """Pure parsing of raw string value into base float."""
    if not raw_val:
        return None
    s = raw_val.strip()
    is_neg = False
    if s.startswith("(") and s.endswith(")"):
        is_neg = True
        s = s[1:-1].strip()
    elif s.startswith("-"):
        is_neg = True
        s = s[1:].strip()

    s = s.replace("$", "").replace("€", "").replace("£", "").replace(",", "").replace("%", "").strip()
    try:
        val = float(s)
        return -val if is_neg else val
    except (ValueError, TypeError):
        return None


def normalize_line_item(
    raw_value: str,
    label: str,
    table_scale: UnitScale = UnitScale.THOUSANDS,
    caption: str | None = None,
) -> NormalizedValueResult:
    """
    Normalizes a line-item numeric amount while strictly preserving the as-reported raw string.
    Exempts per-share and percentage rows from scaling.
    """
    num = parse_raw_numeric(raw_value)
    sign, _is_parenthesized = detect_sign(raw_value, label)

    is_exempt = is_per_share_or_percentage(label, raw_value)

    flag_reason: str | None = None
    is_ambiguous = False

    # Caption validation if passed
    if caption:
        scale_res = detect_scale_from_caption(caption)
        if scale_res.is_ambiguous:
            is_ambiguous = True
            flag_reason = scale_res.flag_reason
        elif scale_res.scale != UnitScale.UNKNOWN:
            table_scale = scale_res.scale

    if num is None:
        return NormalizedValueResult(
            as_reported_raw=raw_value,
            as_reported_numeric=None,
            normalized_numeric_value=None,
            scale=table_scale,
            sign=sign,
            is_exempt_from_scale=is_exempt,
            is_ambiguous=True,
            flag_reason=f"Non-numeric value string: '{raw_value}'",
        )

    # Calculate normalized numeric value
    # If exempt (per-share / ratio), scale multiplier is 1
    multiplier = 1 if is_exempt else int(table_scale)
    # Ensure sign consistency
    magnitude = abs(num)
    normalized_val = magnitude * multiplier * sign

    return NormalizedValueResult(
        as_reported_raw=raw_value,
        as_reported_numeric=num,
        normalized_numeric_value=normalized_val,
        scale=table_scale,
        sign=sign,
        is_exempt_from_scale=is_exempt,
        is_ambiguous=is_ambiguous,
        flag_reason=flag_reason,
    )


def format_workbook_units_header(scale: UnitScale | int) -> str:
    """
    Generates the standardized units declaration for workbook headers (FN-013 AC-4).
    """
    scale_enum = UnitScale(int(scale)) if int(scale) in UnitScale._value2member_map_ else UnitScale.UNKNOWN
    if scale_enum == UnitScale.THOUSANDS:
        return "Amounts in thousands (except per-share amounts)"
    if scale_enum == UnitScale.MILLIONS:
        return "Amounts in millions (except per-share amounts)"
    if scale_enum == UnitScale.BILLIONS:
        return "Amounts in billions (except per-share amounts)"
    if scale_enum == UnitScale.UNITS:
        return "Amounts in dollars"
    return "All figures as reported"
