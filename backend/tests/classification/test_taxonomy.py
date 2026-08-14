"""
Unit tests for taxonomy management and exact string matching (Feature 3 Step 2).

Validates:
- Exact case-sensitive string matching (spec.md AC-4)
- Queuing of unrecognized labels to pending_taxonomy_confirmation (spec.md AC-5, CONSTITUTION §6.3)
- Independent handling of repeated unrecognized labels (spec.md EC-3)
- TaxonomyRepository atomic file persistence and default seed loading
"""

from pathlib import Path

from app.classification.models import TaxonomyStatus
from app.classification.taxonomy import (
    SEED_TAXONOMY,
    TaxonomyRepository,
    check_label_against_taxonomy,
)


def test_exact_match_success() -> None:
    result = check_label_against_taxonomy("Stock-Based Compensation", SEED_TAXONOMY)
    assert result.status == TaxonomyStatus.matched
    assert result.is_matched is True
    assert result.matched_entry == "Stock-Based Compensation"
    assert result.candidate_label == "Stock-Based Compensation"


def test_case_difference_is_unrecognized() -> None:
    # AC-4: Case-sensitive exact equality
    result = check_label_against_taxonomy("stock-based compensation", SEED_TAXONOMY)
    assert result.status == TaxonomyStatus.pending_taxonomy_confirmation
    assert result.is_matched is False
    assert result.matched_entry is None


def test_punctuation_difference_is_unrecognized() -> None:
    # AC-4: "Stock Based Compensation" vs "Stock-Based Compensation"
    result = check_label_against_taxonomy("Stock Based Compensation", SEED_TAXONOMY)
    assert result.status == TaxonomyStatus.pending_taxonomy_confirmation
    assert result.is_matched is False
    assert result.matched_entry is None


def test_spacing_difference_is_unrecognized() -> None:
    # AC-4: Extra whitespace is not trimmed
    result = check_label_against_taxonomy(" Stock-Based Compensation ", SEED_TAXONOMY)
    assert result.status == TaxonomyStatus.pending_taxonomy_confirmation
    assert result.is_matched is False
    assert result.matched_entry is None


def test_unrecognized_arbitrary_label_queued() -> None:
    # AC-5: Arbitrary unknown label is queued for human confirmation
    result = check_label_against_taxonomy("Digital Asset Impairment", SEED_TAXONOMY)
    assert result.status == TaxonomyStatus.pending_taxonomy_confirmation
    assert result.is_matched is False
    assert result.matched_entry is None


def test_repeated_unrecognized_labels_independent() -> None:
    # EC-3: The same unrecognized label produces independent pending states
    res1 = check_label_against_taxonomy("Novel Reserve Item", SEED_TAXONOMY)
    res2 = check_label_against_taxonomy("Novel Reserve Item", SEED_TAXONOMY)
    assert res1.status == TaxonomyStatus.pending_taxonomy_confirmation
    assert res2.status == TaxonomyStatus.pending_taxonomy_confirmation
    assert res1.is_matched is False
    assert res2.is_matched is False


def test_taxonomy_repository_defaults_to_seed_when_no_file(tmp_path: Path) -> None:
    repo = TaxonomyRepository(data_dir=tmp_path)
    loaded = repo.load_taxonomy()
    assert loaded == SEED_TAXONOMY


def test_taxonomy_repository_save_and_reload(tmp_path: Path) -> None:
    repo = TaxonomyRepository(data_dir=tmp_path)
    custom_list = ["Custom Non-GAAP Metric", "Stock-Based Compensation"]
    saved_path = repo.save_taxonomy(custom_list)

    assert saved_path.exists()
    assert not (tmp_path / "taxonomy.json.tmp").exists()

    reloaded = repo.load_taxonomy()
    assert reloaded == custom_list


def test_taxonomy_repository_add_entry(tmp_path: Path) -> None:
    repo = TaxonomyRepository(data_dir=tmp_path)
    assert repo.add_entry("Novel Adjustment") is True
    # Second addition returns False since it already exists
    assert repo.add_entry("Novel Adjustment") is False

    loaded = repo.load_taxonomy()
    assert "Novel Adjustment" in loaded
