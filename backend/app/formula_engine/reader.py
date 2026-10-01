"""
Pure reader and validator for formula engine inputs (Feature 4 Step 1).

Enforces CONSTITUTION §1.4:
- 100% pure function: no I/O, no clock, no random, no global mutable state.
- Idempotent and deterministic for identical input data.
"""

import logging

from app.classification.models import ClassifiedRecord
from app.extraction.models import ConfidenceBand
from app.formula_engine.models import (
    FormulaInputBatch,
    FormulaInputError,
    FormulaInputNode,
)
from app.review.models import ReviewItem, ReviewStatus

_logger = logging.getLogger(__name__)

_REQUIRED_BBOX_KEYS = ("x0", "y0", "x1", "y1")


def _validate_bbox(bbox: dict[str, float]) -> str | None:
    """
    Validates that a bounding box dictionary conforms to W3C 0-1000 normalized coordinate space.

    Returns an error description if invalid, or None if valid.
    """
    for key in _REQUIRED_BBOX_KEYS:
        if key not in bbox:
            return f"Missing required bbox key '{key}'"
        val = bbox[key]
        if not isinstance(val, (int, float)):
            return f"Bbox coordinate '{key}' must be numeric, got {type(val).__name__}"
        if val < 0.0 or val > 1000.0:
            return f"Bbox coordinate '{key}' value {val} is outside valid [0.0, 1000.0] range (EC-8)"

    if bbox["x0"] > bbox["x1"]:
        return f"Bbox x0 ({bbox['x0']}) cannot be greater than x1 ({bbox['x1']})"
    if bbox["y0"] > bbox["y1"]:
        return f"Bbox y0 ({bbox['y0']}) cannot be greater than y1 ({bbox['y1']})"

    return None


def read_formula_inputs(
    records: list[ClassifiedRecord],
    include_unreviewed: bool = False,
) -> FormulaInputBatch:
    """
    Extracts and validates authoritative input nodes from a batch of ClassifiedRecord objects.

    Rules (AC-8, AC-9, EC-1, EC-2, EC-3, EC-5, EC-8, FN-030):
    1. Two-path inclusion / Generate-First workflow:
       - If include_unreviewed is False (default): only auto-accepted and confirmed items are included.
       - If include_unreviewed is True: all non-error items are included immediately
         with confidence metadata (auto_accepted, needs_review, manual_required per Invariant I3).
    2. Auto-accepted records without normalized_label fall back to raw extraction label.
    3. Manual-required records have value set to "" (empty and red in workbook per I3).
    4. Provenance fields (value, page, bbox, source_file, locator) are validated and passed.
    """
    nodes: list[FormulaInputNode] = []
    errors: list[FormulaInputError] = []
    excluded_count = 0

    for idx, classified_record in enumerate(records):
        is_auto_accepted = (
            classified_record.record.confidence_band == ConfidenceBand.auto_accepted
        )
        is_explicitly_confirmed = classified_record.is_confirmed and bool(
            classified_record.normalized_label
            and classified_record.normalized_label.strip()
        )

        if not (is_auto_accepted or is_explicitly_confirmed):
            if not include_unreviewed:
                excluded_count += 1
                continue

        # Resolve effective normalized label
        if (
            classified_record.normalized_label
            and classified_record.normalized_label.strip()
        ):
            effective_normalized_label = classified_record.normalized_label.strip()
        else:
            effective_normalized_label = classified_record.record.record.label.strip()
            _logger.debug(
                "Record at index %d has no normalized_label; "
                "falling back to raw label %r",
                idx,
                effective_normalized_label,
            )

        raw_record = classified_record.record.record

        # Validate provenance fields (AC-9, EC-8)
        provenance_error: str | None = None
        if not raw_record.source_file or not raw_record.source_file.strip():
            provenance_error = "Missing or empty source_file"
        elif raw_record.page < 1:
            provenance_error = f"Invalid page number {raw_record.page} (must be >= 1)"
        elif not isinstance(raw_record.bbox, dict):
            provenance_error = f"Invalid bbox type: expected dict, got {type(raw_record.bbox).__name__}"
        else:
            provenance_error = _validate_bbox(raw_record.bbox)

        if provenance_error is not None:
            errors.append(
                FormulaInputError(
                    record_index=idx,
                    reason=provenance_error,
                    label=effective_normalized_label,
                    source_file=raw_record.source_file or None,
                )
            )
            continue

        # Determine confidence status and value per Invariant I3 (FN-030)
        c_band = classified_record.record.confidence_band
        if is_explicitly_confirmed or is_auto_accepted:
            review_status = "confirmed" if is_explicitly_confirmed else "auto_accepted"
            band_str = "auto_accepted"
            is_confirmed = True
            node_val = str(raw_record.value)
        elif c_band == ConfidenceBand.manual_required:
            review_status = "manual_required"
            band_str = "manual_required"
            is_confirmed = False
            node_val = ""  # Left empty per Invariant I3
        else:
            review_status = "needs_review"
            band_str = "needs_review"
            is_confirmed = False
            node_val = str(raw_record.value)

        # Create valid FormulaInputNode
        node = FormulaInputNode(
            node_id=f"node_{idx}_{effective_normalized_label}",
            normalized_label=effective_normalized_label,
            value=node_val,
            label=raw_record.label,
            page=raw_record.page,
            bbox=raw_record.bbox,
            source_file=raw_record.source_file,
            locator=getattr(raw_record, "locator", None),
            record_index=idx,
            is_hardcode=(c_band == ConfidenceBand.manual_required),
            statement_type=classified_record.statement_type,
            confidence_band=band_str,
            confidence_score=classified_record.record.confidence_score,
            flags=list(classified_record.record.flags),
            review_status=review_status,
            is_confirmed=is_confirmed,
        )
        nodes.append(node)

    error_message: str | None = None
    if len(nodes) == 0:
        error_message = "No confirmed records available for formula generation."

    return FormulaInputBatch(
        nodes=nodes,
        errors=errors,
        total_records_received=len(records),
        confirmed_count=sum(1 for n in nodes if n.is_confirmed),
        excluded_count=excluded_count,
        error_message=error_message,
    )


