"""
Integration tests for Excel Export and Provenance API Router (Feature 4 Step 4).

Tests:
- GET /models/{job_id}/download (Exposed for Feature 6/8)
- GET /models/{job_id}/provenance (Exposed for Feature 6/8)
- GET /models/{job_id}/provenance/{sheet}/{coord} (Exposed for Feature 6)
"""

from pathlib import Path

from app.excel_export.generator import generate_workbook
from app.excel_export.models import (
    BoundingBoxCoordinates,
    ProvenanceQueryResponse,
    W3CAnnotationRecord,
    W3CBody,
    W3CRefinedBy,
    W3CSelector,
    W3CTarget,
    WorkbookGenerationResult,
)
from app.excel_export.repository import ModelRepository
from app.extraction.models import ConfidenceBand
from app.formula_engine.models import FormulaInputBatch, FormulaInputNode
from app.formula_engine.tree import build_formula_tree
from app.ingestion.repository import JobRepository
from app.main import app
from app.review.models import ReviewItem, ReviewStatus
from app.review.repository import ReviewRepository
from fastapi.testclient import TestClient

client = TestClient(app)


def _create_sample_annotation(
    job_id: str = "job_api_test",
    sheet_name: str = "Source_Inputs",
    cell_coord: str = "F2",
) -> W3CAnnotationRecord:
    coords = BoundingBoxCoordinates(x0=100.0, y0=200.0, x1=300.0, y1=250.0)
    selector = W3CSelector(
        page=12,
        value="xywh=percent:100.0,200.0,300.0,250.0",
        refinedBy=W3CRefinedBy(coordinates=coords),
    )
    return W3CAnnotationRecord(
        id=f"urn:footnote:provenance:{job_id}:{sheet_name}:{cell_coord}",
        job_id=job_id,
        sheet_name=sheet_name,
        cell_coord=cell_coord,
        node_id="node_0_rev",
        is_formula=False,
        body=W3CBody(value="500.0", label="Revenue", original_label="Sales"),
        target=W3CTarget(source="annual.pdf", selector=selector),
    )


def test_download_model_not_found() -> None:
    """Verifies 404 for non-existent workbook download."""
    resp = client.get("/models/non_existent_job/download")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


def test_provenance_not_found() -> None:
    """Verifies 404 for non-existent provenance lookup."""
    resp = client.get("/models/non_existent_job/provenance")
    assert resp.status_code == 404


def test_model_download_and_provenance_query(tmp_path: Path) -> None:
    """Verifies end-to-end download and provenance lookup endpoints."""
    job_id = "job_integration_1"
    repo = ModelRepository(data_dir=tmp_path)

    # Generate workbook and provenance
    node = FormulaInputNode(
        node_id="node_0_sbc",
        normalized_label="Stock-Based Compensation",
        value="50.0",
        label="SBC",
        page=5,
        bbox={"x0": 100.0, "y0": 150.0, "x1": 250.0, "y1": 200.0},
        source_file="doc.pdf",
        record_index=0,
        is_hardcode=False,
    )
    batch = FormulaInputBatch(
        nodes=[node],
        total_records_received=1,
        confirmed_count=1,
        excluded_count=0,
    )
    tree = build_formula_tree(batch, target_metric="Adjusted EBITDA")
    gen_result = generate_workbook(tree, job_id=job_id, output_dir=tmp_path)
    assert gen_result.is_success is True

    repo.save_provenance_records(job_id, gen_result.provenance_records)

    # Set the test data_dir repository in router
    from app.excel_export.router import get_model_repository, set_model_repository

    original_repo = get_model_repository()
    set_model_repository(repo)
    try:
        # Test 1: Download workbook
        dl_resp = client.get(f"/models/{job_id}/download")
        assert dl_resp.status_code == 200
        assert dl_resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert len(dl_resp.content) > 0

        # Test 2: Get all provenance records
        prov_resp = client.get(f"/models/{job_id}/provenance")
        assert prov_resp.status_code == 200
        prov_data = ProvenanceQueryResponse.model_validate(prov_resp.json())
        assert prov_data.job_id == job_id
        assert prov_data.total_records == gen_result.total_cells_generated

        # Test 3: Get specific cell provenance
        cell_resp = client.get(f"/models/{job_id}/provenance/Source_Inputs/F2")
        assert cell_resp.status_code == 200
        cell_anno = W3CAnnotationRecord.model_validate(cell_resp.json())
        assert cell_anno.sheet_name == "Source_Inputs"
        assert cell_anno.cell_coord == "F2"
        assert cell_anno.body.label == "Stock-Based Compensation"
        assert cell_anno.target.source == "doc.pdf"

    finally:
        set_model_repository(original_repo)


