"""
A-01: FootnoteBench-Credit question schema and validator.

Questions live in ``eval/agent/questions/<split>.jsonl``, one JSON object per line.
A question states what a correct answer must contain (``expected``) and where that
key came from (``key_provenance``). No key without provenance (ADR-011).

Expected answers:

- ``status`` is ``answered``, ``partial`` or ``refused``. A refusal names its
  ``reason_codes``; an answer names none.
- ``values`` are numbers: ``value`` in the stated ``unit`` (and, for ``usd``, the
  reported ``scale``), for one ``period_id`` such as ``3M-2026-06-30``, with an
  absolute ``tolerance`` in the same unit. Values read from a filing carry their
  sec.gov ``source_urls``.
- ``labels`` are as-reported line labels with a change kind (definition changes,
  recurrence).
- ``ranking`` is an ordered list of tickers (cross-issuer questions).

Usage (from ``backend/``)::

    python -m tools.agent_eval.questions --validate
    python -m tools.agent_eval.questions --write-schema   # eval/agent/questions/schema.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Final, Literal

import yaml
from app.extraction.locator import is_sec_archives_url
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

REPO = Path(__file__).resolve().parents[3]
QUESTIONS_DIR = REPO / "eval" / "agent" / "questions"
SCHEMA_FILE = QUESTIONS_DIR / "schema.json"
UNIVERSE = REPO / "config" / "universe.yaml"

BENCHMARK: Final = "footnotebench-credit-v0"

_ID = re.compile(r"^fbc-[a-z0-9]+(-[a-z0-9]+)*$")
_CIK = re.compile(r"^\d{10}$")
_PERIOD = re.compile(r"^(3|6|9|12)M-(\d{4}-\d{2}-\d{2})$")
_TICKER = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_MAX_RELATIVE_TOLERANCE = Decimal("0.01")
_ZERO_VALUE_TOLERANCE = Decimal("0.5")


class Split(str, Enum):
    dev = "dev"
    test = "test"


class Category(str, Enum):
    """PLAN.md categories C1–C9."""

    point_lookup = "point_lookup"  # C1
    multi_period = "multi_period"  # C2
    point_in_time = "point_in_time"  # C3: as first reported vs recast
    addback_composition = "addback_composition"  # C4
    definition_change = "definition_change"  # C5
    normalization = "normalization"  # C6
    cross_issuer = "cross_issuer"  # C7
    must_refuse = "must_refuse"  # C8
    false_premise = "false_premise"  # C9


ANSWERABLE = frozenset(
    {
        Category.point_lookup,
        Category.multi_period,
        Category.point_in_time,
        Category.addback_composition,
        Category.definition_change,
        Category.normalization,
        Category.cross_issuer,
    }
)


class Status(str, Enum):
    answered = "answered"
    partial = "partial"
    refused = "refused"


class ReasonCode(str, Enum):
    """Why an answer is partial or refused. Shared with the agent's answer schema."""

    not_covered = "not_covered"  # issuer outside the universe
    metric_not_ebitda = "metric_not_ebitda"  # e.g. "Adjusted Operating Income"
    no_bridge = "no_bridge"  # no headline bridge found (recorded failure)
    scale_unknown = "scale_unknown"
    period_not_reported = "period_not_reported"
    unclassified_line = "unclassified_line"  # an OTHER line blocks normalization
    out_of_scope = "out_of_scope"  # covenant EBITDA, guidance, segment bridges
    false_premise = "false_premise"
    ambiguous = "ambiguous"
    unverifiable = "unverifiable"


class KeyProvenance(str, Enum):
    """Where an answer key came from. Scores are reported split by this."""

    gold_human = "gold_human"  # gold label, verified_by=human
    gold_model_agreement = (
        "gold_model_agreement"  # gold label, verified_by=model_agreement
    )
    tieout = "tieout"  # store values whose bridge passes sum and anchor checks
    store_status = "store_status"  # a recorded status: failure, unknown scale, coverage
    human_checked = "human_checked"  # a person checked the key against sec.gov


class Unit(str, Enum):
    usd = "usd"
    percent = "percent"
    ratio = "ratio"
    items = "items"  # a count of things, e.g. add-back lines


class Scale(str, Enum):
    units = "units"
    thousands = "thousands"
    millions = "millions"
    billions = "billions"


