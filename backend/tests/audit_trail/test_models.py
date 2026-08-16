"""
Unit tests for Audit Trail data models (Feature 6 Step 1).

Enforces CONSTITUTION §1.1, §1.3, §2.3:
- Fully typed models with frozen field names.
- Validation bounds on coordinates and pages.
"""

import pytest
from app.audit_trail.models import SourceChainResponse, SourceComponent
from pydantic import ValidationError


def test_source_component_valid() -> None:
    """Test valid instantiation and frozen field preservation."""
    comp = SourceComponent(
        component_id="job123_0",
        source_file="annual_report_2023.pdf",
        page=12,
        bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 250.0},
        value="450.5",
        label="Operating Income (Loss)",
        normalized_label="Operating Income",
        review_status="locked",
        is_missing=False,
        provenance_id="urn:footnote:provenance:job123:Source_Inputs:F2",
    )
    assert comp.component_id == "job123_0"
    assert comp.source_file == "annual_report_2023.pdf"
    assert comp.page == 12
    assert comp.bbox["x0"] == 100.0
    assert comp.value == "450.5"
    assert comp.label == "Operating Income (Loss)"
    assert comp.normalized_label == "Operating Income"
    assert comp.review_status == "locked"
    assert not comp.is_missing


def test_source_component_page_validation() -> None:
    """Test that page must be >= 1."""
    with pytest.raises(ValidationError):
        SourceComponent(
            component_id="comp_1",
            source_file="doc.pdf",
            page=0,  # Invalid: page < 1
            bbox={"x0": 0.0, "y0": 0.0, "x1": 100.0, "y1": 100.0},
            value="100",
            label="Revenue",
            review_status="unreviewed",
        )


def test_source_chain_response_defaults() -> None:
    """Test SourceChainResponse defaults and structure."""
    resp = SourceChainResponse(
        job_id="job_abc",
        sheet_name="Reconciliation",
        cell_coord="C4",
        is_found=True,
    )
    assert resp.job_id == "job_abc"
    assert resp.sheet_name == "Reconciliation"
    assert resp.cell_coord == "C4"
    assert resp.is_found is True
    assert resp.is_formula is False
    assert resp.components == []
    assert resp.error_detail is None


def test_source_chain_response_not_found() -> None:
    """Test SourceChainResponse for out-of-scope / not-found queries."""
    resp = SourceChainResponse(
        job_id="job_abc",
        sheet_name="RandomSheet",
        cell_coord="Z99",
        is_found=False,
        error_detail="No provenance record found for cell 'RandomSheet!Z99'.",
    )
    assert not resp.is_found
    assert resp.error_detail is not None
    assert len(resp.components) == 0
