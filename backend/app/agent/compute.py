"""
A-10: deterministic arithmetic over cited values (ADR-011).

The model never does arithmetic. It asks ``compute`` for an operation over vids
it has already retrieved; the result is a new ``calc:`` value with a formula
trace, cited like any other. Only ``Decimal`` is used. An operation that would
mix units, scales, periods, lines or issuers is refused with a reason, never
coerced.

Operations:

- ``contribution(v)``: the line as it contributes to the total (sign × value).
- ``sum(v...)``: values in one period, or one line over 2–4 consecutive quarters
  (the result period is then ``6M``/``9M``/``12M`` ending at the last quarter).
- ``difference(a, b)``: a − b, same period.
- ``change(new, old)`` and ``pct_change(new, old)``: the same line of the same
  issuer in two periods.
- ``share(part, whole)``: part / whole × 100, same period and issuer.
- ``ratio(a, b)``: a / b, same period.
- ``count(v...)``: how many distinct values.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise
from typing import Literal

from app.agent.values import Ledger, Value

Op = Literal[
    "contribution",
    "sum",
    "difference",
    "change",
    "pct_change",
    "share",
    "ratio",
    "count",
]
ARITY: dict[str, tuple[int, int]] = {
    "contribution": (1, 1),
    "sum": (2, 16),
    "difference": (2, 2),
    "change": (2, 2),
    "pct_change": (2, 2),
    "share": (2, 2),
    "ratio": (2, 2),
    "count": (1, 64),
}
_RATE = Decimal("0.01")


class ComputeError(ValueError):
    """A refused computation; the message is the reason given to the model."""


def _end(period_id: str | None) -> date | None:
    if not period_id or "M-" not in period_id:
        return None
    try:
        return date.fromisoformat(period_id.split("M-", 1)[1])
    except ValueError:
        return None


def _months(period_id: str | None) -> int | None:
    if not period_id or "M-" not in period_id:
        return None
    head = period_id.split("M-", 1)[0]
    return int(head) if head.isdigit() else None


def _fmt(v: Value) -> str:
    return "—" if v.value is None else str(v.value)


def _same(values: list[Value], attr: str, what: str) -> None:
    seen = {getattr(v, attr) for v in values}
    if len(seen) > 1:
        raise ComputeError(f"mixed {what}: {sorted(str(x) for x in seen)}")


def _line(v: Value) -> str:
    return "__total__" if v.role == "total" else (v.line_key or v.label)


def compute(op: str, vids: list[str], ledger: Ledger) -> Value:
    if op not in ARITY:
        raise ComputeError(f"unknown operation {op!r}")
    lo, hi = ARITY[op]
    if not lo <= len(vids) <= hi:
        raise ComputeError(f"{op} takes {lo}–{hi} values, got {len(vids)}")
    if len(set(vids)) != len(vids):
        raise ComputeError("the same vid is given twice")
    values: list[Value] = []
    for vid in vids:
        v = ledger.get(vid)
        if v is None:
            raise ComputeError(f"{vid} was not retrieved in this session")
        values.append(v)
    if op != "count" and any(v.value is None for v in values):
        raise ComputeError("a value is a dash placeholder (no amount)")
    nums = [v.value for v in values if v.value is not None]
    first = values[0]
    unit, scale, period, label = first.unit, first.scale, first.period_id, first.label
    tickers = {v.ticker for v in values}

    if op == "contribution":
        if first.sign not in (1, -1):
            raise ComputeError(f"{first.vid} has no bridge sign")
        result = first.sign * nums[0]
        formula = f"{first.sign} × {_fmt(first)}"
        label = f"{first.label} (contribution)"
    elif op == "count":
        result = Decimal(len(values))
        unit, scale, formula = "items", None, f"count of {len(values)} values"
        label = "count"
        period = first.period_id if len({v.period_id for v in values}) == 1 else None
    else:
        _same(values, "unit", "units")
        if unit == "usd":
            _same(values, "scale", "scales")
            if scale is None:
                raise ComputeError("scale unknown: amounts cannot be combined")
        if op == "sum":
            result, period, formula = _sum(values, nums)
            label = f"sum of {len(values)} values"
        elif op in ("difference", "share", "ratio"):
            _same(values, "period_id", "periods")
            a, b = nums
            if op == "difference":
                result = a - b
                formula = f"{_fmt(values[0])} − {_fmt(values[1])}"
                label = f"{values[0].label} minus {values[1].label}"
            else:
                if len(tickers) > 1:
                    raise ComputeError(f"mixed issuers: {sorted(tickers)}")
                if b == 0:
                    raise ComputeError("division by zero")
                factor = Decimal(100) if op == "share" else Decimal(1)
                result = (a / b * factor).quantize(_RATE)
                unit = "percent" if op == "share" else "ratio"
                scale = None
                sym = "× 100" if op == "share" else ""
                formula = f"{_fmt(values[0])} ÷ {_fmt(values[1])} {sym}".strip()
                label = f"{values[0].label} as a share of {values[1].label}"
        else:  # change, pct_change
            new, old = values
            if len(tickers) > 1:
                raise ComputeError(f"mixed issuers: {sorted(tickers)}")
            if _line(new) != _line(old):
                raise ComputeError(f"different lines: {new.label!r} vs {old.label!r}")
            if new.period_id == old.period_id:
                raise ComputeError("change needs two different periods")
            a, b = nums
            period = new.period_id
            if op == "change":
                result, formula = a - b, f"{_fmt(new)} − {_fmt(old)}"
                label = f"change in {new.label}"
            else:
                if b == 0:
                    raise ComputeError("division by zero")
                result = ((a - b) / abs(b) * 100).quantize(_RATE)
                unit, scale = "percent", None
                formula = f"({_fmt(new)} − {_fmt(old)}) ÷ |{_fmt(old)}| × 100"
                label = f"% change in {new.label}"

    digest = hashlib.sha256(f"{op}|{'|'.join(vids)}".encode()).hexdigest()[:12]
    unverified = [v.vid for v in values if not v.verified]
    return Value(
        vid=f"calc:{digest}",
        kind="calc",
        ticker=first.ticker if len(tickers) == 1 else ",".join(sorted(tickers)),
        label=label,
        period_id=period,
        value=result,
        unit=unit,
        scale=scale,
        verified=not unverified,
        formula=f"{op}: {formula} = {result}",
        inputs=tuple(vids),
        notes=(f"unverified inputs: {unverified}",) if unverified else (),
    )


def _sum(values: list[Value], nums: list[Decimal]) -> tuple[Decimal, str | None, str]:
    total = sum(nums, Decimal(0))
    formula = " + ".join(_fmt(v) for v in values)
    periods = [v.period_id for v in values]
    if len(set(periods)) == 1:
        return total, periods[0], formula
    if len(set(periods)) != len(periods):
        raise ComputeError("mixed periods: some periods repeat and others differ")
    _same(values, "ticker", "issuers")
    if len({_line(v) for v in values}) != 1:
        raise ComputeError("a sum over periods must be one line")
    if any(_months(p) != 3 for p in periods):
        raise ComputeError("a sum over periods must use 3-month periods")
    ends = sorted(e for p in periods if (e := _end(p)) is not None)
    if len(ends) != len(periods) or len(ends) > 4:
        raise ComputeError("a sum over periods takes 2–4 quarters")
    gaps = [b - a for a, b in pairwise(ends)]
    if not all(timedelta(days=80) <= g <= timedelta(days=100) for g in gaps):
        raise ComputeError("the quarters are not consecutive")
    return total, f"{3 * len(ends)}M-{ends[-1].isoformat()}", formula
