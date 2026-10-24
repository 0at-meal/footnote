"""
A-11: the provenance gate and the numbers-by-reference renderer (ADR-011).

``check`` rejects an answer that:

- types a numeral outside the allow-list (dates, years, period IDs such as
  ``3M-2026-06-30``, quarter labels such as ``Q2`` or ``FY2025``, accession
  numbers, SEC form names such as ``8-K`` or ``EX-99.1``, and text inside quotation marks, which is reserved for as-reported
  labels), or spells a number next to a unit ("forty percent");
- cites a malformed vid (unknown kind), or a well-formed vid this session never
  retrieved;
- refuses without a reason code.

``render`` then replaces every placeholder with the value the ledger holds,
formatted, with its source. The model chooses *which* value to cite; it never
writes one. Known limit: a bare four-digit year (1900–2099) passes the gate, so a
value that looks like a year could slip through as prose; it would still not be
a cited value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from app.agent.answer import AgentAnswer, Status
from app.agent.values import Ledger, Value

PLACEHOLDER = re.compile(r"\{\{\s*([^{}\s]+)\s*\}\}")
VID = re.compile(r"^(obs|norm|calc):[A-Za-z0-9:._\-]+$")

_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|"
    r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_ALLOWED = [
    re.compile(rf"\b{_MONTH}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b"),
    re.compile(rf"\b{_MONTH}\.?\s+\d{{4}}\b"),
    re.compile(r"\b\d{1,2}M-\d{4}-\d{2}-\d{2}\b"),  # period IDs
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),  # ISO dates
    re.compile(r"\b\d{10}-\d{2}-\d{6}\b"),  # accession numbers
    re.compile(  # SEC form and exhibit names: 8-K, 10-Q, EX-99.1, Item 2.02
        r"\b(?:8-K|10-Q|10-K|20-F|6-K|EX-\d+(?:\.\d+)?|Exhibit\s+\d+(?:\.\d+)?"
        r"|Item\s+\d+\.\d+)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:FY|CY)\s?'?\d{2,4}\b"),
    re.compile(r"\b[QH][1-4](?:\s?'?\d{2,4})?\b"),
    re.compile(r"\b[1-4]Q\s?'?\d{2,4}\b"),
    re.compile(r"\b(?:19|20)\d{2}\b"),  # years
]
_QUOTED = re.compile(r'"[^"\n]*"|' + "“[^”\n]*”")
_SPELLED = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand)"
    r"(?:[\s-]+\w+)?\s+(?:percent|per cent|million|billion|thousand|dollars)\b",
    re.IGNORECASE,
)
_SCALE_WORD = {
    "units": "",
    "thousands": " thousand",
    "millions": " million",
    "billions": " billion",
}


@dataclass(frozen=True)
class GateResult:
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def bare_numerals(text: str) -> list[str]:
    """Numerals typed in prose, after placeholders, quotes and allowed forms."""
    rest = PLACEHOLDER.sub(" ", text)
    rest = _QUOTED.sub(" ", rest)
    for pattern in _ALLOWED:
        rest = pattern.sub(" ", rest)
    found = re.findall(r"\S*\d\S*", rest)
    found += [m.group(0) for m in _SPELLED.finditer(rest)]
    return found


def _vid_problem(vid: str, ledger: Ledger) -> str | None:
    if not VID.match(vid):
        return f"unknown vid {vid!r}: not an obs:, norm: or calc: value ID"
    if vid not in ledger:
        return f"unretrieved vid {vid!r}: no tool returned it in this session"
    return None


def check(answer: AgentAnswer, ledger: Ledger) -> GateResult:
    problems: list[str] = []
    for where, text in [("text", answer.text)] + [
        (f"value name {v.name!r}", v.name) for v in answer.values
    ]:
        typed = bare_numerals(text)
        if typed:
            problems.append(f"bare numeral in {where}: {typed}; cite a vid instead")
    cited = [m.group(1) for m in PLACEHOLDER.finditer(answer.text)]
    cited += [v.vid for v in answer.values]
    cited += [lb.vid for lb in answer.labels if lb.vid]
    for vid in dict.fromkeys(cited):
        problem = _vid_problem(vid, ledger)
        if problem:
            problems.append(problem)
    if "{{" in PLACEHOLDER.sub("", answer.text) or "}}" in PLACEHOLDER.sub(
        "", answer.text
    ):
        problems.append("malformed placeholder: use {{vid}}")
    if answer.status is not Status.answered and not answer.reason_codes:
        problems.append(f"a {answer.status.value} answer needs a reason code")
    return GateResult(problems)


def format_value(v: Value) -> str:
    if v.value is None:
        return "— (no amount reported)"
    if v.unit == "percent":
        return f"{v.value}%"
    if v.unit == "ratio":
        return f"{v.value}x"
    if v.unit == "items":
        return str(v.value)
    sign = "−" if v.value < 0 else ""
    amount = abs(v.value)
    scale = _SCALE_WORD.get(v.scale or "", " (scale unknown)")
    return f"{sign}${amount:,}{scale}"


@dataclass(frozen=True)
class RenderedValue:
    name: str
    vid: str
    value: Decimal | None
    unit: str
    scale: str | None
    period_id: str | None
    ticker: str
    source_url: str | None
    xpath: str | None
    computed: bool
    verified: bool
    formula: str | None


@dataclass(frozen=True)
class Rendered:
    text: str
    values: list[RenderedValue]


def render(answer: AgentAnswer, ledger: Ledger) -> Rendered:
    """Write the numbers. Call only after ``check`` passed."""

    def sub(m: re.Match[str]) -> str:
        v = ledger.get(m.group(1))
        if v is None:
            raise ValueError(f"render before check: {m.group(1)} not in the ledger")
        shown = format_value(v)
        if v.url:
            return f"{shown} [source]({v.url})"
        if v.formula:
            return f"{shown} ({v.formula})"
        return shown

    values = []
    for c in answer.values:
        v = ledger.get(c.vid)
        if v is None:
            raise ValueError(f"render before check: {c.vid} not in the ledger")
        values.append(
            RenderedValue(
                name=c.name,
                vid=v.vid,
                value=v.value,
                unit=v.unit,
                scale=v.scale,
                period_id=v.period_id,
                ticker=v.ticker,
                source_url=v.url,
                xpath=v.xpath,
                computed=v.kind != "obs",
                verified=v.verified,
                formula=v.formula,
            )
        )
    return Rendered(PLACEHOLDER.sub(sub, answer.text), values)
