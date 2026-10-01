"""
Unit tests for Unit Scale and Sign Normalization (FN-013).
"""


from app.extraction.scale_and_sign import (
    UnitScale,
    detect_scale_from_caption,
    detect_sign,
    format_workbook_units_header,
    is_per_share_or_percentage,
    normalize_line_item,
)


def test_detect_scale_thousands_captions() -> None:
    """FN-013: Detects thousands scale from various standard SEC filing captions."""
    captions = [
        "Consolidated Statements of Operations (in thousands)",
        "(in thousands, except per share data)",
        "Reconciliation of Non-GAAP Financial Measures ($ in thousands)",
        "Adjusted EBITDA Reconciliation (thousands of dollars)",
    ]
    for cap in captions:
        res = detect_scale_from_caption(cap)
        assert res.scale == UnitScale.THOUSANDS
        assert res.multiplier == 1000
        assert not res.is_ambiguous


def test_detect_scale_millions_captions() -> None:
    """FN-013: Detects millions scale from various standard SEC filing captions."""
    captions = [
        "Non-GAAP Reconciliations (in millions)",
        "(in millions, except per share amounts)",
        "Adjusted EBITDA ($ in millions)",
        "Segment Operating Income (millions of dollars)",
    ]
    for cap in captions:
        res = detect_scale_from_caption(cap)
        assert res.scale == UnitScale.MILLIONS
        assert res.multiplier == 1_000_000
        assert not res.is_ambiguous


def test_detect_scale_ambiguity_flags_never_guesses() -> None:
    """FN-013 / I3: Ambiguity creates an explicit flag rather than guessing."""
    # Conflicting scale indicators
    conflicting = "Table 1 (in thousands, except foreign segments in millions)"
    res = detect_scale_from_caption(conflicting)
    assert res.is_ambiguous is True
    assert "Conflicting scale indicators" in (res.flag_reason or "")

    # Missing caption
    empty_res = detect_scale_from_caption(None)
    assert empty_res.is_ambiguous is True
    assert empty_res.scale == UnitScale.UNKNOWN


def test_detect_scale_magnitude_cross_check() -> None:
    """FN-013: Magnitude cross-check detects anomalous numbers for declared scale."""
    # Caption says millions, but values are raw trillions e.g. 50,000,000 in millions
    res = detect_scale_from_caption(
        "(in millions)",
        sample_values=[50_000_000.0, 20_000_000.0],
    )
    assert res.is_ambiguous is True
    assert "Magnitude warning" in (res.flag_reason or "")


def test_detect_sign_parentheses_and_prefixes() -> None:
    """FN-013: Sign detection from accounting parentheses, minus signs, and label directives."""
    # Parentheses negatives
    sign, is_paren = detect_sign("(1,234.50)", "Net Loss")
    assert sign == -1
    assert is_paren is True

    # Leading minus
    sign, is_paren = detect_sign("-500", "Net Interest")
    assert sign == -1
    assert is_paren is False

    # Label with "Less: ..."
    sign, _ = detect_sign("1,200", "Less: Income tax benefit")
    assert sign == -1

    # Label with "Deduct: ..."
    sign, _ = detect_sign("350", "Deduct: Non-operating gains")
    assert sign == -1

    # Standard addition
    sign, _ = detect_sign("8,000", "Depreciation and amortization")
    assert sign == 1

    # "Add / (deduct)" directive
    sign, _ = detect_sign("400", "Add / (deduct) Other income")
    assert sign == 1

    sign, _ = detect_sign("(400)", "Add / (deduct) Other income")
    assert sign == -1


def test_per_share_and_percentage_exemptions() -> None:
    """FN-013: Per-share and percentage rows are exempt from table scale multipliers."""
    assert is_per_share_or_percentage("Diluted net income per share", "1.24") is True
    assert is_per_share_or_percentage("Adjusted EPS", "2.10") is True
    assert is_per_share_or_percentage("Operating Margin", "18.5%") is True
    assert is_per_share_or_percentage("Stock-based compensation", "50,000") is False


def test_normalize_line_item_scale_and_sign() -> None:
    """FN-013: Normalization produces exact numeric value while preserving as-reported string."""
    # Standard add-back in thousands
    item1 = normalize_line_item(
        raw_value="15,000",
        label="Stock-based compensation",
        table_scale=UnitScale.THOUSANDS,
    )
    assert item1.as_reported_raw == "15,000"
    assert item1.as_reported_numeric == 15000.0
    assert item1.normalized_numeric_value == 15_000_000.0  # 15,000 * 1,000
    assert item1.sign == 1
    assert item1.is_exempt_from_scale is False

    # Parentheses negative in millions
    item2 = normalize_line_item(
        raw_value="(1,200)",
        label="Interest expense / (income)",
        table_scale=UnitScale.MILLIONS,
    )
    assert item2.as_reported_raw == "(1,200)"
    assert item2.as_reported_numeric == -1200.0
    assert item2.normalized_numeric_value == -1_200_000_000.0
    assert item2.sign == -1

    # Per-share item in a millions table: must remain unscaled
    eps_item = normalize_line_item(
        raw_value="2.45",
        label="Adjusted diluted EPS",
        table_scale=UnitScale.MILLIONS,
    )
    assert eps_item.as_reported_raw == "2.45"
    assert eps_item.as_reported_numeric == 2.45
    assert eps_item.normalized_numeric_value == 2.45
    assert eps_item.is_exempt_from_scale is True


def test_mixed_scale_tables() -> None:
    """FN-013: Mixed scale tables correctly scale dollar rows while leaving share/percent rows intact."""
    table_rows = [
        ("GAAP Net Income", "50,000", UnitScale.THOUSANDS, False, 50_000_000.0),
        ("Diluted EPS", "1.25", UnitScale.THOUSANDS, True, 1.25),
        ("Effective Tax Rate", "21%", UnitScale.THOUSANDS, True, 21.0),
        ("Adjusted EBITDA", "75,000", UnitScale.THOUSANDS, False, 75_000_000.0),
    ]

    for label, raw_val, scale, expected_exempt, expected_normalized in table_rows:
        res = normalize_line_item(raw_val, label, table_scale=scale)
        assert res.is_exempt_from_scale == expected_exempt
        assert res.normalized_numeric_value == expected_normalized


def test_format_workbook_units_header() -> None:
    """FN-013: Workbook units header format helper."""
    assert format_workbook_units_header(UnitScale.THOUSANDS) == "Amounts in thousands (except per-share amounts)"
    assert format_workbook_units_header(UnitScale.MILLIONS) == "Amounts in millions (except per-share amounts)"
    assert format_workbook_units_header(UnitScale.UNITS) == "Amounts in dollars"
