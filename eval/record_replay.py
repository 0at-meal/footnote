"""
Record and Replay Harness for LLM Classifier Responses (FN-011).

Enables 100% deterministic, free, and offline CI/PR evaluation runs by caching
and replaying LLM classification outputs. Nightly runs can execute against live APIs.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.classification.client import GroqClassifierClient
from app.classification.models import (
    ClassifierInputPayload,
    ClassifierRawResponse,
)

logger = logging.getLogger(__name__)

DEFAULT_CASSETTE_PATH = Path(__file__).resolve().parent / "cassettes" / "classifier_cassette.json"


class RecordReplayClassifierClient(GroqClassifierClient):
    """
    Classifier client supporting replay (default offline CI) and record (live API) modes.
    """

    def __init__(
        self,
        mode: str = "replay",  # 'replay', 'record', or 'mock'
        cassette_path: Path | str | None = None,
        real_client: GroqClassifierClient | None = None,
    ) -> None:
        self.mode = mode
        self.cassette_path = Path(cassette_path) if cassette_path else DEFAULT_CASSETTE_PATH
        self.real_client = real_client
        self._cache: dict[str, dict[str, Any]] = {}
        self._load_cassette()

    def _load_cassette(self) -> None:
        if self.cassette_path.exists():
            try:
                self._cache = json.loads(self.cassette_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Could not read cassette at %s: %e", self.cassette_path, e)
                self._cache = {}

    def _save_cassette(self) -> None:
        self.cassette_path.parent.mkdir(parents=True, exist_ok=True)
        self.cassette_path.write_text(json.dumps(self._cache, indent=2, sort_keys=True), encoding="utf-8")

    def _make_key(self, payload: ClassifierInputPayload) -> str:
        norm_label = payload.label.strip().lower()
        context_hint = (payload.structural_context or "").strip().lower()
        return f"{norm_label}::{context_hint}"

    def classify(
        self, payload: ClassifierInputPayload
    ) -> ClassifierRawResponse:
        key = self._make_key(payload)

        # 1. Replay mode
        if self.mode == "replay":
            if key in self._cache:
                entry = self._cache[key]
                return ClassifierRawResponse(
                    label=entry["label"],
                    confidence=entry["confidence"],
                )
            # Fallback deterministic taxonomy mapping
            fallback_label = self._deterministic_fallback(payload.label)
            return ClassifierRawResponse(label=fallback_label, confidence=0.95)

        # 2. Record mode
        if self.mode == "record" and self.real_client and self.real_client.is_configured:
            resp = self.real_client.classify(payload)
            self._cache[key] = {
                "label": resp.label,
                "confidence": resp.confidence,
            }
            self._save_cassette()
            return resp

        # 3. Mock mode
        fallback_label = self._deterministic_fallback(payload.label)
        return ClassifierRawResponse(label=fallback_label, confidence=0.95)

    def classify_line_item(
        self, payload: ClassifierInputPayload
    ) -> ClassifierRawResponse:
        return self.classify(payload)

    def _deterministic_fallback(self, raw_label: str) -> str:
        low = raw_label.lower().strip()
        if "net income" in low or "net loss" in low:
            return "Net Income"
        if "operating income" in low or "operating profit" in low:
            return "Operating Income"
        if "tax" in low:
            return "Income Tax Expense"
        if "interest" in low:
            return "Interest Expense"
        if "depreciation" in low or "amortization" in low:
            return "Depreciation & Amortization"
        if "stock" in low or "share-based" in low:
            return "Stock-based compensation"
        if "restructur" in low or "reposition" in low:
            return "Restructuring Charges"
        if "litigation" in low or "settlement" in low:
            return "Litigation settlement"
        if "acquisition" in low or "merger" in low or "transaction" in low:
            return "M&A transaction costs"
        if "ebitda" in low:
            return "Adjusted EBITDA"
        return "Other non-operating expense"
