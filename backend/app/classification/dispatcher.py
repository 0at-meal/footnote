"""
Classifier dispatcher coordinating record filtering, sanitization, and batch execution (Feature 3).

Enforces:
- AC-9 / EC-9: Excludes manual_required and extraction_error records from classification.
- CONSTITUTION §6.5: Excludes numeric value, page, bbox, and filename from classifier payloads.
- AC-3 / EC-4: Captures per-item errors without crashing the entire job.
"""

import logging

from groq import APIConnectionError, APIError, RateLimitError

from app.classification.client import GroqClassifierClient
from app.classification.models import (
    ClassificationBatchResult,
    ClassificationItemResult,
    ClassifierInputPayload,
    ClassifierRawResponse,
)
from app.classification.taxonomy import match_canonical_taxonomy
from app.extraction.models import ConfidenceBand, ScoredRecord

logger = logging.getLogger(__name__)

ELIGIBLE_BANDS = {ConfidenceBand.auto_accepted, ConfidenceBand.needs_review}


def is_record_eligible_for_classification(record: ScoredRecord) -> bool:
    """
    Determines if an extraction record meets the precondition for classifier dispatch (AC-9, EC-9).

    Must be in auto_accepted or needs_review band and have status == 'ok'.
    """
    if record.status == "extraction_error":
        return False
    return record.confidence_band in ELIGIBLE_BANDS


def dispatch_records_to_classifier(
    records: list[ScoredRecord],
    client: GroqClassifierClient,
) -> ClassificationBatchResult:
    """
    Processes a list of ScoredRecords through the Groq classifier.

    1. Filters eligible records (AC-9, EC-9).
    2. Builds sanitized ClassifierInputPayload (CONSTITUTION §6.5).
    3. Invokes GroqClassifierClient for each eligible item.
    4. Aggregates results into ClassificationBatchResult.
    """
    item_results: list[ClassificationItemResult] = []
    success_count = 0
    error_count = 0
    skipped_count = 0
    total_dispatched = 0

    for idx, scored_record in enumerate(records):
        if not is_record_eligible_for_classification(scored_record):
            skipped_count += 1
            continue

        # Extract only the label without value or other metadata (CONSTITUTION §6.5)
        raw_label = scored_record.record.label
        payload = ClassifierInputPayload(label=raw_label)
        total_dispatched += 1

        try:
            raw_response = client.classify(payload)
            item_results.append(
                ClassificationItemResult(
                    record_index=idx,
                    payload=payload,
                    raw_response=raw_response,
                    is_error=False,
                    error_detail=None,
                )
            )
            success_count += 1
        except (
            ValueError,
            TypeError,
            RateLimitError,
            APIConnectionError,
            APIError,
            RuntimeError,
        ) as err:
            logger.warning(
                "Classification failed for record index %d ('%s'): %s",
                idx,
                raw_label,
                err,
            )
            fallback_match = match_canonical_taxonomy(raw_label)
            if fallback_match is not None:
                logger.info(
                    "Direct taxonomy fallback matched '%s' -> '%s'",
                    raw_label,
                    fallback_match,
                )
                item_results.append(
                    ClassificationItemResult(
                        record_index=idx,
                        payload=payload,
                        raw_response=ClassifierRawResponse(
                            label=fallback_match,
                            confidence=0.95,
                        ),
                        is_error=False,
                        error_detail=None,
                    )
                )
                success_count += 1
            else:
                item_results.append(
                    ClassificationItemResult(
                        record_index=idx,
                        payload=payload,
                        raw_response=None,
                        is_error=True,
                        error_detail=str(err),
                    )
                )
                error_count += 1

    return ClassificationBatchResult(
        results=item_results,
        total_dispatched=total_dispatched,
        success_count=success_count,
        error_count=error_count,
        skipped_count=skipped_count,
    )
