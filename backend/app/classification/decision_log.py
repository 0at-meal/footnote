"""
Decision log persistence and builder for the classification stage (Feature 3 Step 4).

Enforces:
- spec.md §6: Machine-readable newline-delimited JSON (JSONL) append-only decision log.
- spec.md AC-2: Zero numeric fields in input payload or classifier response.
- spec.md AC-7: Durable persistence and retrieval of every classifier call.
- spec.md EC-10: Durable logging guarantee.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from app.classification.models import (
    ClassificationBatchResult,
    DecisionLogEntry,
    TaxonomyStatus,
)
from app.classification.taxonomy import check_label_against_taxonomy

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"


def build_log_entries(
    job_id: str,
    batch_result: ClassificationBatchResult,
    active_taxonomy: list[str],
) -> list[DecisionLogEntry]:
    """
    Constructs DecisionLogEntry objects for all items dispatched in a classification batch.
    """
    entries: list[DecisionLogEntry] = []
    timestamp = datetime.now(timezone.utc).isoformat()

    for item in batch_result.results:
        if item.is_error or item.raw_response is None:
            entries.append(
                DecisionLogEntry(
                    job_id=job_id,
                    record_index=item.record_index,
                    timestamp=timestamp,
                    input_payload=item.payload,
                    raw_response=None,
                    taxonomy_status=TaxonomyStatus.pending_taxonomy_confirmation,
                    resulting_state="classification_error",
                    error_detail=item.error_detail,
                )
            )
        else:
            match_res = check_label_against_taxonomy(
                item.raw_response.label, active_taxonomy
            )
            resulting_state = (
                "confirmed" if match_res.is_matched else "pending_confirmation"
            )

            entries.append(
                DecisionLogEntry(
                    job_id=job_id,
                    record_index=item.record_index,
                    timestamp=timestamp,
                    input_payload=item.payload,
                    raw_response=item.raw_response,
                    taxonomy_status=match_res.status,
                    resulting_state=resulting_state,
                    error_detail=None,
                )
            )

    return entries


class DecisionLogRepository:
    """
    Persist and read machine-readable decision logs under data/results/<job_id>_decision_log.jsonl.
    """

    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR) -> None:
        self._data_dir = data_dir
        self._results_dir = data_dir / "results"

    def _ensure_dirs(self) -> None:
        """Create data/results/ if missing."""
        self._results_dir.mkdir(parents=True, exist_ok=True)

    def log_batch_calls(
        self,
        job_id: str,
        entries: list[DecisionLogEntry],
    ) -> Path:
        """
        Persists decision log entries to data/results/<job_id>_decision_log.jsonl in JSONL format.

        Uses atomic write via temporary file rename (CONSTITUTION §1.9, EC-10).
        """
        self._ensure_dirs()
        dest_path = self._results_dir / f"{job_id}_decision_log.jsonl"
        tmp_path = self._results_dir / f"{job_id}_decision_log.jsonl.tmp"

        try:
            with tmp_path.open("w", encoding="utf-8") as f:
                for entry in entries:
                    f.write(entry.model_dump_json() + "\n")
            os.replace(tmp_path, dest_path)
            return dest_path
        except (OSError, ValueError) as err:
            logger.error(
                "Failed to write decision log for job %s: %s (EC-10)", job_id, err
            )
            raise

    def get_decision_log(self, job_id: str) -> list[DecisionLogEntry] | None:
        """
        Retrieves DecisionLogEntry records for job_id from data/results/<job_id>_decision_log.jsonl.
        """
        target_path = self._results_dir / f"{job_id}_decision_log.jsonl"
        if not target_path.exists():
            return None

        entries: list[DecisionLogEntry] = []
        try:
            with target_path.open("r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        entries.append(DecisionLogEntry.model_validate_json(stripped))
            return entries
        except (json.JSONDecodeError, OSError, ValueError) as err:
            logger.error("Failed to read decision log for job %s: %s", job_id, err)
            return None
