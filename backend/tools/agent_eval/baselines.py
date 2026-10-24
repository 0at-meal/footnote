"""
A-08: baseline systems for FootnoteBench-Credit.

Each baseline sees only the question's issuers' Item 2.02 exhibits filed on or
before ``as_of``, read from the local EDGAR cache (no network), and must answer
in the same JSON shape the scorer reads (``SystemAnswer``), typing its numbers
itself:

- **B0** closed book: the question alone.
- **B1** plain retrieval: the top passages by BM25 over chunked exhibits
  (pure Python, no vector database).
- **B2** long context: whole exhibits, newest first, up to a character budget.

Output that is not valid JSON in that shape is recorded as an error with the
reason, never repaired.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.agent.answer import ReasonCode
from app.agent.model import ModelClient
from app.store.db import Store
from bs4 import BeautifulSoup
from pydantic import ValidationError

from tools.agent_eval.questions import Question
from tools.agent_eval.records import SystemAnswer
from tools.agent_eval.systems import SystemResult, prompt_hash

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "edgar_cache"
MAX_TOKENS = 4000
CHUNK_CHARS = 1500
CHUNK_OVERLAP = 200
B1_TOP_K = 8
B2_CHAR_BUDGET = 160_000  # about 40K input tokens per question

SYSTEM_PROMPT = f"""You answer questions from credit analysts about US-listed \
issuers' earnings releases (EBITDA reconciliations). Answer only from the \
material provided; if it does not support an answer, refuse.

