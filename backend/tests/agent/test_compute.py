"""
Tests for the A-10 compute tool. All values are synthetic fixtures built in
memory; none describe a filing.
"""

from decimal import Decimal
from typing import Any

import pytest
from app.agent.compute import ComputeError, compute
from app.agent.values import Ledger, Value


def obs(
    vid: str, value: str | None, period: str = "3M-2025-03-31", **over: Any
) -> Value:
    fields: dict[str, Any] = {
        "vid": vid,
        "kind": "obs",
        "ticker": "FIXT",
        "label": "Adjusted EBITDA",
        "period_id": period,
        "value": None if value is None else Decimal(value),
        "scale": "millions",
        "role": "total",
        "sign": 1,
        "line_key": "adjusted ebitda",
        "verified": True,
    }
    fields.update(over)
    return Value.model_validate(fields)


QUARTERS = ["3M-2025-03-31", "3M-2025-06-30", "3M-2025-09-30", "3M-2025-12-31"]


@pytest.fixture
def ledger() -> Ledger:
    led = Ledger()
    led.add([obs(f"obs:q{i}", str(125 + 10 * i), p) for i, p in enumerate(QUARTERS)])
    led.add(
        [
            obs("obs:prior", "125", "3M-2024-12-31"),
            obs(
                "obs:restr",
                "5",
                "3M-2025-12-31",
                label="Restructuring",
                role="adjustment",
                line_key="restructuring",
            ),
            obs(
                "obs:gain",
                "8",
                "3M-2025-12-31",
                label="Gain on sale",
                role="adjustment",
                sign=-1,
                line_key="gain on sale",
            ),
            obs("obs:dash", None, "3M-2025-12-31", label="Other", role="adjustment"),
            obs("obs:k", "155000", "3M-2025-12-31", scale="thousands"),
            obs("obs:other", "50", "3M-2025-12-31", ticker="FIXB"),
            obs(
                "obs:unv",
                "1",
                "3M-2025-12-31",
                label="X",
                role="adjustment",
                line_key="x",
                verified=False,
            ),
        ]
    )
    return led


def test_ltm_sum_is_a_twelve_month_value(ledger: Ledger) -> None:
    v = compute("sum", ["obs:q0", "obs:q1", "obs:q2", "obs:q3"], ledger)
    assert (
        v.value == 560 and v.period_id == "12M-2025-12-31" and v.vid.startswith("calc:")
    )
    assert v.formula == "sum: 125 + 135 + 145 + 155 = 560"
    assert v.inputs == ("obs:q0", "obs:q1", "obs:q2", "obs:q3") and v.verified
    assert compute("sum", ["obs:q0", "obs:q1"], ledger).period_id == "6M-2025-06-30"


def test_pct_change_contribution_share_and_chaining(ledger: Ledger) -> None:
    yoy = compute("pct_change", ["obs:q3", "obs:prior"], ledger)
    assert yoy.value == Decimal("24.00") and yoy.unit == "percent" and yoy.scale is None
    gain = compute("contribution", ["obs:gain"], ledger)
    assert gain.value == -8
    ledger.add([gain])
    share = compute("share", ["obs:restr", "obs:q3"], ledger)
    assert share.value == Decimal("3.23")
    removed = compute("sum", ["obs:restr", gain.vid], ledger)
    ledger.add([removed])
    assert compute("difference", ["obs:q3", removed.vid], ledger).value == 158
    assert compute("count", ["obs:restr", "obs:gain"], ledger).value == 2


@pytest.mark.parametrize(
    "op, vids, reason",
    [
        ("sum", ["obs:q3", "obs:k"], "mixed scales"),
        ("difference", ["obs:q2", "obs:q3"], "mixed periods"),
        ("sum", ["obs:q0", "obs:q2"], "not consecutive"),
        ("sum", ["obs:q0", "obs:q1", "obs:restr"], "one line"),
        ("pct_change", ["obs:q3", "obs:restr"], "different lines"),
        ("pct_change", ["obs:q3", "obs:q3"], "twice"),
        ("share", ["obs:q3", "obs:other"], "mixed issuers"),
        ("sum", ["obs:q3", "obs:dash"], "dash placeholder"),
        ("sum", ["obs:q3", "obs:never"], "not retrieved"),
        ("difference", ["obs:q3"], "takes 2"),
        ("power", ["obs:q3"], "unknown operation"),
    ],
)
def test_refusals(ledger: Ledger, op: str, vids: list[str], reason: str) -> None:
    with pytest.raises(ComputeError, match=reason):
        compute(op, vids, ledger)


def test_unverified_inputs_are_carried(ledger: Ledger) -> None:
    v = compute("difference", ["obs:q3", "obs:unv"], ledger)
    assert not v.verified and "obs:unv" in v.notes[0]


def test_same_inputs_give_the_same_vid(ledger: Ledger) -> None:
    a = compute("sum", ["obs:q0", "obs:q1"], ledger)
    b = compute("sum", ["obs:q0", "obs:q1"], ledger)
    assert a == b
    ledger.add([a, b])  # the ledger accepts an identical re-computation
