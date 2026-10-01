"""
Shared Extraction Cache with Per-User Overlay (FN-025).

Implements:
1. Cache key: (accession, document, pack, extractor_version, taxonomy_version).
2. Multi-layer storage with merge precedence: user > verified > machine.
3. Promotion to shared layer via staff review or N-user consensus (e.g. N=3).
4. Strict privacy guarantees: private overlays and viewing history are never shared.
5. Audit preservation: version bumps trigger lazy recompute; old results are preserved.
6. Filing amendments: records 'supersedes' for amended filings (e.g. 10-K/A).
"""

import json
import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.extraction.models import ExtractedRecord

logger = logging.getLogger(__name__)

DEFAULT_EXTRACTOR_VERSION = "2.0.0"
DEFAULT_TAXONOMY_VERSION = "2026.1"
CONSENSUS_THRESHOLD_N = 3


class CacheKey(BaseModel):
    """Immutable cache key tuple for shared extraction layer."""

    accession: str
    document: str
    pack: str
    extractor_version: str = DEFAULT_EXTRACTOR_VERSION
    taxonomy_version: str = DEFAULT_TAXONOMY_VERSION

    def to_string(self) -> str:
        return f"{self.accession}:{self.document}:{self.pack}:{self.extractor_version}:{self.taxonomy_version}"

    @classmethod
    def from_string(cls, key_str: str) -> "CacheKey":
        parts = key_str.split(":")
        return cls(
            accession=parts[0],
            document=parts[1],
            pack=parts[2],
            extractor_version=parts[3],
            taxonomy_version=parts[4],
        )


class MachineExtractionEntry(BaseModel):
    """Shared base machine extraction output."""

    key: CacheKey
    records: list[ExtractedRecord]
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    supersedes: str | None = None
    is_superseded: bool = False
    superseded_by: str | None = None


class UserCorrection(BaseModel):
    """Private correction made by a single user."""

    user_id: str
    item_id: str  # Matches record label or element path
    field: str  # e.g. 'value', 'label', 'status'
    old_value: Any
    new_value: Any
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class VerifiedCorrection(BaseModel):
    """Shared verified correction approved by staff or consensus."""

    item_id: str
    field: str
    verified_value: Any
    promotion_source: Literal["staff_review", "consensus"]
    approved_by: str  # staff username or 'consensus_N_users'
    contributing_users: list[str] = Field(default_factory=list)
    promoted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MergedRecord(BaseModel):
    """Extracted record enriched with layer origin metadata."""

    record: ExtractedRecord
    origin_layer: Literal["user", "verified", "machine"]
    is_user_modified: bool = False
    is_verified_correction: bool = False


