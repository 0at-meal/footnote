"""
Master Financial Taxonomy management and deterministic alias matching (Feature 3).

Enforces:
- spec.md AC-4: Exact and canonicalized alias matching against Master Financial Taxonomy.
- spec.md AC-5: Unrecognized labels route to pending_taxonomy_confirmation, never auto-accepted.
- CONSTITUTION ? 6.3: Never auto-merge conflicting taxonomy labels.
- CONSTITUTION ? 1.9: Atomic persistence via temporary file rename.
"""

import json
import logging
import os
import re
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


def _build_default_seed_taxonomy() -> MasterTaxonomy:
    seed_file = _DEFAULT_DATA_DIR / "taxonomy.json"
    if seed_file.exists():
        try:
            content = seed_file.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict) and "items" in data:
                return MasterTaxonomy.model_validate(data)
        except (
            json.JSONDecodeError,
            OSError,
            ValidationError,
            TypeError,
            ValueError,
        ) as err:
            logger.debug(
                "Failed to load taxonomy.json in _build_default_seed_taxonomy: %s", err
            )

    # Built-in fallback if file cannot be read
    default_items = [
        TaxonomyItem(
            canonical_name="Revenue",
            statement_type=StatementType.income_statement,
            display_order=10,
            is_debit=False,
            aliases=[
                "Total revenues",
                "Revenues",
                "Net sales",
                "Sales",
                "Total revenue",
                "Operating revenues",
            ],
        ),
        TaxonomyItem(
            canonical_name="Cost of Revenue",
            statement_type=StatementType.income_statement,
            display_order=20,
            is_debit=True,
            aliases=[
                "Cost of revenues",
                "Cost of sales",
                "Cost of goods sold",
                "Total cost of revenues",
                "COGS",
            ],
        ),
        TaxonomyItem(
            canonical_name="Gross Profit",
            statement_type=StatementType.income_statement,
            display_order=30,
            is_debit=False,
            aliases=["Gross margin", "Gross income", "Total gross profit"],
        ),
        TaxonomyItem(
            canonical_name="Research & Development",
            statement_type=StatementType.income_statement,
            display_order=40,
            is_debit=True,
            aliases=[
                "Research and development",
                "R&D expense",
                "Research and development expense",
                "R&D",
            ],
        ),
        TaxonomyItem(
            canonical_name="Sales & Marketing",
            statement_type=StatementType.income_statement,
            display_order=50,
            is_debit=True,
            aliases=[
                "Sales and marketing",
                "Selling and marketing",
                "SG&A - Sales and Marketing",
                "Marketing and sales",
            ],
        ),
        TaxonomyItem(
            canonical_name="General & Administrative",
            statement_type=StatementType.income_statement,
            display_order=60,
            is_debit=True,
            aliases=[
                "General and administrative",
                "SG&A - General and Administrative",
                "Administrative expenses",
                "G&A",
            ],
        ),
        TaxonomyItem(
            canonical_name="Operating Income",
            statement_type=StatementType.income_statement,
            display_order=80,
            is_debit=False,
            aliases=[
                "Operating profit",
                "Operating income (loss)",
                "Income from operations",
                "EBIT",
                "Operating earnings",
            ],
        ),
        TaxonomyItem(
            canonical_name="Net Income",
            statement_type=StatementType.income_statement,
            display_order=140,
            is_debit=False,
            aliases=[
                "Net earnings",
                "Net income (loss)",
                "Net profit",
                "Consolidated net income",
            ],
        ),
        TaxonomyItem(
            canonical_name="Stock-Based Compensation",
            statement_type=StatementType.non_gaap_bridge,
            display_order=610,
            is_debit=False,
            aliases=[
                "Share-based compensation expense",
                "Stock compensation expense",
                "SBC add-back",
                "Share-based payment",
                "Stock-based compensation",
            ],
        ),
        TaxonomyItem(
            canonical_name="Restructuring Charges",
            statement_type=StatementType.non_gaap_bridge,
            display_order=620,
            is_debit=False,
            aliases=[
                "Restructuring and other charges",
                "Severance costs",
                "Facility exit costs",
                "Restructuring expenses",
                "Restructuring Charges",
            ],
        ),
        TaxonomyItem(
            canonical_name="Litigation Charges",
            statement_type=StatementType.non_gaap_bridge,
            display_order=630,
            is_debit=False,
            aliases=[
                "Legal settlement charges",
                "Legal reserves",
                "Litigation and regulatory matters",
                "Litigation Charges",
            ],
        ),
        TaxonomyItem(
            canonical_name="Lease Adjustments",
            statement_type=StatementType.non_gaap_bridge,
            display_order=640,
            is_debit=False,
            aliases=[
                "Lease termination costs",
                "Right-of-use impairment",
                "Excess lease expense",
                "Lease Adjustments",
            ],
        ),
        TaxonomyItem(
            canonical_name="Amortization of Intangibles",
            statement_type=StatementType.non_gaap_bridge,
            display_order=650,
            is_debit=False,
            aliases=[
                "Intangible amortization expense",
                "Amortization of acquired intangibles",
                "Acquired intangible asset amortization",
                "Amortization of Intangibles",
            ],
        ),
        TaxonomyItem(
            canonical_name="Acquisition-Related Expenses",
            statement_type=StatementType.non_gaap_bridge,
            display_order=660,
            is_debit=False,
            aliases=[
                "M&A transaction costs",
                "Acquisition and integration costs",
                "Transaction-related expenses",
                "Acquisition-Related Expenses",
            ],
        ),
        TaxonomyItem(
            canonical_name="Impairment of Assets",
            statement_type=StatementType.non_gaap_bridge,
            display_order=670,
            is_debit=False,
            aliases=[
                "Asset impairment charges",
                "Goodwill impairment",
                "Impairment of long-lived assets",
                "Impairment of Assets",
            ],
        ),
        TaxonomyItem(
            canonical_name="Gain/Loss on Divestitures",
            statement_type=StatementType.non_gaap_bridge,
            display_order=680,
            is_debit=False,
            aliases=[
                "Net gain on sale of business",
                "Loss on sale of assets",
                "Divestiture-related gain (loss)",
                "Gain/Loss on Divestitures",
            ],
        ),
        TaxonomyItem(
            canonical_name="Foreign Currency Adjustments",
            statement_type=StatementType.non_gaap_bridge,
            display_order=690,
            is_debit=False,
            aliases=[
                "FX translation gain (loss)",
                "Foreign exchange remeasurement",
                "Currency hedge gains (losses)",
                "Foreign Currency Adjustments",
            ],
        ),
        TaxonomyItem(
            canonical_name="Other Non-Operating Expenses",
            statement_type=StatementType.non_gaap_bridge,
            display_order=700,
            is_debit=False,
            aliases=[
                "Other non-GAAP adjustments",
                "Miscellaneous non-operating",
                "Other expense (income) net adjustments",
                "Other Non-Operating Expenses",
            ],
        ),
    ]
    return MasterTaxonomy(items=default_items)


