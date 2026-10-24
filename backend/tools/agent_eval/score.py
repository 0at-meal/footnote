"""
A-06: deterministic scorer for FootnoteBench-Credit runs.

Input: the question files and the ``Trial`` JSONL a run wrote. Output: per
system, every metric overall, per ``key_provenance`` and per category. No model is
involved in grading (ADR-011).

Per trial:

- **answered** means status ``answered`` or ``partial``.
- A **value matches** an expected value when the unit is the same, the period and
  ticker agree where the answer gives them, and the values agree within the key's
  tolerance after scaling (an amount in millions is compared in dollars). A dollar
  amount without a scale cannot be compared, so it never matches.
- **wrong number**: the answer contains a value that matches no expected value. A
  number given for a question that has no correct number (C8) is always wrong.
- **correct**:
  - answerable questions: answered, every expected value matched, labels and
    ranking equal, and no wrong number;
  - refusals: refused (for a false premise, also any answer whose reason codes
    name ``false_premise``), a reason code the key accepts, and no wrong number.

Metrics: wrong-number rate (wrong / answered), accuracy, coverage and
over-refusal on answerable questions, correct refusal and reason-code accuracy on
must-refuse ones, the refusal confusion matrix, citation validity, pass@1 / pass^k
/ pass@k, the risk–coverage point, and cost, tokens and latency.

Usage (from ``backend/``)::

    python -m tools.agent_eval.score ../eval/agent/runs/<run> --split dev
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.analytics.source import resolve_xpath
from app.extraction.bridge.keys import line_key
from bs4 import BeautifulSoup, Tag

from tools.agent_eval.questions import (
    QUESTIONS_DIR,
    ExpectedValue,
    Question,
    ReasonCode,
    Status,
    Unit,
    load_file,
)
from tools.agent_eval.records import (
    AnswerLabel,
    AnswerValue,
    SystemAnswer,
    Trial,
    read_trials,
)

SCALE = {
    "units": Decimal(1),
    "thousands": Decimal(1_000),
    "millions": Decimal(1_000_000),
    "billions": Decimal(1_000_000_000),
}
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "edgar_cache"
_EN_DASH = chr(0x2013)
_NOISE = re.compile("[$" + chr(0x200B) + chr(0xA0) + "]")
_NUMBER = re.compile(r"(?<![\w.,])[(\-" + _EN_DASH + r"]?\d[\d,]*(?:\.\d+)?\)?(?![\w])")
_ARCHIVE = re.compile(r"/Archives/edgar/data/\d+/(\d{18})/([^/#?]+)")


def _norm(value: Decimal, unit: Unit, scale: str | None) -> Decimal | None:
    if unit is not Unit.usd:
        return value
    if scale is None:
        return None
    return value * SCALE[scale]


def value_matches(a: AnswerValue, e: ExpectedValue) -> bool:
    if a.unit is not e.unit:
        return False
    if a.period_id is not None and a.period_id != e.period_id:
        return False
    if a.ticker is not None and a.ticker != e.ticker:
        return False
    got = _norm(a.value, a.unit, a.scale.value if a.scale else None)
    want = _norm(e.value, e.unit, e.scale.value if e.scale else None)
    if got is None or want is None:
        return False
    tol = _norm(e.tolerance, e.unit, e.scale.value if e.scale else None)
    assert tol is not None
    return abs(got - want) <= tol


def _label(text: str) -> str:
    return line_key(text)


@dataclass(frozen=True)
class Grade:
    question_id: str
    system: str
    trial: int
    expected_refusal: bool
    outcome: str  # answered | partial | refused | error
    answered: bool
    correct: bool
    wrong_number: bool
    status_ok: bool
    reason_ok: bool | None  # None unless the key expects a refusal
    values_cited: int
    values_cited_valid: int | None  # None when no citation checker was given


class CitationChecker:
    """
    Checks that a cited sec.gov document, read from the local EDGAR cache,
    contains the cited number. With an XPath, the cell it points to must hold the
    number (``app.analytics.source.resolve_xpath``); otherwise the number must
    appear in the document text. A document missing from the cache is invalid.
    """

    def __init__(self, cache_dir: Path = CACHE_DIR) -> None:
        self.cache_dir = cache_dir
        self._docs: dict[Path, BeautifulSoup | None] = {}

    def _doc(self, url: str) -> BeautifulSoup | None:
        m = _ARCHIVE.search(url)
        if m is None:
            return None
        raw, name = m.group(1), m.group(2)
        acc = f"{raw[:10]}-{raw[10:12]}-{raw[12:]}"
        path = self.cache_dir / acc / name
        if path not in self._docs:
            self._docs[path] = (
                BeautifulSoup(path.read_bytes(), "html.parser")
                if path.is_file()
                else None
            )
        return self._docs[path]

    @staticmethod
    def numbers(text: str) -> set[Decimal]:
        """Every number in the text, as a whole token: "1,200" is never "200".
        Accounting parentheses and leading minus signs make a number negative."""
        text = _NOISE.sub(" ", text)
        text = re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", text))
        out: set[Decimal] = set()
        for m in _NUMBER.finditer(text):
            token = m.group(0)
            negative = token.startswith(("(", "-", _EN_DASH)) and (
                not token.startswith("(") or token.endswith(")")
            )
            digits = token.strip("()-" + _EN_DASH).replace(",", "")
            value = Decimal(digits)
            out.add(-value if negative else value)
        return out

    def valid(self, v: AnswerValue) -> bool:
        if v.source_url is None:
            return False
        doc = self._doc(v.source_url)
        if doc is None:
            return False
        node: Tag = doc
        if v.xpath:
            parts = [p for p in v.xpath.split("/") if p]
            root = doc.html
            found = (
                resolve_xpath(root, parts[1:])
                if root is not None and parts[:1] == ["html"]
                else None
            )
            if found is None:
                return False
            node = found
        return v.value in self.numbers(node.get_text(" "))


def grade(q: Question, t: Trial, checker: CitationChecker | None = None) -> Grade:
    exp = q.expected
    expected_refusal = exp.status is Status.refused
    a = t.answer
    if a is None:
        return Grade(
            q.id,
            t.system,
            t.trial,
            expected_refusal,
            "error",
            False,
            False,
            False,
            False,
            None if not expected_refusal else False,
            0,
            0 if checker else None,
        )
    answered = a.status in (Status.answered, Status.partial)
    unmatched = [
        v for v in a.values if not any(value_matches(v, e) for e in exp.values)
    ]
    wrong = bool(unmatched)
    false_premise = ReasonCode.false_premise in exp.reason_codes
    if expected_refusal:
        status_ok = a.status is Status.refused or (
            false_premise and ReasonCode.false_premise in a.reason_codes
        )
        reason_ok: bool | None = bool(set(a.reason_codes) & set(exp.reason_codes))
        correct = status_ok and bool(reason_ok) and not wrong
    else:
        status_ok = answered
        reason_ok = None
        values_ok = all(any(value_matches(v, e) for v in a.values) for e in exp.values)
        labels_ok = {(_label(x.label_raw), x.change) for x in exp.labels} == {
            (_label(x.label), x.change) for x in a.labels
        }
        ranking_ok = list(exp.ranking) == list(a.ranking)
        correct = status_ok and values_ok and labels_ok and ranking_ok and not wrong
    cited = [v for v in a.values if v.source_url and not v.computed]
    valid = sum(checker.valid(v) for v in cited) if checker else None
    return Grade(
        q.id,
        t.system,
        t.trial,
        expected_refusal,
        a.status.value,
        answered,
        correct,
        wrong,
        status_ok,
        reason_ok,
        len(cited),
        valid,
    )


def _rate(num: int, den: int) -> dict[str, Any]:
    return {"rate": round(num / den, 4) if den else None, "n": num, "of": den}


def _percentile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, round(p * (len(xs) - 1))))
    return round(xs[k], 3)


def metrics(grades: list[Grade], trials: list[Trial]) -> dict[str, Any]:
    answerable = [g for g in grades if not g.expected_refusal]
    refusals = [g for g in grades if g.expected_refusal]
    answered = [g for g in grades if g.answered]
    by_q: dict[str, list[Grade]] = defaultdict(list)
    for g in grades:
        by_q[g.question_id].append(g)
    k = min((len(v) for v in by_q.values()), default=0)
    confusion: dict[str, dict[str, int]] = {
        "expected_answer": defaultdict(int),
        "expected_refusal": defaultdict(int),
    }
    for g in grades:
        row = "expected_refusal" if g.expected_refusal else "expected_answer"
        confusion[row][g.outcome] += 1
    cited = sum(g.values_cited for g in grades)
    checked = [g.values_cited_valid for g in grades if g.values_cited_valid is not None]
    correct_trials = sum(g.correct for g in grades)
    cost = sum((t.cost_usd for t in trials), Decimal(0))
    latencies = [t.latency_s for t in trials]
    wrong_answered = sum(g.wrong_number for g in answered)
    return {
        "questions": len(by_q),
        "trials": len(grades),
        "wrong_number_rate": _rate(wrong_answered, len(answered)),
        "accuracy": _rate(correct_trials, len(grades)),
        "coverage": _rate(sum(g.answered for g in answerable), len(answerable)),
        "over_refusal": _rate(
            sum(g.outcome == "refused" for g in answerable), len(answerable)
        ),
        "correct_refusal": _rate(sum(g.status_ok for g in refusals), len(refusals)),
        "reason_code_accuracy": _rate(
            sum(bool(g.reason_ok) for g in refusals if g.status_ok),
            sum(g.status_ok for g in refusals),
        ),
        "errors": sum(g.outcome == "error" for g in grades),
        "confusion": {r: dict(v) for r, v in confusion.items()},
        "citation_validity": (
            _rate(sum(checked), cited)
            if checked and len(checked) == len(grades)
            else None
        ),
        "pass_at_1": _rate(correct_trials, len(grades)),
        "pass_hat_k": {
            "k": k,
            **_rate(
                sum(all(g.correct for g in v[:k]) for v in by_q.values()), len(by_q)
            ),
        },
        "pass_at_k": {
            "k": k,
            **_rate(
                sum(any(g.correct for g in v[:k]) for v in by_q.values()), len(by_q)
            ),
        },
        # Systems give no confidence score, so the curve is one point:
        # risk = wrong numbers among answered trials, at this coverage.
        "risk_coverage": {
            "coverage": _rate(len(answered), len(grades))["rate"],
            "risk": _rate(wrong_answered, len(answered))["rate"],
        },
        "cost_usd": {
            "total": str(cost),
            "per_trial": str(cost / len(trials)) if trials else None,
            "per_correct": str(cost / correct_trials) if correct_trials else None,
        },
        "tokens": {
            "input": sum(t.usage.input_tokens for t in trials),
            "output": sum(t.usage.output_tokens for t in trials),
            "cache_read": sum(t.usage.cache_read_tokens for t in trials),
            "cache_write": sum(t.usage.cache_write_tokens for t in trials),
        },
        "latency_s": {
            "p50": _percentile(latencies, 0.5),
            "p95": _percentile(latencies, 0.95),
            "mean": round(statistics.fmean(latencies), 3) if latencies else None,
        },
        "tool_calls_mean": (
            round(statistics.fmean(t.tool_calls for t in trials), 2) if trials else None
        ),
    }


def score(
    questions: Iterable[Question],
    trials: Iterable[Trial],
    checker: CitationChecker | None = None,
) -> dict[str, Any]:
    """
    Metrics per system: overall, per key provenance and per category. Trials for
    unknown question IDs are an error, never skipped.
    """
    qs = {q.id: q for q in questions}
    by_system: dict[str, list[Trial]] = defaultdict(list)
    for t in trials:
        if t.question_id not in qs:
            raise ValueError(f"trial for unknown question {t.question_id!r}")
        by_system[t.system].append(t)
    report: dict[str, Any] = {}
    for system, ts in sorted(by_system.items()):
        graded = [(grade(qs[t.question_id], t, checker), t) for t in ts]
        missing = sorted(set(qs) - {t.question_id for t in ts})

        def slice_(
            pred: Any, graded: list[tuple[Grade, Trial]] = graded
        ) -> dict[str, Any]:
            sel = [(g, t) for g, t in graded if pred(qs[g.question_id])]
            return metrics([g for g, _ in sel], [t for _, t in sel])

        provenances = sorted({q.key_provenance.value for q in qs.values()})
        categories = sorted({q.category.value for q in qs.values()})
        report[system] = {
            "unanswered_questions": missing,
            "overall": slice_(lambda q: True),
            "by_key_provenance": {
                p: slice_(lambda q, p=p: q.key_provenance.value == p)
                for p in provenances
            },
            "by_category": {
                c: slice_(lambda q, c=c: q.category.value == c) for c in categories
            },
        }
    return report


def oracle_trials(questions: Iterable[Question]) -> list[Trial]:
    """
    The answer keys as answers, for a scorer self-check: every key must grade as
    correct, and its single-source values must be found in the cached filings.
    This is not a system result.
    """
    out: list[Trial] = []
    for q in questions:
        exp = q.expected
        answer = SystemAnswer(
            status=exp.status,
            reason_codes=exp.reason_codes[:1],
            values=[
                AnswerValue(
                    name=e.name,
                    value=e.value,
                    unit=e.unit,
                    scale=e.scale,
                    period_id=e.period_id,
                    ticker=e.ticker,
                    source_url=e.source_urls[0] if e.source_urls else None,
                    computed=len(e.source_urls) != 1 or e.unit is not Unit.usd,
                )
                for e in exp.values
            ],
            labels=[
                AnswerLabel(label=x.label_raw, change=x.change, ticker=x.ticker)
                for x in exp.labels
            ],
            ranking=list(exp.ranking),
        )
        out.append(
            Trial(
                question_id=q.id,
                system="ORACLE",
                trial=1,
                model="none",
                prompt_hash="none",
                answer=answer,
            )
        )
    return out


def load_questions(questions_dir: Path, split: str | None) -> list[Question]:
    out: list[Question] = []
    for path in sorted(questions_dir.glob("*.jsonl")):
        qs, problems = load_file(path)
        if problems:
            raise ValueError(f"{path.name}: {problems}")
        out.extend(q for q in qs if split is None or q.split.value == split)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "run_dir", type=Path, nargs="?", help="directory of trial JSONL files"
    )
    parser.add_argument(
        "--oracle", action="store_true", help="score the keys themselves (self-check)"
    )
    parser.add_argument("--questions", type=Path, default=QUESTIONS_DIR)
    parser.add_argument("--split", choices=["dev", "test"])
    parser.add_argument("--no-citations", action="store_true")
    parser.add_argument("--json", type=Path, help="write the full report here")
    args = parser.parse_args()
    questions = load_questions(args.questions, args.split)
    ids = {q.id for q in questions}
    if args.oracle:
        trials = oracle_trials(questions)
    elif args.run_dir is None:
        parser.error("give a run directory or --oracle")
    else:
        trials = [
            t
            for p in sorted(args.run_dir.glob("*.jsonl"))
            for t in read_trials(p)
            if t.question_id in ids
        ]
    report = score(questions, trials, None if args.no_citations else CitationChecker())
    for system, r in report.items():
        o = r["overall"]
        print(
            f"{system:8} trials {o['trials']:5}  wrong-number "
            f"{o['wrong_number_rate']['rate']}  accuracy {o['accuracy']['rate']}  "
            f"coverage {o['coverage']['rate']}  correct-refusal "
            f"{o['correct_refusal']['rate']}  pass^{o['pass_hat_k']['k']} "
            f"{o['pass_hat_k']['rate']}  cost ${o['cost_usd']['total']}"
        )
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
