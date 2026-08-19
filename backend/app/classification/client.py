"""
Groq API client and rate-limiting wrapper for line item classification (Feature 3).

Adheres to:
- CONSTITUTION §1.2: Public interface never exposes or accepts numeric return fields.
- CONSTITUTION §4.7: Model is Groq API openai/gpt-oss-120b.
- CONSTITUTION §4.8: Free-tier rate limits (30 RPM, 8,000 TPM, 1,000 RPD, 200,000 TPD).
- spec.md AC-1, AC-2, AC-3, AC-8, EC-1, EC-2, EC-4, EC-7, EC-8.
"""

import json
import logging
import os
import time

from groq import APIConnectionError, APIError, Groq, RateLimitError
from groq.types.chat import ChatCompletionMessageParam
from pydantic import ValidationError

from app.classification.models import (
    ClassifierInputPayload,
    ClassifierRawResponse,
)
from app.classification.taxonomy import SEED_TAXONOMY

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "openai/gpt-oss-120b"
MAX_RPM = 30
MAX_TPM = 8000
MAX_RPD = 1000
MAX_LABEL_CHARS = 2000  # Guard against oversized footnote text (EC-7)
DEFAULT_MAX_RETRIES = 3
INITIAL_RETRY_DELAY_SEC = 1.0

_TAXONOMY_LIST_STR = "\n".join(f"- {category}" for category in SEED_TAXONOMY)

CLASSIFIER_SYSTEM_PROMPT = (
    "You are a financial line-item taxonomy classifier. "
    "Given an extracted line item label and its structural context from a financial filing, "
    "classify the item into a standardized non-GAAP reconciliation category.\n\n"
    "You MUST select the most accurate category from the following allowed taxonomy list when applicable:\n"
    f"{_TAXONOMY_LIST_STR}\n\n"
    "If no category fits, respond with the closest standard financial category name.\n\n"
    "You must respond ONLY with a valid JSON object containing exactly two fields:\n"
    '  "label": (string) the standardized category name,\n'
    '  "confidence": (float) your classification confidence between 0.0 and 1.0.\n'
    "Do NOT include any numerical values, amounts, formulas, or extra commentary."
)


class GroqClassifierClient:
    """
    Client for Groq API classification with rate limiting, retry backoff, and strict schema validation.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        client: Groq | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_retry_delay: float = INITIAL_RETRY_DELAY_SEC,
    ) -> None:
        self.model = model
        self.max_retries = max_retries
        self.initial_retry_delay = initial_retry_delay

        if client is not None:
            self._client: Groq = client
        else:
            resolved_key = api_key or os.environ.get("GROQ_API_KEY", "")
            self._client = Groq(api_key=resolved_key)

        # Rate tracking
        self._request_timestamps: list[float] = []
        self._daily_request_count: int = 0
        self._daily_reset_timestamp: float = time.time()

    def _enforce_rate_limits(self) -> None:
        """
        Throttles outbound calls to remain within 30 RPM and tracks daily count.
        """
        now = time.time()

        # Reset daily counter every 24 hours (86400 seconds)
        if now - self._daily_reset_timestamp >= 86400.0:
            self._daily_request_count = 0
            self._daily_reset_timestamp = now

        if self._daily_request_count >= MAX_RPD:
            raise RuntimeError(
                f"Daily request cap of {MAX_RPD} RPD reached (EC-8). Cannot dispatch further calls."
            )

        # Purge timestamps older than 60 seconds
        self._request_timestamps = [ts for ts in self._request_timestamps if now - ts < 60.0]

        if len(self._request_timestamps) >= MAX_RPM:
            oldest = self._request_timestamps[0]
            sleep_duration = max(0.0, 60.0 - (now - oldest) + 0.1)
            logger.info("Throttling Groq requests: sleeping for %.2fs to observe 30 RPM cap", sleep_duration)
            time.sleep(sleep_duration)

        current_time = time.time()
        self._request_timestamps.append(current_time)
        self._daily_request_count += 1

    def _truncate_payload_if_oversized(self, payload: ClassifierInputPayload) -> ClassifierInputPayload:
        """
        Truncate oversized label or context to prevent breaching the 8,000 TPM limit (EC-7).
        """
        truncated_label = payload.label
        if len(truncated_label) > MAX_LABEL_CHARS:
            truncated_label = truncated_label[:MAX_LABEL_CHARS] + " [TRUNCATED]"

        truncated_context = payload.structural_context
        if truncated_context is not None and len(truncated_context) > MAX_LABEL_CHARS:
            truncated_context = truncated_context[:MAX_LABEL_CHARS] + " [TRUNCATED]"

        return ClassifierInputPayload(
            label=truncated_label,
            structural_context=truncated_context,
        )

    def classify(self, payload: ClassifierInputPayload) -> ClassifierRawResponse:
        """
        Dispatches a single input payload to Groq and parses the response into ClassifierRawResponse.

        Handles:
        - Rate limiting (AC-1)
        - 429 exponential backoff (AC-8)
        - Payload truncation (EC-7)
        - Strict numeric-free JSON parsing (AC-2, AC-3, EC-1, EC-2)
        """
        sanitized_payload = self._truncate_payload_if_oversized(payload)

        prompt_user_content = f"Item Label: {sanitized_payload.label}"
        if sanitized_payload.structural_context:
            prompt_user_content += f"\nStructural Context: {sanitized_payload.structural_context}"

        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt_user_content},
        ]

        attempt = 0
        while True:
            try:
                self._enforce_rate_limits()

                completion = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.0,
                )

                choice = completion.choices[0]
                content = choice.message.content or ""
                return self._parse_and_validate_response(content)

            except RateLimitError as err:
                attempt += 1
                if attempt > self.max_retries:
                    logger.error("Exceeded max retries (%d) for rate limit: %s", self.max_retries, err)
                    raise

                delay = self.initial_retry_delay * (2 ** (attempt - 1))
                logger.warning(
                    "Groq API 429 RateLimit encountered. Backing off for %.2fs (attempt %d/%d)",
                    delay,
                    attempt,
                    self.max_retries,
                )
                time.sleep(delay)

            except APIConnectionError as err:
                logger.error("Groq API connection error: %s", err)
                raise

            except APIError as err:
                logger.error("Groq API error: %s", err)
                raise

    def _parse_and_validate_response(self, raw_content: str) -> ClassifierRawResponse:
        """
        Parse raw JSON response and enforce strict numeric-free Pydantic schema (AC-3, EC-1, EC-2).
        """
        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError as err:
            raise ValueError(f"Malformed JSON response from Groq classifier: {raw_content!r}") from err

        if not isinstance(data, dict):
            raise TypeError(f"Expected JSON object from classifier, got {type(data).__name__}")

        # Check for disallowed numeric output keys beyond confidence
        disallowed_keys = [k for k in data if k not in ("label", "confidence")]
        if disallowed_keys:
            logger.warning("Classifier returned unexpected extra fields: %s", disallowed_keys)

        try:
            return ClassifierRawResponse(
                label=str(data.get("label", "")),
                confidence=float(data.get("confidence", -1.0)),
            )
        except (ValidationError, TypeError, ValueError) as err:
            raise ValueError(f"Classifier response failed schema validation: {raw_content!r}") from err
