"""
Unit tests for W3C Web Annotation provenance formatting (Feature 4 Step 4).

Tests:
- plan §6.1 item 7: W3C JSON-LD compliance
- 0-1000 coordinate normalization preservation
- Exact formatting of human-readable cell comments and hyperlinks
"""

from app.excel_export.models import W3CAnnotationRecord
from app.excel_export.provenance import (
    build_w3c_annotation_for_node,
    format_cell_comment,
    format_cell_hyperlink_url,
)
from app.formula_engine.models import FormulaInputNode, FormulaNode, FormulaNodeType


def _create_sample_leaf_node() -> FormulaNode:
    src = FormulaInputNode(
        node_id="node_0_sbc",
        normalized_label="Stock-Based Compensation",
        value="45.50",
        label="Operating Expenses / SBC",
        page=15,
        bbox={"x0": 120.0, "y0": 240.0, "x1": 380.0, "y1": 270.0},
        source_file="acme_10k.pdf",
        record_index=0,
        is_hardcode=False,
    )
    return FormulaNode(
        node_id="leaf_0_sbc",
        label="Stock-Based Compensation",
        node_type=FormulaNodeType.leaf,
        operator="+",
        source_node=src,
    )


def test_build_w3c_annotation_for_leaf_node() -> None:
    """Verifies W3C JSON-LD schema, coordinate normalization, and field binding."""
    leaf = _create_sample_leaf_node()
    anno = build_w3c_annotation_for_node("job_123", "Source_Inputs", "F2", leaf)

    assert isinstance(anno, W3CAnnotationRecord)
    assert anno.context == "http://www.w3.org/ns/anno.jsonld"
    assert anno.id == "urn:footnote:provenance:job_123:Source_Inputs:F2"
    assert anno.sheet_name == "Source_Inputs"
    assert anno.cell_coord == "F2"
    assert anno.body.value == "45.50"
    assert anno.body.label == "Stock-Based Compensation"
    assert anno.body.original_label == "Operating Expenses / SBC"
    assert anno.target.source == "acme_10k.pdf"
    assert anno.target.selector is not None
    assert anno.target.selector.page == 15
    assert anno.target.selector.refinedBy.coordinate_space == "0-1000"
    assert anno.target.selector.refinedBy.coordinates.x0 == 120.0
    assert anno.target.selector.refinedBy.coordinates.y0 == 240.0


def test_format_cell_comment_leaf() -> None:
    """Verifies human-readable projection for cell comments."""
    leaf = _create_sample_leaf_node()
    anno = build_w3c_annotation_for_node("job_123", "Source_Inputs", "F2", leaf)
    comment = format_cell_comment(anno)

    assert "[Footnote Provenance]" in comment
    assert "Label: Stock-Based Compensation" in comment
    assert "Value: 45.50" in comment
    assert "Source: acme_10k.pdf (p. 15)" in comment
    assert "BBox [0-1000]: [120.0, 240.0, 380.0, 270.0]" in comment
    assert "ID: urn:footnote:provenance:job_123:Source_Inputs:F2" in comment


def test_format_cell_hyperlink_url() -> None:
    """Verifies canonical URL construction for provenance hyperlink."""
    url = format_cell_hyperlink_url("job_123", "Reconciliation", "C4")
    assert url == "http://localhost:8000/models/job_123/provenance/Reconciliation/C4"
