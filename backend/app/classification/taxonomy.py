"""
Taxonomy management and exact string verification (Feature 3 Step 2).

Enforces:
- spec.md AC-4: Exact case-sensitive string matching only. No normalization, stemming, or fuzzy comparison.
- spec.md AC-5: Unrecognized labels route to pending_taxonomy_confirmation, never auto-accepted.
- CONSTITUTION §6.3: Never auto-merge conflicting taxonomy labels.
- CONSTITUTION §1.9: Atomic persistence via temporary file rename.
"""

import json
import logging
import os
from pathlib import Path

from app.classification.models import (
    TaxonomyCheckResult,
    TaxonomyStatus,
)

logger = logging.getLogger(__name__)

# Default seed taxonomy (plan.md §6.1 Item 5, spec.md §3)
SEED_TAXONOMY: list[str] = [
    "Stock-Based Compensation",
    "Restructuring Charges",
    "Litigation Charges",
    "Lease Adjustments",
    "Amortization of Intangibles",
    "Acquisition-Related Expenses",
    "Impairment of Assets",
    "Gain/Loss on Divestitures",
    "Foreign Currency Adjustments",
    "Other Non-Operating Expenses",
]

_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"


def check_label_against_taxonomy(
    candidate_label: str,
    active_taxonomy: list[str],
) -> TaxonomyCheckResult:
    """
    Checks candidate label by exact string match against the active taxonomy (AC-4, AC-5).

    Matches strictly on case-sensitive string equality without fuzzy matching,
    stemming, or normalization.

    Args:
        candidate_label: The string label returned by the classifier.
        active_taxonomy: Current active taxonomy entries list.

    Returns:
        TaxonomyCheckResult with status 'matched' or 'pending_taxonomy_confirmation'.
    """
    # Exact case-sensitive string equality check (AC-4)
    for entry in active_taxonomy:
        if candidate_label == entry:
            return TaxonomyCheckResult(
                candidate_label=candidate_label,
                status=TaxonomyStatus.matched,
                matched_entry=entry,
                is_matched=True,
            )

    # Unrecognized label queued for human confirmation (AC-5, CONSTITUTION §6.3)
    return TaxonomyCheckResult(
        candidate_label=candidate_label,
        status=TaxonomyStatus.pending_taxonomy_confirmation,
        matched_entry=None,
        is_matched=False,
    )


class TaxonomyRepository:
    """
    Persisted store for the active taxonomy list.
    """

    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR) -> None:
        self._data_dir = data_dir
        self._taxonomy_file = data_dir / "taxonomy.json"

    def _ensure_dir(self) -> None:
        """Create data directory if missing."""
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def load_taxonomy(self) -> list[str]:
        """
        Loads the active taxonomy from disk, falling back to SEED_TAXONOMY if not present.
        """
        if not self._taxonomy_file.exists():
            return list(SEED_TAXONOMY)

        try:
            content = self._taxonomy_file.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, list) and all(isinstance(x, str) for x in data):
                return list(data)
            logger.warning("taxonomy.json format invalid; falling back to default seed")
            return list(SEED_TAXONOMY)
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as err:
            logger.error("Failed to read taxonomy.json: %s", err)
            return list(SEED_TAXONOMY)

    def save_taxonomy(self, entries: list[str]) -> Path:
        """
        Persists taxonomy entries to data/taxonomy.json atomically (CONSTITUTION §1.9).
        """
        self._ensure_dir()
        dest_path = self._taxonomy_file
        tmp_path = self._data_dir / "taxonomy.json.tmp"

        payload = entries
        tmp_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp_path, dest_path)
        return dest_path

    def add_entry(self, entry: str) -> bool:
        """
        Adds a new confirmed entry to the persisted taxonomy if not already present.

        Returns True if added, False if already present.
        """
        current = self.load_taxonomy()
        if entry in current:
            return False

        current.append(entry)
        self.save_taxonomy(current)
        return True
