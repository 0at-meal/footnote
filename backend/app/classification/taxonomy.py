"""
Master Financial Taxonomy management and deterministic alias matching.

Enforces:
- Exact and canonicalized alias matching against Master Financial Taxonomy.
- Unrecognized labels route to pending_taxonomy_confirmation, never auto-accepted.
- Never auto-merge conflicting taxonomy labels.
- Atomic persistence via temporary file rename.
"""

import difflib
import json
import logging
import os
import re
from enum import Enum
from pathlib import Path

from pydantic import ValidationError

from app.classification.models import (
    MasterTaxonomy,
    StatementType,
    TaxonomyCheckResult,
    TaxonomyItem,
    TaxonomyStatus,
)

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"


_SEED_FILE: Path = Path(__file__).with_name("seed_taxonomy.json")


def _load_seed_taxonomy() -> MasterTaxonomy:
    """
    Loads the version-controlled seed taxonomy shipped with the package.

    The seed never depends on runtime data; user-confirmed additions live in
    ``TaxonomyRepository``. An unreadable or invalid seed raises at import time
    rather than silently degrading matching.
    """
    return MasterTaxonomy.model_validate_json(_SEED_FILE.read_text(encoding="utf-8"))


SEED_MASTER_TAXONOMY: MasterTaxonomy = _load_seed_taxonomy()


def clean_raw_label(label: str) -> str:
    """
    Cleans a line item label for robust financial taxonomy matching:
    1. Strips parentheticals e.g. (exclusive of depreciation), (loss), (Note 4), (1).
    2. Strips bracketed footnote references e.g. [1], [a].
    3. Strips date or period column segments when separated by '/' e.g. ' / 2024'.
    4. Strips leading/trailing footnote symbols and numeric bullets.
    5. Normalizes whitespace and returns stripped text.
    """
    text = label.strip()
    if not text:
        return ""

    # Check for slash-delimited segments e.g. "Research and development / 2024"
    segments = [s.strip() for s in text.split("/") if s.strip()]
    while len(segments) > 1 and re.match(
        r"^(?:(?:19|20)\d{2}|Q[1-4]|FY\d{2,4}|[A-Za-z]+ \d{1,2},? \d{4}|\d{1,2}/\d{1,2}/\d{2,4}|three months|six months|nine months|twelve months|years? ended.*)$",
        segments[-1],
        re.IGNORECASE,
    ):
        segments.pop()
    text = " / ".join(segments)

    # Strip parentheticals e.g. (exclusive of...), (loss), (Note 4), (1)
    text = re.sub(r"\([^)]*\)", " ", text)
    # Strip brackets e.g. [1], [a]
    text = re.sub(r"\[[^\]]*\]", " ", text)
    # Strip common footnote marks at start or end
    text = re.sub(r"^[\d*#†‡§]+\s*[-.:]?\s*", "", text)
    text = re.sub(r"\s*[\d*#†‡§]+$", "", text)
    # Normalize whitespace
    return re.sub(r"\s+", " ", text).strip()


def canonicalize_label(label: str) -> str:
    """
    Canonicalizes a line item label for direct fallback matching.
    Collapses non-alphanumeric characters, strips, and converts to lowercase.
    """
    return re.sub(r"[^a-zA-Z0-9]+", " ", label).strip().lower()


def extract_semantic_leaf(label: str) -> str:
    """
    Extracts the most specific semantic line-item leaf from a path,
    stripping trailing period/year/quarter column header segments.
    For example:
    'Research and development / 2024' -> 'Research and development'
    'Operating Expenses / Novel Unclassified Reserve' -> 'Novel Unclassified Reserve'
    """
    segments = [s.strip() for s in label.replace("\n", "/").split("/") if s.strip()]
    if not segments:
        return label
    while len(segments) > 1 and re.search(
        r"^(?:(?:19|20)\d{2}|Q[1-4]|FY\d{2,4}|three months|six months|nine months|twelve months|years? ended)",
        segments[-1],
        re.IGNORECASE,
    ):
        segments.pop()
    return segments[-1]


