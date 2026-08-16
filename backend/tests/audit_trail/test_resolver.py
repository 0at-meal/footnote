"""
Unit tests for Audit Trail Resolver (Feature 6 Step 1).

Enforces:
- AC-1: Every generated cell resolves to a non-empty source chain.
- AC-2: All contributing records appear in the chain for aggregated formulas.
- AC-4: Review status displayed per component is current (read from Feature 5 state store).
- AC-5: Feature 6 does not modify any review status.
- AC-6 / EC-2: Cells outside Feature 4's scope return clear 'no provenance' response.
- AC-7: Provenance record ID lookup works independently and matches cell lookup.
- EC-1: Missing records surfaced with status 'source_record_missing' without truncating chain.
- EC-7: Non-existent provenance ID returns structured not-found response.
"""

from pathlib import Path

import pytest
from app.audit_trail.resolver import AuditTrailResolver
from app.classification.models import ClassifiedRecord, TaxonomyStatus
from app.classification.repository import ClassificationRepository
from app.excel_export.generator import generate_workbook
from app.excel_export.repository import ModelRepository
from app.extraction.models import ConfidenceBand, ExtractedRecord, ScoredRecord
from app.formula_engine.reader import read_formula_inputs
from app.formula_engine.tree import build_formula_tree
from app.review.models import ReviewStatus
from app.review.repository import ReviewRepository


def _create_sample_classified_records(job_id: str) -> list[ClassifiedRecord]:
    """Helper to build a realistic set of classified records with duplicate label (EC-1)."""
    return [
        ClassifiedRecord(
            record=ScoredRecord(
                record=ExtractedRecord(
                    value="1,500.00",
                    label="Operating Income",
                    page=10,
                    bbox={"x0": 100.0, "y0": 150.0, "x1": 400.0, "y1": 180.0},
                    source_file="filing_2023.pdf",
                ),
                confidence_score=0.98,
                confidence_band=ConfidenceBand.auto_accepted,
                flags=[],
                status="ok",
                error_detail=None,
            ),
            normalized_label="Operating Income",
            taxonomy_status=TaxonomyStatus.matched,
            reasoning="Exact match",
            is_confirmed=True,
        ),
        # Stock-Based Compensation item 1
        ClassifiedRecord(
            record=ScoredRecord(
                record=ExtractedRecord(
                    value="250.00",
                    label="Stock-based comp - R&D",
                    page=14,
                    bbox={"x0": 110.0, "y0": 220.0, "x1": 380.0, "y1": 240.0},
                    source_file="filing_2023.pdf",
                ),
                confidence_score=0.96,
                confidence_band=ConfidenceBand.auto_accepted,
                flags=[],
                status="ok",
                error_detail=None,
            ),
            normalized_label="Stock-Based Compensation",
            taxonomy_status=TaxonomyStatus.matched,
            reasoning="Exact match",
            is_confirmed=True,
        ),
        # Stock-Based Compensation item 2 (Duplicate label for aggregate testing)
        ClassifiedRecord(
            record=ScoredRecord(
                record=ExtractedRecord(
                    value="150.00",
                    label="Stock-based comp - SG&A",
                    page=18,
                    bbox={"x0": 120.0, "y0": 310.0, "x1": 390.0, "y1": 330.0},
                    source_file="filing_2023.pdf",
                ),
                confidence_score=0.95,
                confidence_band=ConfidenceBand.auto_accepted,
                flags=[],
                status="ok",
                error_detail=None,
            ),
            normalized_label="Stock-Based Compensation",
            taxonomy_status=TaxonomyStatus.matched,
            reasoning="Exact match",
            is_confirmed=True,
        ),
    ]


