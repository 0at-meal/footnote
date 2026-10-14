"""
P0-05b: render a saved gold release's approved table as plain text rows.

This is deliberately *not* the extractor: it does no cell merging, period
binding, sign or subtotal logic. Each ``<tr>`` becomes one line of its non-empty
cell texts joined by ``" | "``, preceded by the text just above the table (where
scale captions often sit). A reader (P0-05b) transcribes the bridge from this
output independently of ``tools.gold.draft``.

Usage (from ``backend/``)::

    python -m tools.gold.render_table <accession> [<accession> ...]
"""

from __future__ import annotations

import gzip
import re
import sys
from pathlib import Path

import yaml
from bs4 import BeautifulSoup, Tag

GOLD_DIR = Path(__file__).resolve().parents[3] / "eval" / "gold"


def _text(node: Tag) -> str:
    return re.sub(
        r"\s+", " ", node.get_text(" ", strip=True).replace("\xa0", " ")
    ).strip()


def render(html: bytes, table_index: int, context_chars: int = 400) -> str:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find_all("table")[table_index]
    before = " ".join(
        s.strip()
        for s in reversed(table.find_all_previous(string=True, limit=60))
        if s.strip()
    )
    scale_phrases = re.findall(
        r"[^.()]{0,40}\bin (?:thousands|millions|billions)\b[^.()]{0,30}",
        before[-8000:],
    )
    lines = [
        f"[text before table] ...{before[-context_chars:]}",
        f"[scale phrases in the 8,000 chars before the table] {scale_phrases[-3:]}",
        "[table]",
    ]
    for i, tr in enumerate(table.find_all("tr")):
        cells = [_text(td) for td in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if cells:
            lines.append(f"r{i:02d}: " + " | ".join(cells))
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    issuers = yaml.safe_load((GOLD_DIR / "issuers.yaml").read_text(encoding="utf-8"))
    by_acc = {
        r["accession"]: (c["ticker"], r)
        for c in issuers["selected"]
        for r in c["releases"]
    }
    for acc in argv:
        ticker, rel = by_acc[acc]
        path = GOLD_DIR / "raw" / acc / f"{rel['exhibit']}.gz"
        print(f"===== {ticker} {acc} table {rel['table_index']}")
        print(render(gzip.decompress(path.read_bytes()), int(rel["table_index"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
