"""
Classification and normalization stage package (Feature 3).
"""

from app.classification.client import GroqClassifierClient
from app.classification.decision_log import (
    DecisionLogRepository,
    build_log_entries,
)
from app.classification.dispatcher import (
    dispatch_records_to_classifier,
    is_record_eligible_for_classification,
)
from app.classification.models import (
    ClassificationBatchResult,
    ClassificationItemResult,
    ClassifiedRecord,
    ClassifierInputPayload,
    ClassifierRawResponse,
    DecisionLogEntry,
    DecisionLogResponse,
    TaxonomyCheckResult,
    TaxonomyStatus,
)
from app.classification.normalizer import normalize_records
from app.classification.repository import ClassificationRepository
from app.classification.router import router as classification_router
from app.classification.taxonomy import (
    SEED_TAXONOMY,
    TaxonomyRepository,
    check_label_against_taxonomy,
)

__all__ = [
    "SEED_TAXONOMY",
    "ClassificationBatchResult",
    "ClassificationItemResult",
    "ClassificationRepository",
    "ClassifiedRecord",
    "ClassifierInputPayload",
    "ClassifierRawResponse",
    "DecisionLogEntry",
    "DecisionLogRepository",
    "DecisionLogResponse",
    "GroqClassifierClient",
    "TaxonomyCheckResult",
    "TaxonomyRepository",
    "TaxonomyStatus",
    "build_log_entries",
    "check_label_against_taxonomy",
    "classification_router",
    "dispatch_records_to_classifier",
    "is_record_eligible_for_classification",
    "normalize_records",
]