SEED_MASTER_TAXONOMY: MasterTaxonomy = _build_default_seed_taxonomy()
SEED_TAXONOMY: list[str] = [item.canonical_name for item in SEED_MASTER_TAXONOMY.items]


def canonicalize_label(label: str) -> str:
    """
    Canonicalizes a line item label for direct fallback matching.
    Collapses non-alphanumeric characters, strips, and converts to lowercase.
    """
    return re.sub(r"[^a-zA-Z0-9]+", " ", label).strip().lower()


def match_master_taxonomy(
    candidate_label: str,
    master: MasterTaxonomy | None = None,
) -> TaxonomyItem | None:
    """
    Attempts to match candidate_label against MasterTaxonomy entries using:
    1. Exact canonical_name match (case-insensitive and exact)
    2. Exact alias match (case-insensitive and exact)
    3. Canonicalized match on full candidate against canonical_name & aliases
    4. Leaf label match (after last '/') on canonical_name and aliases

    Returns the matched TaxonomyItem or None.
    """
    active_master = master if master is not None else SEED_MASTER_TAXONOMY
    candidate_raw = candidate_label.strip()
    if not candidate_raw:
        return None

    candidate_lower = candidate_raw.lower()
    candidate_canon = canonicalize_label(candidate_raw)

    # 1. Exact canonical_name match
    for item in active_master.items:
        if (
            candidate_raw == item.canonical_name
            or candidate_lower == item.canonical_name.lower()
        ):
            return item

    # 2. Exact alias match
    for item in active_master.items:
        for alias in item.aliases:
            if candidate_raw == alias or candidate_lower == alias.lower():
                return item

    # 3. Canonicalized match on full candidate against canonical_name & aliases
    for item in active_master.items:
        if (
            candidate_canon
            and canonicalize_label(item.canonical_name) == candidate_canon
        ):
            return item
        for alias in item.aliases:
            if candidate_canon and canonicalize_label(alias) == candidate_canon:
                return item

    # 4. Leaf match on canonical_name & aliases
    leaf_raw = candidate_raw.split("/")[-1].strip()
    leaf_raw = leaf_raw.split("\n")[-1].strip()
    leaf_lower = leaf_raw.lower()
    leaf_canon = canonicalize_label(leaf_raw)

    if leaf_canon and leaf_canon != candidate_canon:
        for item in active_master.items:
            if (
                leaf_lower == item.canonical_name.lower()
                or canonicalize_label(item.canonical_name) == leaf_canon
            ):
                return item
            for alias in item.aliases:
                if (
                    leaf_lower == alias.lower()
                    or canonicalize_label(alias) == leaf_canon
                ):
                    return item

    return None


def match_canonical_taxonomy(
    candidate_label: str,
    active_taxonomy: list[str] | MasterTaxonomy | None = None,
) -> str | None:
    """
    Legacy compatibility wrapper returning canonical name string or None.
    """
    if isinstance(active_taxonomy, MasterTaxonomy):
        matched = match_master_taxonomy(candidate_label, active_taxonomy)
        return matched.canonical_name if matched else None

    master_to_use = SEED_MASTER_TAXONOMY
    matched = match_master_taxonomy(candidate_label, master_to_use)
    if matched:
        return matched.canonical_name
    return None


def check_label_against_taxonomy(
    candidate_label: str,
    active_taxonomy: list[str] | MasterTaxonomy,
) -> TaxonomyCheckResult:
    """
    Checks candidate label against the active taxonomy (AC-4, AC-5).

    Supports MasterTaxonomy (exact and alias match) and legacy list[str].
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
        Persists MasterTaxonomy to data/taxonomy.json atomically (CONSTITUTION ? 1.9).
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
