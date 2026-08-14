"""
Classification and normalization stage package (Feature 3).
"""

from app.classification.client import GroqClassifierClient
from app.classification.dispatcher import (
    dispatch_records_to_classifier,
    is_record_eligible_for_classification,
)
from app.classification.models import (
    ClassificationBatchResult,
    ClassificationItemResult,
    ClassifierInputPayload,
    ClassifierRawResponse,
    TaxonomyCheckResult,
    TaxonomyStatus,
)
from app.classification.taxonomy import (
    SEED_TAXONOMY,
    TaxonomyRepository,
    check_label_against_taxonomy,
)

__all__ = [
    "SEED_TAXONOMY",
    "ClassificationBatchResult",
    "ClassificationItemResult",
    "ClassifierInputPayload",
    "ClassifierRawResponse",
    "GroqClassifierClient",
    "TaxonomyCheckResult",
    "TaxonomyRepository",
    "TaxonomyStatus",
    "check_label_against_taxonomy",
    "dispatch_records_to_classifier",
    "is_record_eligible_for_classification",
]
