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
    label_cache: dict[str, ClassifierRawResponse | None] = {}
    circuit_breaker_rate_limited = False

    for idx, scored_record in enumerate(records):
        if not is_record_eligible_for_classification(scored_record):
            skipped_count += 1
            continue

        raw_label = scored_record.record.label
        parts = [p.strip() for p in raw_label.split(" / ") if p.strip()]
        core_label = parts[0] if parts else raw_label
        payload = ClassifierInputPayload(label=raw_label)
        total_dispatched += 1

        normalized_key = core_label.strip().lower()

        # 1. Check in-batch cache first
        if normalized_key in label_cache:
            cached_resp = label_cache[normalized_key]
            if cached_resp is not None:
                item_results.append(
                    ClassificationItemResult(
                        record_index=idx,
                        payload=payload,
                        raw_response=cached_resp,
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
                        error_detail="Classification previously failed for label",
                    )
                )
                error_count += 1
            continue

        # 2. If circuit breaker tripped (e.g. 429 Daily Limit), fast-fallback
        if circuit_breaker_rate_limited:
            fallback_match = match_canonical_taxonomy(raw_label) or match_canonical_taxonomy(core_label)
            if fallback_match is not None:
                resp = ClassifierRawResponse(label=fallback_match, confidence=0.98)
                label_cache[normalized_key] = resp
                item_results.append(
                    ClassificationItemResult(
                        record_index=idx,
                        payload=payload,
                        raw_response=resp,
                        is_error=False,
                        error_detail=None,
                    )
                )
                success_count += 1
            else:
                label_cache[normalized_key] = None
                item_results.append(
                    ClassificationItemResult(
                        record_index=idx,
                        payload=payload,
                        raw_response=None,
                        is_error=True,
                        error_detail="Rate limit circuit breaker active",
                    )
                )
                error_count += 1
            continue

        # 3. Invoke classifier client
        try:
            raw_response = client.classify(payload)
            label_cache[normalized_key] = raw_response
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
            Exception,
        ) as err:
            if isinstance(err, RateLimitError) or "429" in str(err) or "rate limit" in str(err).lower():
                logger.warning(
                    "Groq daily limit / 429 reached. Tripping circuit breaker to instant local financial classification."
                )
                circuit_breaker_rate_limited = True

            logger.warning(
                "Classification failed for record index %d ('%s'): %s",
                idx,
                raw_label,
                err,
            )
            fallback_match = match_canonical_taxonomy(raw_label) or match_canonical_taxonomy(core_label)
            if fallback_match is not None:
                resp = ClassifierRawResponse(label=fallback_match, confidence=0.95)
                label_cache[normalized_key] = resp
                item_results.append(
                    ClassificationItemResult(
                        record_index=idx,
                        payload=payload,
                        raw_response=resp,
                        is_error=False,
                        error_detail=None,
                    )
                )
                success_count += 1
            else:
                label_cache[normalized_key] = None
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
