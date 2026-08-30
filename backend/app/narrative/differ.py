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
    RiskFactor,
    RiskFactorChange,
    RiskFactorRedline,
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


def diff_risk_factors(
    earlier_risks: list[RiskFactor],
    later_risks: list[RiskFactor],
    company_id: str | None = None,
    earlier_job_id: str = "",
    later_job_id: str = "",
) -> RiskFactorRedline:
    """
    Compute heading-matched delta redline for Item 1A Risk Factors.
    """
    changes: list[RiskFactorChange] = []
    matched_early_indices: set[int] = set()

    for late in later_risks:
        best_match_idx: int | None = None
        best_match_ratio: float = 0.0

        for idx, early in enumerate(earlier_risks):
            if idx in matched_early_indices:
                continue
            # Exact or fuzzy heading match
            if early.heading.strip().lower() == late.heading.strip().lower():
                best_match_idx = idx
                best_match_ratio = 1.0
                break
            ratio = difflib.SequenceMatcher(
                None, early.heading.lower(), late.heading.lower()
            ).ratio()
            if ratio > 0.70 and ratio > best_match_ratio:
                best_match_ratio = ratio
                best_match_idx = idx

        if best_match_idx is None:
            # Newly added risk factor
            changes.append(
                RiskFactorChange(
                    heading=late.heading,
                    change_type="added",
                    severity_score=1.0,
                    added_text=late.body_text,
                    removed_text="",
                )
            )
        else:
            matched_early_indices.add(best_match_idx)
            early = earlier_risks[best_match_idx]
            body_sim = difflib.SequenceMatcher(
                None, early.body_text, late.body_text
            ).ratio()

            if body_sim < 0.98 or early.heading != late.heading:
                severity = round(1.0 - body_sim, 2)
                changes.append(
                    RiskFactorChange(
                        heading=late.heading,
                        change_type="modified",
                        severity_score=max(0.1, severity),
                        added_text=late.body_text,
                        removed_text=early.body_text,
                    )
                )

    # Check for removed risk factors
    for idx, early in enumerate(earlier_risks):
        if idx not in matched_early_indices:
            changes.append(
                RiskFactorChange(
                    heading=early.heading,
                    change_type="removed",
                    severity_score=1.0,
                    added_text="",
                    removed_text=early.body_text,
                )
            )

    # Sort changes by severity descending
    changes.sort(key=lambda c: c.severity_score, reverse=True)

    added_cnt = sum(1 for c in changes if c.change_type == "added")
    removed_cnt = sum(1 for c in changes if c.change_type == "removed")
    modified_cnt = sum(1 for c in changes if c.change_type == "modified")

    return RiskFactorRedline(
        company_id=company_id,
        earlier_job_id=earlier_job_id,
        later_job_id=later_job_id,
        changes=changes,
        added_count=added_cnt,
        removed_count=removed_cnt,
        modified_count=modified_cnt,
    )
