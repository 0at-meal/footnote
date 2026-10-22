"""
Stable line keys: the same bridge line keeps its key across quarters (P2-01).
"""

import re

_FOOTNOTE = re.compile(
    r"\s*\((?:[a-z]|\d{1,2})\)(?:,\s*\((?:[a-z]|\d{1,2})\))*\s*$", re.IGNORECASE
)


def line_key(label: str) -> str:
    """Case, whitespace, dash and trailing-footnote insensitive label key."""
    text = label.replace("—", "-").replace("–", "-").replace("’", "'")
    text = re.sub(r"^\s*plus:\s*", "", text, flags=re.IGNORECASE)
    previous = None
    while previous != text:
        previous = text
        text = _FOOTNOTE.sub("", text)
    return re.sub(r"\s+", " ", text).strip().lower()