def match_master_taxonomy(
    candidate_label: str,
    master: MasterTaxonomy | None = None,
) -> TaxonomyItem | None:
    """
    Matches a raw candidate label against MasterTaxonomy canonical names and aliases.

    Evaluation order:
    1. Exact canonical_name match (case-insensitive, raw or cleaned).
    2. Exact alias match (case-insensitive, raw or cleaned).
    3. Canonicalized match on candidate vs canonical_name and aliases.
    4. Semantic leaf match across slash/newline delimited paths (ignoring trailing year headers).

    Returns the matching TaxonomyItem, or None if no match is found.
    Never raises an exception on unexpected label formats.
    """
    active_master = master if master is not None else SEED_MASTER_TAXONOMY
    candidate_raw = candidate_label.strip()
    if not candidate_raw:
        return None

    candidate_lower = candidate_raw.lower()
    candidate_canon = canonicalize_label(candidate_raw)
    clean_label = clean_raw_label(candidate_raw)
    clean_lower = clean_label.lower() if clean_label else ""
    clean_canon = canonicalize_label(clean_label) if clean_label else ""

    # 1. Exact canonical_name match (raw or cleaned)
    for item in active_master.items:
        if (
            candidate_raw == item.canonical_name
            or candidate_lower == item.canonical_name.lower()
            or (clean_label and clean_label == item.canonical_name)
            or (clean_lower and clean_lower == item.canonical_name.lower())
        ):
            return item

    # 2. Exact alias match (raw or cleaned)
    for item in active_master.items:
        for alias in item.aliases:
            alias_lower = alias.lower()
            if (
                candidate_raw == alias
                or candidate_lower == alias_lower
                or (clean_label and clean_label == alias)
                or (clean_lower and clean_lower == alias_lower)
            ):
                return item

    # 3. Canonicalized match on full candidate and clean candidate
    for item in active_master.items:
        item_canon = canonicalize_label(item.canonical_name)
        if (candidate_canon and item_canon == candidate_canon) or (
            clean_canon and item_canon == clean_canon
        ):
            return item
        for alias in item.aliases:
            alias_canon = canonicalize_label(alias)
            if (candidate_canon and alias_canon == candidate_canon) or (
                clean_canon and alias_canon == clean_canon
            ):
                return item

    # 4. Semantic leaf matching for slash or newline delimited paths
    semantic_leaf = extract_semantic_leaf(candidate_raw)
    if semantic_leaf and semantic_leaf != candidate_raw:
        leaf_clean = clean_raw_label(semantic_leaf)
        leaf_lower = semantic_leaf.lower()
        leaf_clean_lower = leaf_clean.lower() if leaf_clean else ""
        leaf_canon = canonicalize_label(semantic_leaf)
        leaf_clean_canon = canonicalize_label(leaf_clean) if leaf_clean else ""

        for item in active_master.items:
            item_lower = item.canonical_name.lower()
            item_canon = canonicalize_label(item.canonical_name)
            if (
                semantic_leaf == item.canonical_name
                or leaf_lower == item_lower
                or (leaf_clean and leaf_clean == item.canonical_name)
                or (leaf_clean_lower and leaf_clean_lower == item_lower)
                or (leaf_canon and item_canon == leaf_canon)
                or (leaf_clean_canon and item_canon == leaf_clean_canon)
            ):
                return item
            for alias in item.aliases:
                alias_lower = alias.lower()
                alias_canon = canonicalize_label(alias)
                if (
                    semantic_leaf == alias
                    or leaf_lower == alias_lower
                    or (leaf_clean and leaf_clean == alias)
                    or (leaf_clean_lower and leaf_clean_lower == alias_lower)
                    or (leaf_canon and alias_canon == leaf_canon)
                    or (leaf_clean_canon and alias_canon == leaf_clean_canon)
                ):
                    return item

    return None


def compute_token_set_ratio(s1: str, s2: str) -> float:
    """
    Computes token-set-ratio similarity between two financial strings in [0.0, 1.0].
    """
    t1 = canonicalize_label(s1).split()
    t2 = canonicalize_label(s2).split()
    if not t1 or not t2:
        return 0.0
    set1 = set(t1)
    set2 = set(t2)
    intersection = set1 & set2
    diff1 = set1 - set2
    diff2 = set2 - set1

    sorted_inter = " ".join(sorted(intersection))
    sorted_1 = " ".join(sorted(intersection) + sorted(diff1))
    sorted_2 = " ".join(sorted(intersection) + sorted(diff2))

    if not sorted_inter:
        return difflib.SequenceMatcher(
            None, " ".join(sorted(t1)), " ".join(sorted(t2))
        ).ratio()

    r1 = difflib.SequenceMatcher(None, sorted_inter, sorted_1).ratio()
    r2 = difflib.SequenceMatcher(None, sorted_inter, sorted_2).ratio()
    r3 = difflib.SequenceMatcher(None, sorted_1, sorted_2).ratio()
    return max(r1, r2, r3)


