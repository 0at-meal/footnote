"""Deterministic category suggestions (spec v0.1 §4). Labels are generic examples."""

import pytest
from app.analytics.classify import suggest


@pytest.mark.parametrize(
    ("label", "code"),
    [
        ("depreciation and amortization", "DA"),
        ("interest expense, net", "INT"),
        ("interest income", "INT"),
        ("provision for income taxes", "TAX"),
        ("net income attributable to noncontrolling interests", "NCI"),
        ("stock-based compensation expense", "SBC"),
        ("severance", "RESTR"),
        ("goodwill impairment", "IMPAIR"),
        ("transaction and separation costs", "MA"),
        ("litigation and investigation costs", "LITIG"),
        ("loss on extinguishment of debt", "DEBT"),
        ("loss on debt financing transactions", "DEBT"),
        ("gain on sales of assets and businesses, net", "DIVEST"),
        ("pre-opening expenses", "PREOPEN"),
        ("warrant revenue", "REV"),
        ("other, net", "OTHER_NR"),
        ("vehicle debt-related charges", "OTHER"),
    ],
)
def test_single_codes(label: str, code: str) -> None:
    assert suggest(label).code == code


def test_mixed_line_keeps_constituents() -> None:
    s = suggest("impairment and restructuring charges, and acquisition-related costs")
    assert s.code == "MIXED"
    assert set(s.components) == {"IMPAIR", "RESTR", "MA"}
    assert "mixed" in s.flags


def test_residual_other_and_netted_flags() -> None:
    assert "residual_other" in suggest("restructuring and other related charges").flags
    s = suggest("litigation and other matters, net of insurance recoveries")
    assert s.code == "LITIG"
    assert {"netted", "residual_other"} <= set(s.flags)


def test_excluding_parenthetical_is_ignored() -> None:
    s = suggest(
        "acquisition-related costs (excluding amortization of intangible assets)"
    )
    assert s.code == "MA"