@pytest.fixture
def populated_job_env(tmp_path: Path) -> tuple[str, Path]:
    """Creates a temporary test environment with a generated model and review state."""
    job_id = "test_job_audit_123"

    # 1. Save classified records
    class_repo = ClassificationRepository(data_dir=tmp_path)
    records = _create_sample_classified_records(job_id)
    class_repo.save_classified_records(job_id, records)

    # 2. Initialize review state & mark one item as locked, one as flagged
    review_repo = ReviewRepository(data_dir=tmp_path)
    review_items = review_repo.get_review_items(job_id)
    assert review_items is not None
    review_repo.confirm_item(job_id, f"{job_id}_0")  # Locked
    review_repo.flag_item(job_id, f"{job_id}_1")     # Flagged

    # 3. Generate formula tree and workbook
    inputs = read_formula_inputs(records)
    tree = build_formula_tree(inputs, target_metric="Adjusted EBITDA")
    gen_result = generate_workbook(tree, job_id=job_id, output_dir=tmp_path)
    assert gen_result.is_success
    assert gen_result.provenance_records

    model_repo = ModelRepository(data_dir=tmp_path)
    model_repo.save_provenance_records(job_id, gen_result.provenance_records)

    return job_id, tmp_path


def test_resolve_single_leaf_cell(populated_job_env: tuple[str, Path]) -> None:
    """Test resolving a single leaf cell in Source_Inputs (AC-1, AC-4)."""
    job_id, data_dir = populated_job_env
    resolver = AuditTrailResolver(data_dir=data_dir)

    # Source_Inputs!F2 is Operating Income
    resp = resolver.resolve_by_cell(job_id, "Source_Inputs", "F2")
    assert resp.is_found
    assert resp.job_id == job_id
    assert resp.sheet_name == "Source_Inputs"
    assert resp.cell_coord == "F2"
    assert not resp.is_formula
    assert len(resp.components) == 1

    comp = resp.components[0]
    assert comp.component_id == f"{job_id}_0"
    assert comp.source_file == "filing_2023.pdf"
    assert comp.page == 10
    assert comp.normalized_label == "Operating Income"
    assert comp.review_status == ReviewStatus.locked.value
    assert not comp.is_missing


def test_resolve_aggregated_formula_cell(populated_job_env: tuple[str, Path]) -> None:
    """Test resolving an aggregated formula cell (e.g. Total Stock-Based Compensation) (AC-2)."""
    job_id, data_dir = populated_job_env
    resolver = AuditTrailResolver(data_dir=data_dir)

    # In our sample, Stock-Based Compensation has 2 items (leaf 1 on p.14 and leaf 2 on p.18).
    # Reconciliation rows:
    # Row 4: Operating Income
    # Row 5: SBC p.14
    # Row 6: SBC p.18
    # Row 7: Total SBC (aggregate formula)
    resp = resolver.resolve_by_cell(job_id, "Reconciliation", "C7")
    assert resp.is_found
    assert resp.is_formula
    assert resp.node_id is not None and resp.node_id.startswith("agg_")
    # All contributing records must appear in the chain (AC-2)
    assert len(resp.components) == 2

    comp1 = resp.components[0]
    comp2 = resp.components[1]
    assert comp1.page == 14
    assert comp1.review_status == ReviewStatus.flagged.value  # Current live status (AC-4)
    assert comp2.page == 18
    assert comp2.review_status == ReviewStatus.auto_accepted.value


def test_resolve_root_total_cell(populated_job_env: tuple[str, Path]) -> None:
    """Test resolving the root target metric (Adjusted EBITDA) row (AC-1, AC-2)."""
    job_id, data_dir = populated_job_env
    resolver = AuditTrailResolver(data_dir=data_dir)

    # Reconciliation!C8 is Adjusted EBITDA total root
    resp = resolver.resolve_by_cell(job_id, "Reconciliation", "C8")
    assert resp.is_found
    assert resp.is_formula
    assert resp.node_id is not None and resp.node_id.startswith("root_")
    # Root should resolve to all 3 leaf components in order
    assert len(resp.components) == 3
    pages = [c.page for c in resp.components]
    assert pages == [10, 14, 18]


