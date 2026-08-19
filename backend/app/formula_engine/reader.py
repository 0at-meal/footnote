"""
Pure reader and validator for formula engine inputs (Feature 4 Step 1).

Enforces CONSTITUTION §1.4:
- 100% pure function: no I/O, no clock, no random, no global mutable state.
- Idempotent and deterministic for identical input data.
"""

from app.classification.models import ClassifiedRecord
from app.extraction.models import ConfidenceBand
from app.formula_engine.models import (
    FormulaInputBatch,
    FormulaInputError,
    FormulaInputNode,
)
from app.review.models import ReviewItem, ReviewStatus

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


def read_formula_inputs(records: list[ClassifiedRecord]) -> FormulaInputBatch:
    """
    Extracts and validates authoritative input nodes from a batch of ClassifiedRecord objects.

    Rules (AC-8, AC-9, EC-1, EC-2, EC-3, EC-5, EC-8):
    1. Only confirmed records with non-empty normalized_label are selected.
    2. Pending, unconfirmed, and extraction_error records are excluded from the engine.
    3. Provenance fields (value, page, bbox, source_file) are validated and passed without modification.
    4. Out-of-bounds bbox (< 0.0 or > 1000.0) or invalid provenance surfaces as FormulaInputError.
    5. Zero valid confirmed records sets top-level error message (EC-5).
    """
    nodes: list[FormulaInputNode] = []
    errors: list[FormulaInputError] = []
    excluded_count = 0

    for idx, classified_record in enumerate(records):
        # 1. Check if record is confirmed and has a valid normalized_label (AC-8)
        if (
            not classified_record.is_confirmed
            or not classified_record.normalized_label
            or not classified_record.normalized_label.strip()
        ):
            excluded_count += 1
            continue

        raw_record = classified_record.record.record

        # 2. Validate provenance fields (AC-9, EC-8)
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
                    label=classified_record.normalized_label,
                    source_file=raw_record.source_file or None,
                )
            )
            continue

        # 3. Create valid FormulaInputNode
        node = FormulaInputNode(
            node_id=f"node_{idx}_{classified_record.normalized_label}",
            normalized_label=classified_record.normalized_label.strip(),
            value=raw_record.value,
            label=raw_record.label,
            page=raw_record.page,
            bbox=raw_record.bbox,
            source_file=raw_record.source_file,
            record_index=idx,
            is_hardcode=False,
        )
        nodes.append(node)

    error_message: str | None = None
    if len(nodes) == 0:
        error_message = "No confirmed records available for formula generation."

    return FormulaInputBatch(
        nodes=nodes,
        errors=errors,
        total_records_received=len(records),
        confirmed_count=len(nodes),
        excluded_count=excluded_count,
        error_message=error_message,
    )


def read_formula_inputs_from_review(items: list[ReviewItem]) -> FormulaInputBatch:
    """
    Extracts and validates authoritative input nodes from a list of ReviewItem objects (Feature 5 -> Feature 4).

    Rules:
    1. Selects items that are locked (status == ReviewStatus.locked) or confirmed with a valid normalized_label.
    2. Items marked extraction_error or without normalized_label/label are excluded.
    3. Provenance fields (value, page, bbox, source_file) are validated and passed without modification.
    4. Out-of-bounds bbox (< 0.0 or > 1000.0) or invalid provenance surfaces as FormulaInputError.
    5. Returns FormulaInputBatch with nodes, errors, and metadata.
    """
    nodes: list[FormulaInputNode] = []
    errors: list[FormulaInputError] = []
    excluded_count = 0

    for idx, item in enumerate(items):
        # 1. Check if item is confirmed / locked with a non-empty normalized_label
        effective_label = (item.normalized_label or "").strip()
        if not effective_label and item.status == ReviewStatus.locked and item.label.strip():
            effective_label = item.label.strip()

        is_eligible = (item.status == ReviewStatus.locked) or (
            item.status in (ReviewStatus.auto_accepted, ReviewStatus.needs_review)
            and bool(item.normalized_label and item.normalized_label.strip())
        )

        if not is_eligible or not effective_label:
            excluded_count += 1
            continue

        # 2. Validate provenance fields (AC-9, EC-8)
        provenance_error: str | None = None
        if not item.source_file or not item.source_file.strip():
            provenance_error = "Missing or empty source_file"
        elif item.page < 1:
            provenance_error = f"Invalid page number {item.page} (must be >= 1)"
        elif not isinstance(item.bbox, dict):
            provenance_error = f"Invalid bbox type: expected dict, got {type(item.bbox).__name__}"
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

        # 3. Create valid FormulaInputNode
        node = FormulaInputNode(
            node_id=f"node_{idx}_{effective_label}",
            normalized_label=effective_label,
            value=item.value,
            label=item.label,
            page=item.page,
            bbox=item.bbox,
            source_file=item.source_file,
            record_index=idx,
            is_hardcode=(item.confidence_band == ConfidenceBand.manual_required),
        )
        nodes.append(node)

    error_message: str | None = None
    if len(nodes) == 0:
        error_message = "No confirmed review records available for formula generation."

    return FormulaInputBatch(
        nodes=nodes,
        errors=errors,
        total_records_received=len(items),
        confirmed_count=len(nodes),
        excluded_count=excluded_count,
        error_message=error_message,
    )
