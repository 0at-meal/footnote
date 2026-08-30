"""
Narrative Section Extractor (Feature 10, Step G & H).

Extracts textual sections (Item 7 MD&A, Item 2 MD&A, Item 1A Risk Factors)
from parsed filing layout items or raw text.

Adheres to:
- CONSTITUTION §1.1: mypy --strict compliance.
- Pure deterministic parsing without LLM dependency.
"""

import re
from collections.abc import Sequence

from app.extraction.models import DoclingItem, ExtractedRecord, ScoredRecord
from app.narrative.models import NarrativeSection, RiskFactor

_ITEM_7_REGEX = re.compile(
    r"\bitem\s+7\.?\s*(?:[-:—]\s*)?(?:management'?s?\s+discussion\s+and\s+analysis|md&a)\b",
    re.IGNORECASE,
)
_ITEM_2_REGEX = re.compile(
    r"\bitem\s+2\.?\s*(?:[-:—]\s*)?(?:management'?s?\s+discussion\s+and\s+analysis|md&a)\b",
    re.IGNORECASE,
)
_ITEM_1A_REGEX = re.compile(
    r"\bitem\s+1a\.?\s*(?:[-:—]\s*)?risk\s+factors\b",
    re.IGNORECASE,
)
_NEXT_ITEM_REGEX = re.compile(
    r"\bitem\s+(?:1b|2|3|7a|8|9)\b",
    re.IGNORECASE,
)


def extract_narrative_sections_from_text(
    job_id: str,
    full_text: str,
) -> list[NarrativeSection]:
    """
    Extract narrative sections from raw plain text document using heading boundary parsing.
    """
    sections: list[NarrativeSection] = []

    # 1. Look for Item 7 MD&A
    mda_match = _ITEM_7_REGEX.search(full_text)
    if not mda_match:
        mda_match = _ITEM_2_REGEX.search(full_text)

    if mda_match:
        item_no = "Item 7" if "7" in mda_match.group(0) else "Item 2"
        # Find next section heading
        rest_text = full_text[mda_match.end() :]
        next_match = _NEXT_ITEM_REGEX.search(rest_text)
        if next_match:
            section_body = rest_text[: next_match.start()].strip()
        else:
            section_body = rest_text[:20000].strip()

        sections.append(
            NarrativeSection(
                job_id=job_id,
                item_number=item_no,
                title=f"{item_no}. Management's Discussion and Analysis of Financial Condition and Results of Operations",
                text=section_body,
                page_start=1,
                page_end=1,
            )
        )

    # 2. Look for Item 1A Risk Factors
    risk_match = _ITEM_1A_REGEX.search(full_text)
    if risk_match:
        rest_risk = full_text[risk_match.end() :]
        next_match = re.search(r"\bitem\s+(?:1b|1c|2|3)\b", rest_risk, re.IGNORECASE)
        if next_match:
            risk_body = rest_risk[: next_match.start()].strip()
        else:
            risk_body = rest_risk[:30000].strip()

        sections.append(
            NarrativeSection(
                job_id=job_id,
                item_number="Item 1A",
                title="Item 1A. Risk Factors",
                text=risk_body,
                page_start=1,
                page_end=1,
            )
        )

    return sections


def extract_narrative_sections(
    job_id: str,
    records_or_items: (
        Sequence[DoclingItem | ExtractedRecord | ScoredRecord] | None
    ) = None,
    raw_text: str | None = None,
) -> list[NarrativeSection]:
    """
    Main extraction function for narrative sections from parsed records or text.
    """
    if raw_text:
        return extract_narrative_sections_from_text(job_id, raw_text)

    if not records_or_items:
        return []

    # Gather text chunks ordered by page
    chunks_by_page: dict[int, list[str]] = {}
    for r in records_or_items:
        rec = r.record if isinstance(r, ScoredRecord) else r
        page = getattr(rec, "page", 1)
        label = getattr(rec, "label", "")
        val = getattr(rec, "value", "")
        text = f"{label} {val}".strip()
        if text:
            chunks_by_page.setdefault(page, []).append(text)

    # Reconstruct document text
    all_pages = sorted(chunks_by_page.keys())
    full_doc = "\n\n".join(
        "\n".join(chunks_by_page[p]) for p in all_pages if chunks_by_page[p]
    )

    extracted = extract_narrative_sections_from_text(job_id, full_doc)
    if extracted and all_pages:
        for s in extracted:
            s.page_start = all_pages[0]
            s.page_end = all_pages[-1]

    return extracted


def extract_risk_factors(risk_section_text: str) -> list[RiskFactor]:
    """
    Parse individual risk factors (heading + body text) from Item 1A text.
    """
    if not risk_section_text.strip():
        return []

    # Heuristic: split by paragraphs with prominent leading sentences or bold headers
    paragraphs = [p.strip() for p in risk_section_text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in risk_section_text.split("\n") if p.strip()]

    risks: list[RiskFactor] = []
    for p in paragraphs:
        # First sentence or first 120 chars as heading
        first_period = p.find(". ")
        if first_period != -1 and first_period < 150:
            heading = p[: first_period + 1].strip()
            body = p[first_period + 1 :].strip()
        else:
            lines = p.split("\n")
            heading = lines[0].strip()
            body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""

        if len(heading) > 5:
            risks.append(RiskFactor(heading=heading, body_text=body))

    return risks