def test_resolve_by_provenance_id(populated_job_env: tuple[str, Path]) -> None:
    """Test that provenance record ID lookup resolves identically to cell lookup (AC-7)."""
    job_id, data_dir = populated_job_env
    resolver = AuditTrailResolver(data_dir=data_dir)

    prov_id = f"urn:footnote:provenance:{job_id}:Reconciliation:C4"
    resp_by_id = resolver.resolve_by_provenance_id(job_id, prov_id)
    resp_by_cell = resolver.resolve_by_cell(job_id, "Reconciliation", "C4")

    assert resp_by_id.is_found
    assert resp_by_cell.is_found
    assert resp_by_id.provenance_id == prov_id
    assert resp_by_id.cell_coord == resp_by_cell.cell_coord
    assert len(resp_by_id.components) == len(resp_by_cell.components)
    assert resp_by_id.components[0].component_id == resp_by_cell.components[0].component_id
    assert resp_by_id.components[0].value == resp_by_cell.components[0].value


def test_resolve_out_of_scope_cell(populated_job_env: tuple[str, Path]) -> None:
    """Test non-generated cell reference returns structured 'not found' response (AC-6, EC-2)."""
    job_id, data_dir = populated_job_env
    resolver = AuditTrailResolver(data_dir=data_dir)

    resp = resolver.resolve_by_cell(job_id, "Reconciliation", "Z99")
    assert not resp.is_found
    assert resp.sheet_name == "Reconciliation"
    assert resp.cell_coord == "Z99"
    assert len(resp.components) == 0
    assert resp.error_detail is not None


def test_resolve_unknown_provenance_id(populated_job_env: tuple[str, Path]) -> None:
    """Test non-existent provenance ID returns structured 'not found' response (EC-7)."""
    job_id, data_dir = populated_job_env
    resolver = AuditTrailResolver(data_dir=data_dir)

    resp = resolver.resolve_by_provenance_id(job_id, "urn:footnote:provenance:fake_job:Sheet1:A1")
    assert not resp.is_found
    assert len(resp.components) == 0
    assert resp.error_detail is not None


def test_read_only_invariance(populated_job_env: tuple[str, Path]) -> None:
    """Test that performing audit trail lookup NEVER mutates review state (AC-5, CONSTITUTION §6.6)."""
    job_id, data_dir = populated_job_env
    resolver = AuditTrailResolver(data_dir=data_dir)
    review_repo = ReviewRepository(data_dir=data_dir)

    # Initial state
    items_before = review_repo.get_review_items(job_id)
    assert items_before is not None
    status_map_before = {item.id: item.status for item in items_before}

    # Perform multiple lookups
    resolver.resolve_by_cell(job_id, "Reconciliation", "C7")
    resolver.resolve_by_cell(job_id, "Source_Inputs", "F2")
    resolver.resolve_by_provenance_id(job_id, f"urn:footnote:provenance:{job_id}:Reconciliation:C8")

    # State after lookups must be strictly identical
    items_after = review_repo.get_review_items(job_id)
    assert items_after is not None
    status_map_after = {item.id: item.status for item in items_after}

    assert status_map_before == status_map_after


def test_missing_review_record_gap_handling(populated_job_env: tuple[str, Path]) -> None:
    """Test gap handling when a review record was deleted from the store (EC-1)."""
    job_id, data_dir = populated_job_env
    resolver = AuditTrailResolver(data_dir=data_dir)
    review_repo = ReviewRepository(data_dir=data_dir)

    # Simulate deleting item 1 from review store
    items = review_repo.get_review_items(job_id)
    assert items is not None
    # Keep only item 0 and item 2 (remove item 1)
    filtered_items = [it for it in items if it.id != f"{job_id}_1"]
    review_repo.save_review_items(job_id, filtered_items)

    # Lookup aggregate cell that includes item 1 and item 2
    resp = resolver.resolve_by_cell(job_id, "Reconciliation", "C7")
    assert resp.is_found
    assert len(resp.components) == 2  # Chain is not silently truncated!

    comp_missing = resp.components[0]
    assert comp_missing.is_missing
    assert comp_missing.review_status == "source_record_missing"

    comp_present = resp.components[1]
    assert not comp_present.is_missing
    assert comp_present.review_status == ReviewStatus.auto_accepted.value