def match_master_taxonomy_fuzzy(
    candidate_label: str,
    master: MasterTaxonomy | None = None,
    threshold: float = 0.85,
) -> tuple[TaxonomyItem | None, float]:
    """
    Finds best fuzzy matching TaxonomyItem with token-set-ratio >= threshold.
    """
    active_master = master if master is not None else SEED_MASTER_TAXONOMY
    candidate_raw = candidate_label.strip()
    if not candidate_raw:
        return None, 0.0

    best_item: TaxonomyItem | None = None
    best_score: float = 0.0

    for item in active_master.items:
        score_canon = compute_token_set_ratio(candidate_raw, item.canonical_name)
        if score_canon > best_score:
            best_score = score_canon
            best_item = item

        for alias in item.aliases:
            score_alias = compute_token_set_ratio(candidate_raw, alias)
            if score_alias > best_score:
                best_score = score_alias
                best_item = item

    if best_score >= threshold:
        return best_item, best_score
    return None, best_score


def check_label_against_taxonomy(
    candidate_label: str,
    active_taxonomy: list[str] | MasterTaxonomy,
    fuzzy_threshold: float = 0.85,
) -> TaxonomyCheckResult:
    """
    Checks candidate label against the active taxonomy.

    1. Exact & canonicalized match -> TaxonomyStatus.matched (is_matched=True)
    2. Fuzzy token-set-ratio match (>= 0.85) -> TaxonomyStatus.fuzzy_matched
       (is_matched=False): a *suggestion* for human confirmation, never an
       automatic match. Token-set ratio scores 1.0 whenever one label's tokens
       are a subset of the other's (e.g. "Net income attributable to
       noncontrolling interests" vs "Net Income"), so it cannot be trusted alone.
    3. Unrecognized -> TaxonomyStatus.pending_taxonomy_confirmation (is_matched=False)
    """
    if isinstance(active_taxonomy, MasterTaxonomy):
        matched_item = match_master_taxonomy(candidate_label, active_taxonomy)
        if matched_item is not None:
            return TaxonomyCheckResult(
                candidate_label=candidate_label,
                status=TaxonomyStatus.matched,
                matched_entry=matched_item.canonical_name,
                matched_item=matched_item,
                is_matched=True,
            )

        # Fuzzy match pass
        fuzzy_item, fuzzy_score = match_master_taxonomy_fuzzy(
            candidate_label, active_taxonomy, threshold=fuzzy_threshold
        )
        if fuzzy_item is not None:
            return TaxonomyCheckResult(
                candidate_label=candidate_label,
                status=TaxonomyStatus.fuzzy_matched,
                matched_entry=fuzzy_item.canonical_name,
                matched_item=fuzzy_item,
                is_matched=False,
                similarity_score=round(fuzzy_score, 2),
            )

        return TaxonomyCheckResult(
            candidate_label=candidate_label,
            status=TaxonomyStatus.pending_taxonomy_confirmation,
            matched_entry=None,
            matched_item=None,
            is_matched=False,
        )

    # Legacy list[str] exact match
    for entry in active_taxonomy:
        if candidate_label == entry:
            return TaxonomyCheckResult(
                candidate_label=candidate_label,
                status=TaxonomyStatus.matched,
                matched_entry=entry,
                matched_item=None,
                is_matched=True,
            )

    return TaxonomyCheckResult(
        candidate_label=candidate_label,
        status=TaxonomyStatus.pending_taxonomy_confirmation,
        matched_entry=None,
        matched_item=None,
        is_matched=False,
    )