class SharedExtractionCache:
    """
    Multi-layer shared cache managing machine base, verified corrections, and user overlays.
    """

    def __init__(
        self,
        storage_dir: Path | str | None = None,
        consensus_threshold: int = CONSENSUS_THRESHOLD_N,
    ) -> None:
        self.storage_dir = Path(storage_dir) if storage_dir else None
        self.consensus_threshold = consensus_threshold

        # Layer 1: Shared Machine Base [cache_key_str -> MachineExtractionEntry]
        self._machine_base: dict[str, MachineExtractionEntry] = {}

        # Layer 2: Shared Verified Corrections [cache_key_str -> dict[item_id:field -> VerifiedCorrection]]
        self._verified_corrections: dict[str, dict[str, VerifiedCorrection]] = defaultdict(dict)

        # Layer 3: Private Per-User Overlays [user_id -> dict[cache_key_str -> dict[item_id:field -> UserCorrection]]]
        self._user_overlays: dict[str, dict[str, dict[str, UserCorrection]]] = defaultdict(lambda: defaultdict(dict))

        # Consensus tracking [cache_key_str -> dict[item_id:field:val_str -> set[user_id]]]
        self._pending_consensus: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

        self._lock = threading.Lock()

    # ── Machine Layer Operations ──────────────────────────────────────────────

    def put_machine_base(
        self,
        key: CacheKey,
        records: list[ExtractedRecord],
        supersedes_accession: str | None = None,
    ) -> MachineExtractionEntry:
        """Stores machine extracted records in the shared base layer."""
        with self._lock:
            k_str = key.to_string()
            entry = MachineExtractionEntry(
                key=key,
                records=records,
                supersedes=supersedes_accession,
            )
            self._machine_base[k_str] = entry

            # If this filing supersedes an earlier accession, link them
            if supersedes_accession:
                for old_entry in self._machine_base.values():
                    if old_entry.key.accession == supersedes_accession and old_entry.key.pack == key.pack:
                        old_entry.is_superseded = True
                        old_entry.superseded_by = key.accession

            return entry

    def get_machine_base(self, key: CacheKey) -> MachineExtractionEntry | None:
        """Retrieves raw machine extraction without any overlays."""
        with self._lock:
            return self._machine_base.get(key.to_string())

    # ── User Overlay & Promotion Operations ───────────────────────────────────

    def submit_user_correction(
        self,
        user_id: str,
        key: CacheKey,
        item_id: str,
        field: str,
        old_value: Any,
        new_value: Any,
    ) -> UserCorrection:
        """
        Submits a user correction to their private overlay.
        Checks for consensus promotion: if N independent users agree, promotes to shared verified layer.
        """
        with self._lock:
            k_str = key.to_string()
            corr = UserCorrection(
                user_id=user_id,
                item_id=item_id,
                field=field,
                old_value=old_value,
                new_value=new_value,
            )

            # Store in private user overlay
            sub_key = f"{item_id}:{field}"
            self._user_overlays[user_id][k_str][sub_key] = corr

            # Track consensus candidates
            val_sig = json.dumps(new_value, sort_keys=True, default=str)
            consensus_key = f"{item_id}:{field}:{val_sig}"
            self._pending_consensus[k_str][consensus_key].add(user_id)

            # Check if consensus threshold reached by distinct users
            contributing = list(self._pending_consensus[k_str][consensus_key])
            if len(contributing) >= self.consensus_threshold:
                verified = VerifiedCorrection(
                    item_id=item_id,
                    field=field,
                    verified_value=new_value,
                    promotion_source="consensus",
                    approved_by=f"consensus_{len(contributing)}_users",
                    contributing_users=contributing,
                )
                self._verified_corrections[k_str][sub_key] = verified
                logger.info("Correction %s on %s promoted to verified via consensus", sub_key, k_str)

            return corr

    def approve_by_staff(
        self,
        staff_user_id: str,
        key: CacheKey,
        item_id: str,
        field: str,
        new_value: Any,
    ) -> VerifiedCorrection:
        """Staff review approval promotes correction directly to shared verified layer."""
        with self._lock:
            k_str = key.to_string()
            sub_key = f"{item_id}:{field}"
            verified = VerifiedCorrection(
                item_id=item_id,
                field=field,
                verified_value=new_value,
                promotion_source="staff_review",
                approved_by=staff_user_id,
            )
            self._verified_corrections[k_str][sub_key] = verified
            return verified

    # ── Merge Precedence: user > verified > machine ───────────────────────────

    def get_merged(self, user_id: str, key: CacheKey) -> list[MergedRecord]:
        """
        Retrieves extracted records with merge precedence: user > verified > machine.
        """
        with self._lock:
            k_str = key.to_string()
            base = self._machine_base.get(k_str)
            if not base:
                return []

            verified_map = self._verified_corrections.get(k_str, {})
            user_map = self._user_overlays.get(user_id, {}).get(k_str, {})

            merged_results: list[MergedRecord] = []

            for rec in base.records:
                # Identify item by label or unique characteristic
                item_id = rec.label
                rec_copy = rec.model_copy(deep=True)
                origin: Literal["user", "verified", "machine"] = "machine"
                is_user_mod = False
                is_ver_mod = False

                # 1. Check verified corrections
                val_ver_key = f"{item_id}:value"
                if val_ver_key in verified_map:
                    rec_copy.value = str(verified_map[val_ver_key].verified_value)
                    origin = "verified"
                    is_ver_mod = True

                lbl_ver_key = f"{item_id}:label"
                if lbl_ver_key in verified_map:
                    rec_copy.label = str(verified_map[lbl_ver_key].verified_value)
                    origin = "verified"
                    is_ver_mod = True

                # 2. Check user private overlay (takes precedence over verified and machine)
                val_user_key = f"{item_id}:value"
                if val_user_key in user_map:
                    rec_copy.value = str(user_map[val_user_key].new_value)
                    origin = "user"
                    is_user_mod = True

                lbl_user_key = f"{item_id}:label"
                if lbl_user_key in user_map:
                    rec_copy.label = str(user_map[lbl_user_key].new_value)
                    origin = "user"
                    is_user_mod = True

                merged_results.append(
                    MergedRecord(
                        record=rec_copy,
                        origin_layer=origin,
                        is_user_modified=is_user_mod,
                        is_verified_correction=is_ver_mod,
                    )
                )

            return merged_results

    # ── Privacy and Audit Checks ──────────────────────────────────────────────

    def get_shared_layer_raw(self, key: CacheKey) -> dict[str, Any]:
        """
        Returns shared layer data to verify that zero user overlay or viewing history exists in it.
        """
        with self._lock:
            k_str = key.to_string()
            base = self._machine_base.get(k_str)
            verified = self._verified_corrections.get(k_str, {})
            return {
                "base": base.model_dump() if base else None,
                "verified": {k: v.model_dump() for k, v in verified.items()},
            }