def test_generate_model_from_review_items_success(tmp_path: Path) -> None:
    """Verifies that POST /models/{job_id}/generate creates .xlsx and saves provenance from review items."""
    job_repo = JobRepository(data_dir=tmp_path)
    job_repo.save_job(
        filename="10k_filing.pdf",
        content=b"%PDF-1.4 dummy",
        target_metric="Adjusted EBITDA",
    )
    # The saved job will have its own UUID, but let's update or ensure the job exists with target_metric
    jobs = job_repo.list_jobs()
    real_job_id = jobs[0].job_id

    review_repo = ReviewRepository(data_dir=tmp_path)
    review_items = [
        ReviewItem(
            id=f"{real_job_id}_0",
            value="1,200.00",
            label="Operating Expenses / Stock-based comp",
            page=15,
            bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 250.0},
            source_file="10k_filing.pdf",
            confidence_band=ConfidenceBand.auto_accepted,
            confidence_score=0.98,
            normalized_label="Stock-Based Compensation",
            status=ReviewStatus.locked,
        ),
        ReviewItem(
            id=f"{real_job_id}_1",
            value="350.00",
            label="Depreciation and amortization",
            page=16,
            bbox={"x0": 100.0, "y0": 300.0, "x1": 300.0, "y1": 350.0},
            source_file="10k_filing.pdf",
            confidence_band=ConfidenceBand.needs_review,
            confidence_score=0.85,
            normalized_label="Amortization of Intangibles",
            status=ReviewStatus.locked,
        ),
    ]
    review_repo.save_review_items(real_job_id, review_items)

    model_repo = ModelRepository(data_dir=tmp_path)
    from app.excel_export.router import get_model_repository, set_model_repository

    original_repo = get_model_repository()
    set_model_repository(model_repo)
    try:
        resp = client.post(f"/models/{real_job_id}/generate")
        assert resp.status_code == 200
        result = WorkbookGenerationResult.model_validate(resp.json())
        assert result.is_success is True
        assert result.total_cells_generated > 0
        assert result.formula_cells_count > 0

        # Assert .xlsx exists on disk
        workbook_path = model_repo.get_workbook_path(real_job_id)
        assert workbook_path is not None
        assert workbook_path.exists()

        # Assert provenance records saved to disk
        prov_records = model_repo.get_provenance_records(real_job_id)
        assert prov_records is not None
        assert len(prov_records) == result.total_cells_generated

    finally:
        set_model_repository(original_repo)


def test_generate_model_no_confirmed_items_raises_400(tmp_path: Path) -> None:
    """Verifies that POST /models/{job_id}/generate returns 400 when no items are confirmed/locked."""
    job_repo = JobRepository(data_dir=tmp_path)
    job_repo.save_job(
        filename="report.pdf",
        content=b"%PDF-1.4 dummy",
        target_metric="Adjusted EBITDA",
    )
    job_id = job_repo.list_jobs()[0].job_id

    review_repo = ReviewRepository(data_dir=tmp_path)
    review_items = [
        ReviewItem(
            id=f"{job_id}_0",
            value="100.0",
            label="Pending Item",
            page=1,
            bbox={"x0": 10.0, "y0": 20.0, "x1": 30.0, "y1": 40.0},
            source_file="report.pdf",
            confidence_band=ConfidenceBand.needs_review,
            confidence_score=0.70,
            normalized_label=None,
            status=ReviewStatus.pending_taxonomy_confirmation,
        ),
    ]
    review_repo.save_review_items(job_id, review_items)

    model_repo = ModelRepository(data_dir=tmp_path)
    from app.excel_export.router import get_model_repository, set_model_repository

    original_repo = get_model_repository()
    set_model_repository(model_repo)
    try:
        resp = client.post(f"/models/{job_id}/generate")
        assert resp.status_code == 400
        assert "no confirmed" in resp.json()["detail"].lower()
    finally:
        set_model_repository(original_repo)


def test_generate_model_job_not_found_raises_404(tmp_path: Path) -> None:
    """Verifies that POST /models/{job_id}/generate returns 404 for unknown jobs."""
    model_repo = ModelRepository(data_dir=tmp_path)
    from app.excel_export.router import get_model_repository, set_model_repository

    original_repo = get_model_repository()
    set_model_repository(model_repo)
    try:
        resp = client.post("/models/unknown_job_uuid/generate")
        assert resp.status_code == 404
    finally:
        set_model_repository(original_repo)