class TaxonomyRepository:
    """
    Persisted store for the active MasterTaxonomy.
    """

    def __init__(self, data_dir: Path = _DEFAULT_DATA_DIR) -> None:
        self._data_dir = data_dir
        self._taxonomy_file = data_dir / "taxonomy.json"

    def _ensure_dir(self) -> None:
        """Create data directory if missing."""
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def load_taxonomy(self) -> MasterTaxonomy:
        """
        Loads the active MasterTaxonomy from disk, falling back to SEED_MASTER_TAXONOMY if not present or invalid.
        """
        if not self._taxonomy_file.exists():
            return SEED_MASTER_TAXONOMY.model_copy(deep=True)

        try:
            content = self._taxonomy_file.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict) and "items" in data:
                return MasterTaxonomy.model_validate(data)
            elif isinstance(data, list):
                # Legacy flat list migration fallback
                items = [
                    TaxonomyItem(
                        canonical_name=x,
                        statement_type=StatementType.non_gaap_bridge,
                        display_order=i * 10,
                        is_debit=False,
                        aliases=[],
                    )
                    for i, x in enumerate(data)
                    if isinstance(x, str)
                ]
                return MasterTaxonomy(items=items)
            logger.warning("taxonomy.json format invalid; falling back to default seed")
            return SEED_MASTER_TAXONOMY.model_copy(deep=True)
        except (
            json.JSONDecodeError,
            ValidationError,
            OSError,
            TypeError,
            ValueError,
        ) as err:
            logger.error("Failed to read taxonomy.json: %s", err)
            return SEED_MASTER_TAXONOMY.model_copy(deep=True)

    def save_taxonomy(self, master: MasterTaxonomy) -> Path:
        """
        Persists MasterTaxonomy to data/taxonomy.json atomically.
        """
        self._ensure_dir()
        dest_path = self._taxonomy_file
        tmp_path = self._data_dir / "taxonomy.json.tmp"

        payload = master.model_dump(mode="json")
        tmp_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp_path, dest_path)
        return dest_path

    def get_items_by_statement(
        self, statement_type: StatementType
    ) -> list[TaxonomyItem]:
        """
        Returns all taxonomy items belonging to a specific statement type, sorted by display_order.
        """
        master = self.load_taxonomy()
        matching = [
            item for item in master.items if item.statement_type == statement_type
        ]
        matching.sort(key=lambda x: x.display_order)
        return matching

    def get_all_canonical_names(self) -> list[str]:
        """
        Returns a flat list of all canonical names for backward compatibility.
        """
        master = self.load_taxonomy()
        return [item.canonical_name for item in master.items]

    def add_entry(
        self,
        item: TaxonomyItem | str,
        statement_type: StatementType = StatementType.non_gaap_bridge,
    ) -> bool:
        """
        Adds a new confirmed entry to the persisted taxonomy if not already present.
        Returns True if added, False if already present.
        """
        master = self.load_taxonomy()
        if isinstance(item, str):
            canonical_name = item.strip()
            if any(
                i.canonical_name.lower() == canonical_name.lower() for i in master.items
            ):
                return False
            new_item = TaxonomyItem(
                canonical_name=canonical_name,
                statement_type=statement_type,
                display_order=len(master.items) * 10,
                is_debit=False,
                aliases=[],
            )
            master.items.append(new_item)
        else:
            if any(
                i.canonical_name.lower() == item.canonical_name.lower()
                for i in master.items
            ):
                return False
            master.items.append(item)

        self.save_taxonomy(master)
        return True


class StandardAddBackCategory(str, Enum):
    """
    Standardized add-back categories:
    SBC, restructuring, impairment, M&A/integration, litigation, FX, other.
    """

    SBC = "SBC"
    RESTRUCTURING = "Restructuring"
    IMPAIRMENT = "Impairment"
    MA_INTEGRATION = "M&A/Integration"
    LITIGATION = "Litigation"
    FX = "FX"
    OTHER = "Other"


def classify_addback_category(label: str) -> StandardAddBackCategory:
    """
    Deterministically maps a line item label to a standard add-back category by
    ordered keyword matching (first category whose keywords appear wins).
    D&A, interest, and taxes are not add-back categories here and map to OTHER.
    """
    norm = label.lower().strip()

    # 1. SBC
    if any(
        kw in norm
        for kw in (
            "stock-based",
            "share-based",
            "stock based",
            "share based",
            "sbc",
            "equity compensation",
            "stock compensation",
            "equity-based",
            "share award",
        )
    ):
        return StandardAddBackCategory.SBC

    # 2. Restructuring
    if any(
        kw in norm
        for kw in (
            "restructuring",
            "severance",
            "facility exit",
            "plant closure",
            "reorganization",
            "workforce reduction",
            "rationalization",
            "exit costs",
        )
    ):
        return StandardAddBackCategory.RESTRUCTURING

    # 3. Impairment
    if any(
        kw in norm
        for kw in (
            "impairment",
            "write-down",
            "write down",
            "write-off",
            "write off",
            "goodwill impairment",
            "asset impairment",
            "intangible impairment",
        )
    ):
        return StandardAddBackCategory.IMPAIRMENT

    # 4. M&A / Integration
    if any(
        kw in norm
        for kw in (
            "acquisition",
            "integration",
            "transaction cost",
            "transaction expense",
            "merger",
            "m&a",
            "due diligence",
            "advisory fee",
            "purchase accounting",
        )
    ):
        return StandardAddBackCategory.MA_INTEGRATION

    # 5. Litigation
    if any(
        kw in norm
        for kw in (
            "litigation",
            "legal settlement",
            "legal reserve",
            "legal charges",
            "regulatory settlement",
            "dispute",
            "arbitration",
            "lawsuit",
        )
    ):
        return StandardAddBackCategory.LITIGATION

    # 6. FX
    if any(
        kw in norm
        for kw in (
            "foreign exchange",
            "foreign currency",
            "currency transaction",
            "currency fluctuation",
            "fx gain",
            "fx loss",
            "translation gain",
            "translation loss",
        )
    ):
        return StandardAddBackCategory.FX

    return StandardAddBackCategory.OTHER
