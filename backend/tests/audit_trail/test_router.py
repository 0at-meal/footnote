"""
Integration tests for Audit Trail API router (Feature 6 Step 1).

Enforces:
- AC-1, AC-2, AC-6, AC-7: API endpoints return structured source chain responses.
- EC-2, EC-7, EC-8: Structured not-found response for non-generated cells / invalid IDs.
"""

from pathlib import Path

import pytest
from app.audit_trail.resolver import AuditTrailResolver
from app.audit_trail.router import set_audit_trail_resolver
from app.classification.models import ClassifiedRecord, TaxonomyStatus
from app.classification.repository import ClassificationRepository
from app.excel_export.generator import generate_workbook
from app.excel_export.repository import ModelRepository
from app.extraction.models import ConfidenceBand, ExtractedRecord, ScoredRecord
from app.formula_engine.reader import read_formula_inputs
from app.formula_engine.tree import build_formula_tree
from app.main import app
from app.review.repository import ReviewRepository
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Configures TestClient with isolated temporary data directory."""
    job_id = "job_api_test_456"

    # Setup sample data in tmp_path
    class_repo = ClassificationRepository(data_dir=tmp_path)
    records = [
        ClassifiedRecord(
            record=ScoredRecord(
                record=ExtractedRecord(
                    value="2,000.00",
                    label="Operating Income",
                    page=8,
                    bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 220.0},
                    source_file="doc_2023.pdf",
                ),
                confidence_score=0.99,
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
    ]
    class_repo.save_classified_records(job_id, records)

    review_repo = ReviewRepository(data_dir=tmp_path)
    review_repo.get_review_items(job_id)
    review_repo.confirm_item(job_id, f"{job_id}_0")

    inputs = read_formula_inputs(records)
    tree = build_formula_tree(inputs, target_metric="Adjusted EBITDA")
    gen_result = generate_workbook(tree, job_id=job_id, output_dir=tmp_path)
    assert gen_result.is_success
    assert gen_result.provenance_records

    model_repo = ModelRepository(data_dir=tmp_path)
    model_repo.save_provenance_records(job_id, gen_result.provenance_records)

    resolver = AuditTrailResolver(data_dir=tmp_path)
    set_audit_trail_resolver(resolver)

    return TestClient(app)


def test_get_cell_source_chain_success(client: TestClient) -> None:
    """Test GET /audit-trail/{job_id}/cell/{sheet_name}/{cell_coord} returns valid source chain."""
    response = client.get("/audit-trail/job_api_test_456/cell/Source_Inputs/F2")
    assert response.status_code == 200
    data = response.json()
    assert data["is_found"] is True
    assert data["job_id"] == "job_api_test_456"
    assert data["sheet_name"] == "Source_Inputs"
    assert data["cell_coord"] == "F2"
    assert len(data["components"]) == 1
    assert data["components"][0]["review_status"] == "locked"
    assert data["components"][0]["source_file"] == "doc_2023.pdf"
    assert data["components"][0]["page"] == 8


def test_get_cell_source_chain_not_found(client: TestClient) -> None:
    """Test GET /audit-trail/{job_id}/cell/... for non-existent cell returns is_found=False."""
    response = client.get("/audit-trail/job_api_test_456/cell/Source_Inputs/Z99")
    assert response.status_code == 200
    data = response.json()
    assert data["is_found"] is False
    assert len(data["components"]) == 0
    assert data["error_detail"] is not None


def test_get_record_source_chain_query(client: TestClient) -> None:
    """Test GET /audit-trail/{job_id}/record?provenance_id=... query parameter lookup (AC-7)."""
    prov_id = "urn:footnote:provenance:job_api_test_456:Source_Inputs:F2"
    response = client.get(f"/audit-trail/job_api_test_456/record?provenance_id={prov_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["is_found"] is True
    assert data["provenance_id"] == prov_id
    assert len(data["components"]) == 1


def test_get_record_source_chain_path(client: TestClient) -> None:
    """Test GET /audit-trail/{job_id}/provenance/{provenance_id:path} lookup (AC-7)."""
    prov_id = "urn:footnote:provenance:job_api_test_456:Source_Inputs:F2"
    response = client.get(f"/audit-trail/job_api_test_456/provenance/{prov_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["is_found"] is True
    assert data["provenance_id"] == prov_id
    assert len(data["components"]) == 1
