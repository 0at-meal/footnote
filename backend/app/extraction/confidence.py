"""
Structural confidence scoring engine for Feature 2, Step 4.

Scope:
    Evaluates extracted records deterministically using structural signals,
    computes a confidence score in [0.0, 1.0], assigns confidence routing bands
    (auto_accepted >= 0.95, needs_review 0.65-0.95, manual_required < 0.65),
    and attaches diagnostic flags.

Isolation (CONSTITUTION §3.8, §3.2):
    This module must NEVER import from classification/, formula_engine/, excel_export/,
    or audit_report/.
"""

import re

from app.extraction.models import (
    ConfidenceBand,
    ExtractedRecord,
    NormalizedItem,
    ScoredRecord,
)

# Footnote reference markers: e.g. (1), (a), [1], *, †, ‡
_FOOTNOTE_MARKER_REGEX = re.compile(r"(\(\d+\)|\([a-zA-Z]\)|\[\d+\]|[\*\†\‡])")


def assign_confidence_band(score: float) -> ConfidenceBand:
    """
    Assign a confidence routing band based on a structural score.

    Boundaries are upper-inclusive (Spec EC-8):
        score >= 0.95 -> auto_accepted
        0.65 <= score < 0.95 -> needs_review
        score < 0.65 -> manual_required

    Args:
        score: Computed confidence score in [0.0, 1.0].

    Returns:
        ConfidenceBand enum value.
    """
    if score >= 0.95:
        return ConfidenceBand.auto_accepted
    if score >= 0.65:
        return ConfidenceBand.needs_review
    return ConfidenceBand.manual_required


def compute_confidence_score(record: ExtractedRecord) -> tuple[float, list[str]]:
    """
    Compute a deterministic structural confidence score and list of diagnostic flags.

    Args:
        record: The ExtractedRecord to evaluate.

    Returns:
        A tuple of (confidence_score, list_of_flag_strings).
    """
    score = 1.0
    flags: list[str] = []

    clean_label = record.label.strip()
    clean_val = record.value.strip()

    # Signal 1: Missing header hierarchy
    if not clean_label or clean_label == clean_val or " / " not in clean_label:
        score -= 0.15
        flags.append("missing_header_hierarchy")

    # Signal 2: Label / cell span ambiguity
    lower_label = clean_label.lower()
    if "merged" in lower_label or "ambiguous" in lower_label or not clean_label:
        score -= 0.35
        flags.append("label_ambiguity")

    # Signal 3: Footnote marker present in label or value
    if _FOOTNOTE_MARKER_REGEX.search(clean_label) or _FOOTNOTE_MARKER_REGEX.search(
        clean_val
    ):
        score -= 0.10
        flags.append("footnote_marker_present")

    clamped_score = round(max(0.0, min(1.0, score)), 2)
    return clamped_score, flags


def score_record(
    record: ExtractedRecord,
    normalized_item: NormalizedItem | None = None,
) -> ScoredRecord:
    """
    Score a single ExtractedRecord and return a ScoredRecord.

    Args:
        record: The ExtractedRecord instance.
        normalized_item: Optional corresponding NormalizedItem to check error status.

    Returns:
        A ScoredRecord with confidence_score, confidence_band, and flags.
    """
    table_name = normalized_item.table_name if normalized_item is not None else None
    is_rec = (
        normalized_item.is_reconciliation_candidate
        if normalized_item is not None
        else record.is_reconciliation_candidate
    )

    if normalized_item is not None and normalized_item.is_error:
        return ScoredRecord(
            record=record,
            confidence_score=0.0,
            confidence_band=ConfidenceBand.manual_required,
            flags=["extraction_error"],
            table_name=table_name,
            status="extraction_error",
            error_detail=normalized_item.error_detail or "Extraction error",
            is_reconciliation_candidate=is_rec,
        )

    score, flags = compute_confidence_score(record)
    band = assign_confidence_band(score)
    return ScoredRecord(
        record=record,
        confidence_score=score,
        confidence_band=band,
        flags=flags,
        table_name=table_name,
        status="ok",
        error_detail=None,
        is_reconciliation_candidate=is_rec,
    )


def score_records(
    records: list[ExtractedRecord],
    normalized_items: list[NormalizedItem] | None = None,
) -> list[ScoredRecord]:
    """
    Score a list of ExtractedRecord objects, preserving input ordering (NFR1).

    Args:
        records: List of ExtractedRecord objects.
        normalized_items: Optional parallel list of NormalizedItem objects.

    Returns:
        List of ScoredRecord objects in identical order.
    """
    if normalized_items is not None and len(normalized_items) == len(records):
        return [score_record(rec, norm) for rec, norm in zip(records, normalized_items)]
    return [score_record(rec) for rec in records]
