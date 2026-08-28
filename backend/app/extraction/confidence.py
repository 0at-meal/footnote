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

import logging
import re
from collections import defaultdict

from app.extraction.models import (
    ConfidenceBand,
    ExtractedRecord,
    NormalizedItem,
    ScoredRecord,
)

logger = logging.getLogger(__name__)

# Footnote reference markers: e.g. (1), (a), [1], *, †, ‡
_FOOTNOTE_MARKER_REGEX = re.compile(r"(\(\d+\)|\([a-zA-Z]\)|\[\d+\]|[\*\†\‡])")


def is_well_formed_numeric_value(val: str) -> bool:
    """
    Check whether an extracted string represents a well-formed financial numeric value.

    Handles parenthetical negatives (e.g. '(123,456)' -> '-123456'), currency symbols ($),
    percentage signs (%), and comma formatting.
    """
    s = val.strip()
    if not s:
        return False
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()
    s = s.replace("$", "").replace("%", "").replace(",", "").strip()
    if not s:
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


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


def compute_confidence_score(
    record: ExtractedRecord,
    is_reconciliation_candidate: bool | None = None,
) -> tuple[float, list[str]]:
    """
    Compute a deterministic structural confidence score and list of diagnostic flags.

    Args:
        record: The ExtractedRecord to evaluate.
        is_reconciliation_candidate: Optional flag indicating if item is from a reconciliation table.
                                      If None, uses record.is_reconciliation_candidate.

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

    # Signal 4: Reconciliation candidate table bonus (Ticket 3.3)
    # Offsets the -0.15 missing_header_hierarchy deduction for flat labels in reconciliation tables
    is_rec = (
        is_reconciliation_candidate
        if is_reconciliation_candidate is not None
        else record.is_reconciliation_candidate
    )
    if is_rec:
        score += 0.15

    # Signal 5: Numeric value signal (Ticket 6.1)
    if is_well_formed_numeric_value(clean_val):
        score += 0.05
        flags.append("value_is_numeric")

    clamped_score = round(max(0.0, min(1.0, score)), 2)
    return clamped_score, flags


def _apply_table_consistency_boost(
    scored_records: list[ScoredRecord],
) -> list[ScoredRecord]:
    """
    Post-pass to boost confidence of items in predominantly high-confidence tables (Ticket 6.2).

    If >= 70% of items in a named table have confidence_score >= 0.80,
    boost all remaining items in that table (< 0.80) with status != 'extraction_error'
    by +0.10 (clamped to 1.0) and update their confidence band.
    """
    table_groups: dict[str, list[ScoredRecord]] = defaultdict(list)
    for rec in scored_records:
        if rec.table_name and rec.table_name.strip():
            table_groups[rec.table_name].append(rec)

    for table_name, items in table_groups.items():
        if not items:
            continue
        high_conf_count = sum(1 for item in items if item.confidence_score >= 0.80)
        ratio = high_conf_count / len(items)
        if ratio >= 0.70:
            logger.debug(
                "Table '%s' qualified for consistency boost (%.1f%% >= 0.80)",
                table_name,
                ratio * 100.0,
            )
            for item in items:
                if item.confidence_score < 0.80 and item.status != "extraction_error":
                    new_score = round(min(1.0, item.confidence_score + 0.10), 2)
                    item.confidence_score = new_score
                    item.confidence_band = assign_confidence_band(new_score)
                    if "table_consistency_boost" not in item.flags:
                        item.flags.append("table_consistency_boost")
                    logger.debug(
                        "Applied table consistency boost (+0.10) to item '%s' in table '%s' (new score: %.2f)",
                        item.record.label,
                        table_name,
                        new_score,
                    )

    return scored_records


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

    score, flags = compute_confidence_score(
        record, is_reconciliation_candidate=is_rec
    )
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
        List of ScoredRecord objects in identical order with table consistency boosts applied.
    """
    if normalized_items is not None and len(normalized_items) == len(records):
        scored = [
            score_record(rec, norm) for rec, norm in zip(records, normalized_items)
        ]
    else:
        scored = [score_record(rec) for rec in records]
    return _apply_table_consistency_boost(scored)
