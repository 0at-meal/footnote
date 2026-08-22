"""
Record assembly module for Feature 2, Step 3.

Scope:
    Assembles normalized extraction items (NormalizedItem) into canonical
    ExtractedRecord instances with the frozen 5-field schema.

Isolation (CONSTITUTION §3.8, §3.2):
    This module must NEVER import from classification/, formula_engine/, excel_export/,
    or audit_report/.
"""

from app.extraction.models import ExtractedRecord, NormalizedItem


def assemble_record(item: NormalizedItem) -> ExtractedRecord:
    """
    Assemble a single NormalizedItem into the canonical 5-field ExtractedRecord schema.

    Args:
        item: The normalized extraction item from Step 2.

    Returns:
        An ExtractedRecord instance with bbox formatted as a W3C dict.
    """
    bbox_dict: dict[str, float] = {
        "x0": item.bbox.x0,
        "y0": item.bbox.y0,
        "x1": item.bbox.x1,
        "y1": item.bbox.y1,
    }

    return ExtractedRecord(
        value=item.value,
        label=item.label,
        page=item.page,
        bbox=bbox_dict,
        source_file=item.source_file,
        is_reconciliation_candidate=item.is_reconciliation_candidate,
    )


def assemble_records(items: list[NormalizedItem]) -> list[ExtractedRecord]:
    """
    Assemble a list of NormalizedItem objects into canonical ExtractedRecord objects.

    Maintains strict input list ordering (NFR1 determinism).

    Args:
        items: List of normalized extraction items.

    Returns:
        List of ExtractedRecord instances.
    """
    return [assemble_record(item) for item in items]
