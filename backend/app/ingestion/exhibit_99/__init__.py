"""
8-K EX-99.1 Earnings Release Support Package (FN-022).
"""

from app.ingestion.exhibit_99.detector import (
    classify_exhibit_format,
    detect_earnings_release_exhibit,
    is_guidance_text,
    is_item_2_02_text,
)
from app.ingestion.exhibit_99.differ import diff_bridges, merge_dedupe_bridges
from app.ingestion.exhibit_99.extractor import Exhibit99Extractor
from app.ingestion.exhibit_99.models import (
    BridgeDiffReport,
    CanonicalBridgeResult,
    DiffItem,
    EarningsReleaseMetadata,
    ExhibitFormat,
)

__all__ = [
    "BridgeDiffReport",
    "CanonicalBridgeResult",
    "DiffItem",
    "EarningsReleaseMetadata",
    "Exhibit99Extractor",
    "ExhibitFormat",
    "classify_exhibit_format",
    "detect_earnings_release_exhibit",
    "diff_bridges",
    "is_guidance_text",
    "is_item_2_02_text",
    "merge_dedupe_bridges",
]
