"""
Tests for the A-11 answer schema, provenance gate and renderer. Values are
synthetic fixtures held in memory; none describe a filing.
"""

from decimal import Decimal
from typing import Any

import pytest
from app.agent.answer import AgentAnswer, ReasonCode, refusal
from app.agent.gate import bare_numerals, check, format_value, render
from app.agent.values import Ledger, Value

URL = "https://www.sec.gov/Archives/edgar/data/1/000000000026000001/ex991.htm"
OBS = "obs:7:4:3M-2026-06-30"


def _value(**over: Any) -> Value:
    fields: dict[str, Any] = {
        "vid": OBS,
        "kind": "obs",
        "ticker": "FIXT",
        "label": "Adjusted EBITDA",
        "period_id": "3M-2026-06-30",
        "value": Decimal("1431.5"),
        "scale": "millions",
        "url": URL,
        "verified": True,
    }
    fields.update(over)
    return Value.model_validate(fields)


@pytest.fixture
def ledger() -> Ledger:
    led = Ledger()
    led.add(
        [
            _value(),
            _value(
                vid="calc:abc123def456",
                kind="calc",
                value=Decimal("12.50"),
                unit="percent",
                scale=None,
                url=None,
                formula="pct_change: … = 12.50",
            ),
        ]
    )
    return led


def answer(text: str, **over: Any) -> AgentAnswer:
    fields: dict[str, Any] = {"status": "answered", "text": text}
    fields.update(over)
    return AgentAnswer.model_validate(fields)


def test_a_cited_answer_passes_and_renders(ledger: Ledger) -> None:
    a = answer(
        f'FIXT reported "Adjusted EBITDA (1)" of {{{{{OBS}}}}} for the quarter ended '
        "June 30, 2026 (3M-2026-06-30, Q2 FY2026), up {{calc:abc123def456}} year over "
        "year in its 8-K 0000000000-26-000001.",
        values=[{"name": "Adjusted EBITDA", "vid": OBS}],
    )
    assert check(a, ledger).ok
    r = render(a, ledger)
    assert f"$1,431.5 million [source]({URL})" in r.text
    assert "12.50% (pct_change" in r.text
    assert r.values[0].value == Decimal("1431.5") and not r.values[0].computed


@pytest.mark.parametrize(
    "text, problem",
    [
        ("Adjusted EBITDA was 1,431.5 million.", "bare numeral"),
        ("Margins were 12.5%.", "bare numeral"),
        ("It fell forty percent.", "bare numeral"),
        ("See {{obs:999:1:3M-2026-06-30}}.", "unretrieved vid"),
        ("See {{ebitda_q2}}.", "unknown vid"),
        ("See {{obs:7:4:3M-2026-06-30}.", "malformed placeholder"),
    ],
)
def test_gate_rejections(ledger: Ledger, text: str, problem: str) -> None:
    result = check(answer(text), ledger)
    assert not result.ok
    assert any(problem in p for p in result.problems), result.problems


def test_cited_values_and_names_are_checked(ledger: Ledger) -> None:
    bad = answer("", values=[{"name": "EBITDA of 1431", "vid": OBS}])
    assert any("bare numeral in value name" in p for p in check(bad, ledger).problems)
    unknown = answer("", values=[{"name": "EBITDA", "vid": "obs:1:1:3M-2026-06-30"}])
    assert any("unretrieved" in p for p in check(unknown, ledger).problems)


def test_refusals_need_a_reason(ledger: Ledger) -> None:
    assert check(refusal(ReasonCode.scale_unknown, "The unit is unknown."), ledger).ok
    no_reason = AgentAnswer(status="refused", text="Cannot say.")
    assert not check(no_reason, ledger).ok


def test_allowed_forms_are_not_numerals() -> None:
    assert (
        bare_numerals(
            "For the three months ended Sept. 30, 2025 and FY'24, in 2Q25 and H1 2026, "
            'per "Note 4" and 2026-06-30.'
        )
        == []
    )
    assert bare_numerals("about 5 times") == ["5"]


def test_format_value() -> None:
    assert format_value(_value(value=Decimal("-58.0"))) == "−$58.0 million"
    assert format_value(_value(value=None)) == "— (no amount reported)"
    assert format_value(_value(scale=None)) == "$1,431.5 (scale unknown)"
    assert format_value(_value(unit="items", value=Decimal(2), scale=None)) == "2"