def read_formula_inputs_from_review(
    items: list[ReviewItem],
    include_unreviewed: bool = False,
) -> FormulaInputBatch:
    """
    Extracts and validates authoritative input nodes from a list of ReviewItem objects (FN-030).

    Rules:
    1. If include_unreviewed=False (default): only locked/auto-accepted items are included.
       If include_unreviewed=True: generates immediate model from all items;
       unreviewed items tagged as needs_review or manual_required per Invariant I3.
    2. Items marked extraction_error or without labels are excluded.
    3. Manual-required items are left empty (value="") per Invariant I3.
    4. Provenance fields (value, page, bbox, source_file, locator) are validated and passed.
    """
    nodes: list[FormulaInputNode] = []
    errors: list[FormulaInputError] = []
    excluded_count = 0

    for idx, item in enumerate(items):
        # 1. Skip explicit extraction errors
        if item.status == ReviewStatus.extraction_error:
            excluded_count += 1
            continue

        # 2. Resolve effective normalized label
        effective_label = (item.normalized_label or "").strip() or (
            item.label or ""
        ).strip()
        if not effective_label:
            excluded_count += 1
            continue

        # Items pending taxonomy confirmation without a standardized label cannot be mapped
        if item.status == ReviewStatus.pending_taxonomy_confirmation and not (
            item.normalized_label and item.normalized_label.strip()
        ):
            excluded_count += 1
            continue

        # 3. Check eligibility
        is_eligible = (
            item.status in (ReviewStatus.locked, ReviewStatus.auto_accepted)
            or item.confidence_band == ConfidenceBand.auto_accepted
            or (
                item.status == ReviewStatus.needs_review
                and bool(item.normalized_label and item.normalized_label.strip())
            )
        )

        if not is_eligible and not include_unreviewed:
            excluded_count += 1
            continue

        # 4. Validate provenance fields (AC-9, EC-8, CONSTITUTION §1.4)
        provenance_error: str | None = None
        if not item.source_file or not item.source_file.strip():
            provenance_error = "Missing or empty source_file"
        elif item.page < 1:
            provenance_error = f"Invalid page number {item.page} (must be >= 1)"
        elif not isinstance(item.bbox, dict):
            provenance_error = (
                f"Invalid bbox type: expected dict, got {type(item.bbox).__name__}"
            )
        else:
            provenance_error = _validate_bbox(item.bbox)

        if provenance_error is not None:
            errors.append(
                FormulaInputError(
                    record_index=idx,
                    reason=provenance_error,
                    label=effective_label,
                    source_file=item.source_file or None,
                )
            )
            continue

        # 5. Determine status and value per Invariant I3 (FN-030)
        raw_val = item.value if item.value is not None else item.extracted_value
        is_locked = item.status == ReviewStatus.locked
        is_auto = (
            item.status == ReviewStatus.auto_accepted
            or item.confidence_band == ConfidenceBand.auto_accepted
        )
        is_manual = (
            item.confidence_band == ConfidenceBand.manual_required
            or item.status == ReviewStatus.manual_required
        )

        if is_locked:
            review_status = "confirmed"
            band_str = "auto_accepted"
            is_confirmed = True
            node_val = str(raw_val or "0")
        elif is_auto:
            review_status = "auto_accepted"
            band_str = "auto_accepted"
            is_confirmed = True
            node_val = str(raw_val or "0")
        elif is_manual:
            review_status = "manual_required"
            band_str = "manual_required"
            is_confirmed = False
            node_val = ""  # Left empty per Invariant I3
        else:
            review_status = "needs_review"
            band_str = "needs_review"
            is_confirmed = False
            node_val = str(raw_val or "0")

        # 6. Create valid FormulaInputNode
        node = FormulaInputNode(
            node_id=f"node_{idx}_{effective_label}",
            normalized_label=effective_label,
            value=node_val,
            label=item.label,
            page=item.page,
            bbox=item.bbox,
            source_file=item.source_file,
            locator=getattr(item, "locator", None),
            record_index=idx,
            is_hardcode=(item.confidence_band == ConfidenceBand.manual_required),
            statement_type=item.statement_type,
            confidence_band=band_str,
            confidence_score=item.confidence_score,
            flags=list(item.flags),
            review_status=review_status,
            is_confirmed=is_confirmed,
        )
        nodes.append(node)

    error_message: str | None = None
    if len(nodes) == 0:
        error_message = "No confirmed review records available for formula generation."

    return FormulaInputBatch(
        nodes=nodes,
        errors=errors,
        total_records_received=len(items),
        confirmed_count=len(nodes) if not include_unreviewed else sum(1 for n in nodes if n.is_confirmed),
        excluded_count=excluded_count,
        error_message=error_message,
    )