class LabelChange(str, Enum):
    added = "added"
    dropped = "dropped"
    renamed = "renamed"
    recast = "recast"
    recurring = "recurring"  # a "non-recurring" add-back in >=3 of the last 4 quarters


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _period_end(period_id: str) -> date:
    m = _PERIOD.match(period_id)
    if not m:
        raise ValueError(f"period_id must look like '3M-2026-06-30': {period_id!r}")
    return date.fromisoformat(m.group(2))


class ExpectedValue(_Strict):
    name: str = Field(..., min_length=1, description="what is measured, as asked")
    ticker: str
    period_id: str
    value: Decimal
    unit: Unit
    scale: Scale | None = None
    tolerance: Decimal = Field(..., ge=0)
    source_urls: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> ExpectedValue:
        _period_end(self.period_id)
        if (self.unit is Unit.usd) != (self.scale is not None):
            raise ValueError("scale is required for usd values and only for them")
        limit = (
            abs(self.value) * _MAX_RELATIVE_TOLERANCE
            if self.value != 0
            else _ZERO_VALUE_TOLERANCE
        )
        if self.tolerance > limit:
            raise ValueError(
                f"tolerance {self.tolerance} is looser than 1% of {self.value}"
            )
        for url in self.source_urls:
            if not is_sec_archives_url(url):
                raise ValueError(f"source_url is not a sec.gov Archives URL: {url}")
        return self


class ExpectedLabel(_Strict):
    ticker: str
    label_raw: str = Field(..., min_length=1)
    change: LabelChange
    source_urls: list[str] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _urls(self) -> ExpectedLabel:
        for url in self.source_urls:
            if not is_sec_archives_url(url):
                raise ValueError(f"source_url is not a sec.gov Archives URL: {url}")
        return self


class Expected(_Strict):
    status: Status
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    values: list[ExpectedValue] = Field(default_factory=list)
    labels: list[ExpectedLabel] = Field(default_factory=list)
    ranking: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _shape(self) -> Expected:
        has_content = bool(self.values or self.labels or self.ranking)
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("duplicate reason code")
        if len(set(self.ranking)) != len(self.ranking):
            raise ValueError("duplicate ticker in ranking")
        if self.status is Status.answered:
            if self.reason_codes:
                raise ValueError("an answered key has no reason codes")
            if not has_content:
                raise ValueError("an answered key needs values, labels or a ranking")
        else:
            if not self.reason_codes:
                raise ValueError(f"a {self.status.value} key needs reason codes")
            if self.status is Status.partial and not has_content:
                raise ValueError("a partial key needs values, labels or a ranking")
            if (
                self.status is Status.refused
                and has_content
                and ReasonCode.false_premise not in self.reason_codes
            ):
                raise ValueError(
                    "a refusal carries values only to refute a false premise"
                )
        return self


class Question(_Strict):
    schema_version: Literal[1] = 1
    benchmark: Literal["footnotebench-credit-v0"] = BENCHMARK
    id: str
    split: Split
    category: Category
    question: str = Field(..., min_length=10)
    as_of: date
    tickers: list[str] = Field(..., min_length=1)
    expected: Expected
    key_provenance: KeyProvenance
    author: str = Field(..., min_length=1)
    written_on: date
    checked_by: str | None = None
    checked_on: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Question:
        if not _ID.match(self.id):
            raise ValueError(f"id must look like 'fbc-c1-0001': {self.id!r}")
        for t in self.tickers:
            if not _TICKER.match(t):
                raise ValueError(f"bad ticker: {t!r}")
        exp = self.expected
        cited = (
            {v.ticker for v in exp.values}
            | {lb.ticker for lb in exp.labels}
            | set(exp.ranking)
        )
        if self.category is not Category.cross_issuer and not cited <= set(
            self.tickers
        ):
            raise ValueError(f"expected answer cites tickers not asked about: {cited}")
        for v in exp.values:
            if _period_end(v.period_id) > self.as_of:
                raise ValueError(f"{v.period_id} ends after as_of {self.as_of}")

        if self.category in ANSWERABLE and exp.status is Status.refused:
            raise ValueError(f"{self.category.value} questions must be answerable")
        if self.category is Category.must_refuse and exp.status is not Status.refused:
            raise ValueError("must_refuse questions expect status refused")
        if (
            self.category is Category.false_premise
            and ReasonCode.false_premise not in exp.reason_codes
        ):
            raise ValueError("false_premise questions expect reason false_premise")
        if self.category is Category.cross_issuer and not (exp.ranking or exp.values):
            raise ValueError("cross_issuer keys need a ranking or values")

        if self.key_provenance is KeyProvenance.store_status:
            if exp.status is not Status.refused or exp.values or exp.labels:
                raise ValueError(
                    "store_status keys are only for refusals with no values"
                )
        elif self.key_provenance is not KeyProvenance.human_checked and not (
            exp.values or exp.labels or exp.ranking
        ):
            raise ValueError(
                f"{self.key_provenance.value} keys need values, labels or a ranking"
            )
        if self.key_provenance is KeyProvenance.human_checked and not (
            self.checked_by and self.checked_on
        ):
            raise ValueError("human_checked keys need checked_by and checked_on")
        if (self.checked_by is None) != (self.checked_on is None):
            raise ValueError("checked_by and checked_on go together")
        if self.checked_on is not None and self.checked_on < self.written_on:
            raise ValueError("checked_on is before written_on")
        for v in exp.values:
            if (
                self.key_provenance is not KeyProvenance.store_status
                and v.unit is Unit.usd
                and not v.source_urls
            ):
                raise ValueError(f"usd value {v.name!r} needs its sec.gov source_urls")
        return self


