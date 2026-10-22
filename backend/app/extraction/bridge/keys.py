"""
Stable line keys: the same bridge line keeps its key across quarters (P2-01).
"""

import re

# Trailing footnote markers: "(a)", "(12)", "[2]", "[2] [4] [5]", "(1)(3)",
# "(a), (b)", and a lone superscript digit after a word ("Adjusted EBITDA 3").
_MARK = r"(?:\((?:[a-z]|\d{1,2})\)|\[(?:[a-z]|\d{1,2})\])"
_FOOTNOTE = re.compile(rf"\s*{_MARK}(?:[,\s]*{_MARK})*\s*$", re.IGNORECASE)
_SUPERSCRIPT = re.compile(r"(?<=[a-z)])\s+\d$", re.IGNORECASE)
_INVISIBLE = re.compile(r"[\u200b-\u200d\u2060\ufeff]")


def line_key(label: str) -> str:
    """
    Case, whitespace, dash, hyphen and trailing-footnote insensitive label key.

    Zero-width characters and non-breaking spaces (common in EDGAR HTML) are
    ignored, and "stock-based" and "stock based" give the same key.
    """
    text = _INVISIBLE.sub("", label).replace("\N{NO-BREAK SPACE}", " ")
    text = text.replace("—", "-").replace("–", "-").replace("’", "'")
    text = re.sub(r"^\s*plus:\s*", "", text, flags=re.IGNORECASE)
    previous = None
    while previous != text:
        previous = text
        text = _FOOTNOTE.sub("", text)
        text = _SUPERSCRIPT.sub("", text)
    text = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip().lower()