Reply with one JSON object and nothing else:
{{
  "status": "answered" | "partial" | "refused",
  "reason_codes": [one or more of {[r.value for r in ReasonCode]}] (empty if answered),
  "values": [{{"name": str, "value": number, "unit": "usd"|"percent"|"ratio"|"items",
              "scale": "units"|"thousands"|"millions"|"billions" (usd only),
              "period_id": "3M-YYYY-MM-DD" style (3M/6M/9M/12M + period end),
              "ticker": str, "source_url": str (the sec.gov URL you read it from)}}],
  "labels": [{{"label": str, "change": "added"|"dropped"|"renamed"|"recast"|"recurring"}}],
  "ranking": [ticker, ...],
  "text": str
}}
Give amounts as reported, negative when shown in parentheses. If the question \
rests on a false premise, say so with reason "false_premise" and give the \
correct figures."""


@dataclass(frozen=True)
class Exhibit:
    ticker: str
    accession: str
    filed: date
    url: str
    text: str


class Corpus:
    """The cached EX-99.1 text of every filing in the store, by ticker."""

    def __init__(self, store: Store, cache_dir: Path = CACHE_DIR) -> None:
        self.cache_dir = cache_dir
        self.store = store
        self._text: dict[Path, str | None] = {}

    def exhibits(self, tickers: list[str], as_of: date) -> list[Exhibit]:
        out: list[Exhibit] = []
        for r in self.store.query(
            f"""
            SELECT i.ticker, f.accession, f.filed, f.url, f.exhibit
            FROM filings f JOIN issuers i ON i.cik = f.cik
            WHERE i.ticker IN ({",".join("?" * len(tickers))}) AND f.filed <= ?
              AND f.exhibit IS NOT NULL
            ORDER BY f.filed DESC
            """,
            (*tickers, as_of.isoformat()),
        ):
            text = self._read(self.cache_dir / r["accession"] / r["exhibit"])
            if text is not None:
                out.append(
                    Exhibit(
                        r["ticker"],
                        r["accession"],
                        date.fromisoformat(r["filed"]),
                        r["url"],
                        text,
                    )
                )
        return out

    def _read(self, path: Path) -> str | None:
        if path not in self._text:
            if not path.is_file():
                self._text[path] = None
            else:
                soup = BeautifulSoup(path.read_bytes(), "html.parser")
                for row in soup.find_all("tr"):
                    cells = [
                        " ".join(c.get_text(" ").split())
                        for c in row.find_all(["td", "th"])
                    ]
                    row.replace_with(" | ".join(c for c in cells if c) + "\n")
                lines = (
                    " ".join(ln.split()) for ln in soup.get_text("\n").splitlines()
                )
                self._text[path] = "\n".join(ln for ln in lines if ln)
        return self._text[path]


def header(e: Exhibit) -> str:
    return f"[{e.ticker} earnings release filed {e.filed} — {e.url}]"


# ---- BM25 ------------------------------------------------------------------------

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def chunks(
    e: Exhibit, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP
) -> list[str]:
    step = size - overlap
    return [e.text[i : i + size] for i in range(0, max(len(e.text) - overlap, 1), step)]


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.docs = [tokenize(d) for d in docs]
        self.k1, self.b = k1, b
        self.avg = sum(len(d) for d in self.docs) / len(self.docs) if self.docs else 0.0
        df: Counter[str] = Counter()
        for d in self.docs:
            df.update(set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in self.docs]

    def scores(self, query: str) -> list[float]:
        q = tokenize(query)
        out = []
        for tf, d in zip(self.tf, self.docs, strict=True):
            s = 0.0
            for t in q:
                if t not in tf:
                    continue
                f = tf[t]
                s += (
                    self.idf[t]
                    * f
                    * (self.k1 + 1)
                    / (f + self.k1 * (1 - self.b + self.b * len(d) / (self.avg or 1)))
                )
            out.append(s)
        return out

    def top(self, query: str, k: int) -> list[int]:
        scored = sorted(enumerate(self.scores(query)), key=lambda x: (-x[1], x[0]))
        return [i for i, s in scored[:k] if s > 0]


# ---- systems ------------------------------------------------------------------------


def parse_answer(text: str) -> tuple[SystemAnswer | None, str | None]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None, "invalid output: no JSON object"
    try:
        return SystemAnswer.model_validate(json.loads(text[start : end + 1])), None
    except (json.JSONDecodeError, ValidationError) as exc:
        return None, f"invalid output: {type(exc).__name__}: {str(exc)[:300]}"


def _question_block(q: Question) -> str:
    return (
        f"Question (as of {q.as_of.isoformat()}; issuers: {', '.join(q.tickers)}):\n"
        f"{q.question}"
    )


class _Baseline:
    name = ""

    def __init__(self, corpus: Corpus | None = None) -> None:
        self.corpus = corpus

    def context(self, q: Question) -> str:
        return ""

    def messages(self, q: Question) -> list[dict[str, object]]:
        ctx = self.context(q)
        body = f"{ctx}\n\n{_question_block(q)}" if ctx else _question_block(q)
        return [{"role": "user", "content": body}]

    def answer(self, question: Question, client: ModelClient) -> SystemResult:
        messages = self.messages(question)
        phash = prompt_hash(self.name, SYSTEM_PROMPT, MAX_TOKENS)
        turn = client.create(
            system=SYSTEM_PROMPT, messages=messages, tools=[], max_tokens=MAX_TOKENS
        )
        if turn.stop_reason not in ("end_turn", "stop_sequence"):
            return SystemResult(None, phash, error=f"stop_reason {turn.stop_reason}")
        answer, error = parse_answer(turn.text)
        return SystemResult(answer, phash, error=error)


class ClosedBook(_Baseline):
    name = "B0"


class Retrieval(_Baseline):
    name = "B1"

    def context(self, q: Question) -> str:
        assert self.corpus is not None
        exhibits = self.corpus.exhibits(q.tickers, q.as_of)
        pieces = [(e, c) for e in exhibits for c in chunks(e)]
        if not pieces:
            return "No filings are available for these issuers as of that date."
        index = BM25([c for _, c in pieces])
        top = index.top(q.question, B1_TOP_K)
        return "\n\n".join(f"{header(pieces[i][0])}\n{pieces[i][1]}" for i in top)


class LongContext(_Baseline):
    name = "B2"

    def context(self, q: Question) -> str:
        assert self.corpus is not None
        exhibits = self.corpus.exhibits(q.tickers, q.as_of)
        if not exhibits:
            return "No filings are available for these issuers as of that date."
        parts: list[str] = []
        used = 0
        for e in exhibits:  # newest first
            block = f"{header(e)}\n{e.text}"
            if used + len(block) > B2_CHAR_BUDGET and parts:
                break
            parts.append(block[:B2_CHAR_BUDGET])
            used += len(block)
        return "\n\n".join(parts)