def load_universe(path: Path = UNIVERSE) -> dict[str, str]:
    """Ticker -> 10-digit CIK from ``config/universe.yaml``."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for issuer in data["issuers"]:
        cik = str(issuer["cik"])
        if not _CIK.match(cik):
            raise ValueError(f"universe CIK for {issuer['ticker']} is not 10 digits")
        out[str(issuer["ticker"])] = cik
    return out


def load_file(path: Path) -> tuple[list[Question], list[str]]:
    """Questions in one JSONL file, plus problems (line-numbered)."""
    questions: list[Question] = []
    problems: list[str] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            problems.append(f"{path.name}:{n}: blank line")
            continue
        try:
            questions.append(Question.model_validate_json(line))
        except ValidationError as exc:
            problems.append(
                f"{path.name}:{n}: {exc.error_count()} schema error(s): {exc}"
            )
    return questions, problems


def validate_dir(questions_dir: Path, universe: dict[str, str]) -> list[str]:
    """
    Problems across all question files; an empty list means valid.

    Files are ``<split>.jsonl``. Each question's split matches its file, IDs are
    unique across files, and every ticker is in the universe unless the key is a
    ``not_covered`` refusal (which must then name a ticker outside it).
    """
    problems: list[str] = []
    seen: dict[str, str] = {}
    for path in sorted(questions_dir.glob("*.jsonl")):
        try:
            split = Split(path.stem)
        except ValueError:
            problems.append(f"{path.name}: file name must be one of dev/test .jsonl")
            continue
        questions, file_problems = load_file(path)
        problems.extend(file_problems)
        for q in questions:
            where = f"{path.name}: {q.id}"
            if q.split is not split:
                problems.append(f"{where}: split {q.split.value} in {path.name}")
            if q.id in seen:
                problems.append(f"{where}: duplicate id (also in {seen[q.id]})")
            seen[q.id] = path.name
            uncovered = [t for t in q.tickers if t not in universe]
            not_covered = ReasonCode.not_covered in q.expected.reason_codes
            if uncovered and not not_covered:
                problems.append(f"{where}: tickers not in the universe: {uncovered}")
            if not_covered and not uncovered:
                problems.append(f"{where}: not_covered but every ticker is covered")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--validate", action="store_true")
    group.add_argument("--write-schema", action="store_true")
    args = parser.parse_args()

    if args.write_schema:
        QUESTIONS_DIR.mkdir(parents=True, exist_ok=True)
        SCHEMA_FILE.write_text(
            json.dumps(Question.model_json_schema(), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {SCHEMA_FILE}")
        return 0

    problems = validate_dir(QUESTIONS_DIR, load_universe())
    for p in problems:
        print(p)
    files = sorted(QUESTIONS_DIR.glob("*.jsonl"))
    count = sum(len(load_file(f)[0]) for f in files)
    print(
        f"{len(files)} question files, {count} questions checked, "
        f"{len(problems)} problems"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
