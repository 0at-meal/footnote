"""
Narrative Section Differ (Feature 10, Step G & H).

Pure deterministic word/token-level diffing between narrative sections using difflib.
No LLM calls or numeric hallucinations.

Adheres to:
- CONSTITUTION §1.1: mypy --strict compliance.
- CONSTITUTION §1.2: Deterministic sequence matching.
"""

import difflib
import re

from app.narrative.models import (
    NarrativeDiff,
    NarrativeDiffToken,
    NarrativeSection,
)


def tokenize_narrative_text(text: str) -> list[str]:
    """
    Tokenize narrative text into words and whitespace/punctuation preserving exact structure.
    """
    if not text:
        return []
    # Match non-whitespace words or whitespace chunks
    return re.findall(r"\S+|\s+", text)


def diff_narrative_sections(
    earlier: NarrativeSection,
    later: NarrativeSection,
    company_id: str | None = None,
) -> NarrativeDiff:
    """
    Compute token-level word diff between earlier and later narrative sections.
    """
    tokens_a = tokenize_narrative_text(earlier.text)
    tokens_b = tokenize_narrative_text(later.text)

    matcher = difflib.SequenceMatcher(None, tokens_a, tokens_b)
    diff_tokens: list[NarrativeDiffToken] = []

    added_count = 0
    removed_count = 0
    unchanged_count = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            chunk_text = "".join(tokens_a[i1:i2])
            if chunk_text:
                diff_tokens.append(NarrativeDiffToken(type="equal", text=chunk_text))
                # Count non-whitespace words
                unchanged_count += len([t for t in tokens_a[i1:i2] if t.strip()])

        elif tag == "delete":
            chunk_text = "".join(tokens_a[i1:i2])
            if chunk_text:
                diff_tokens.append(NarrativeDiffToken(type="delete", text=chunk_text))
                removed_count += len([t for t in tokens_a[i1:i2] if t.strip()])

        elif tag == "insert":
            chunk_text = "".join(tokens_b[j1:j2])
            if chunk_text:
                diff_tokens.append(NarrativeDiffToken(type="insert", text=chunk_text))
                added_count += len([t for t in tokens_b[j1:j2] if t.strip()])

        elif tag == "replace":
            chunk_deleted = "".join(tokens_a[i1:i2])
            chunk_inserted = "".join(tokens_b[j1:j2])
            if chunk_deleted:
                diff_tokens.append(
                    NarrativeDiffToken(type="delete", text=chunk_deleted)
                )
                removed_count += len([t for t in tokens_a[i1:i2] if t.strip()])
            if chunk_inserted:
                diff_tokens.append(
                    NarrativeDiffToken(type="insert", text=chunk_inserted)
                )
                added_count += len([t for t in tokens_b[j1:j2] if t.strip()])

    similarity = round(float(matcher.ratio()), 4)

    return NarrativeDiff(
        company_id=company_id,
        item_number=later.item_number or earlier.item_number,
        earlier_job_id=earlier.job_id,
        later_job_id=later.job_id,
        tokens=diff_tokens,
        added_tokens=added_count,
        removed_tokens=removed_count,
        unchanged_tokens=unchanged_count,
        similarity_ratio=similarity,
    )
