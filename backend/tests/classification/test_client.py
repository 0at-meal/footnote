"""
Unit tests for GroqClassifierClient (Feature 3 Step 1).

Validates:
- Successful API call and JSON response parsing (AC-2)
- Rate limiting and 429 exponential backoff (AC-1, AC-8)
- Payload truncation for oversized footnote text (EC-7)
- Malformed response rejection and error surfacing (AC-3, EC-1, EC-2)
- Daily request limit enforcement (EC-8)
"""

from unittest.mock import MagicMock, patch

import pytest
from app.classification.client import (
    CLASSIFIER_SYSTEM_PROMPT,
    MAX_LABEL_CHARS,
    MAX_RPD,
    GroqClassifierClient,
)
from app.classification.models import ClassifierInputPayload
from app.classification.taxonomy import SEED_TAXONOMY
from groq import APIConnectionError, RateLimitError


def create_mock_completion(content: str) -> MagicMock:
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    return mock_completion


def test_classify_successful_response() -> None:
    mock_groq = MagicMock()
    mock_groq.chat.completions.create.return_value = create_mock_completion(
        '{"label": "Stock-Based Compensation", "confidence": 0.98}'
    )

    client = GroqClassifierClient(client=mock_groq)
    payload = ClassifierInputPayload(label="Stock compensation expense")

    response = client.classify(payload)
    assert response.label == "Stock-Based Compensation"
    assert response.confidence == 0.98
    assert mock_groq.chat.completions.create.call_count == 1


def test_classify_retry_on_429_exponential_backoff() -> None:
    mock_groq = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.headers = {}
    mock_response.json.return_value = {"error": {"message": "Rate limit exceeded"}}

    rate_limit_err = RateLimitError(
        message="Rate limit exceeded",
        response=mock_response,
        body=None,
    )

    # First call raises 429, second call succeeds
    mock_groq.chat.completions.create.side_effect = [
        rate_limit_err,
        create_mock_completion('{"label": "Litigation Charges", "confidence": 0.90}'),
    ]

    client = GroqClassifierClient(
        client=mock_groq,
        max_retries=2,
        initial_retry_delay=0.01,
    )
    payload = ClassifierInputPayload(label="Legal settlement cost")

    with patch("time.sleep") as mock_sleep:
        response = client.classify(payload)

    assert response.label == "Litigation Charges"
    assert response.confidence == 0.90
    assert mock_groq.chat.completions.create.call_count == 2
    mock_sleep.assert_called_once_with(0.01)


def test_classify_max_retries_exceeded_raises() -> None:
    mock_groq = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.headers = {}
    mock_response.json.return_value = {"error": {"message": "Rate limit exceeded"}}

    rate_limit_err = RateLimitError(
        message="Rate limit exceeded",
        response=mock_response,
        body=None,
    )

    mock_groq.chat.completions.create.side_effect = rate_limit_err

    client = GroqClassifierClient(
        client=mock_groq,
        max_retries=2,
        initial_retry_delay=0.01,
    )
    payload = ClassifierInputPayload(label="Legal settlement cost")

    with patch("time.sleep"), pytest.raises(RateLimitError):
        client.classify(payload)

    # 1 initial attempt + 2 retries = 3 attempts total before raising
    assert mock_groq.chat.completions.create.call_count == 3


def test_classify_malformed_json_raises_value_error() -> None:
    mock_groq = MagicMock()
    mock_groq.chat.completions.create.return_value = create_mock_completion(
        "Invalid JSON not parseable"
    )

    client = GroqClassifierClient(client=mock_groq)
    payload = ClassifierInputPayload(label="Amortization")

    with pytest.raises(ValueError, match="Malformed JSON response"):
        client.classify(payload)


def test_classify_invalid_schema_missing_fields_raises_value_error() -> None:
    mock_groq = MagicMock()
    mock_groq.chat.completions.create.return_value = create_mock_completion(
        '{"unexpected_key": "some_value"}'
    )

    client = GroqClassifierClient(client=mock_groq)
    payload = ClassifierInputPayload(label="Amortization")

    with pytest.raises(
        ValueError, match="Classifier response failed schema validation"
    ):
        client.classify(payload)


def test_classify_invalid_confidence_bounds_raises_value_error() -> None:
    mock_groq = MagicMock()
    mock_groq.chat.completions.create.return_value = create_mock_completion(
        '{"label": "Amortization of Intangibles", "confidence": 1.5}'
    )

    client = GroqClassifierClient(client=mock_groq)
    payload = ClassifierInputPayload(label="Amortization")

    with pytest.raises(
        ValueError, match="Classifier response failed schema validation"
    ):
        client.classify(payload)


def test_classify_truncates_oversized_payload() -> None:
    mock_groq = MagicMock()
    mock_groq.chat.completions.create.return_value = create_mock_completion(
        '{"label": "Restructuring", "confidence": 0.85}'
    )

    client = GroqClassifierClient(client=mock_groq)
    long_label = "A" * (MAX_LABEL_CHARS + 500)
    payload = ClassifierInputPayload(label=long_label)

    response = client.classify(payload)
    assert response.label == "Restructuring"

    # Verify that the message passed to completions.create used truncated text
    call_args = mock_groq.chat.completions.create.call_args
    sent_messages = call_args.kwargs["messages"]
    user_content = sent_messages[1]["content"]
    assert "[TRUNCATED]" in user_content
    assert len(user_content) < len(long_label)


def test_classify_daily_rpd_cap_enforcement() -> None:
    mock_groq = MagicMock()
    client = GroqClassifierClient(client=mock_groq)
    client._daily_request_count = MAX_RPD

    payload = ClassifierInputPayload(label="Tax adjustment")

    with pytest.raises(RuntimeError, match="Daily request cap"):
        client.classify(payload)

    assert mock_groq.chat.completions.create.call_count == 0


def test_classify_api_connection_error_propagates() -> None:
    mock_groq = MagicMock()
    mock_request = MagicMock()
    mock_groq.chat.completions.create.side_effect = APIConnectionError(
        request=mock_request
    )

    client = GroqClassifierClient(client=mock_groq)
    payload = ClassifierInputPayload(label="Tax adjustment")

    with pytest.raises(APIConnectionError):
        client.classify(payload)


def test_classifier_system_prompt_contains_seed_taxonomy() -> None:
    for category in SEED_TAXONOMY:
        assert category in CLASSIFIER_SYSTEM_PROMPT

    assert (
        "You MUST select the most accurate category from the following allowed taxonomy list"
        in CLASSIFIER_SYSTEM_PROMPT
    )
    assert '"label": (string)' in CLASSIFIER_SYSTEM_PROMPT
    assert '"confidence": (float)' in CLASSIFIER_SYSTEM_PROMPT
