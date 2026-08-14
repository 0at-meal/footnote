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
)

__all__ = [
    "ClassificationBatchResult",
    "ClassificationItemResult",
    "ClassifierInputPayload",
    "ClassifierRawResponse",
    "GroqClassifierClient",
    "dispatch_records_to_classifier",
    "is_record_eligible_for_classification",
]
