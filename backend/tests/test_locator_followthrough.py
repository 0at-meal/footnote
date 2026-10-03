"""
AUD-037: finish FN-023 around the locator union.

- canonical_locator_key(): one deterministic key per locator, however it was built.
- W3C provenance records carry the leaf's locator; HTML targets get a TextQuoteSelector.
- The audit trail finds the live review item for an HTML leaf (it hashed URL + whole page before).
- The audit report tolerates selectors without a bounding box (it dereferenced refinedBy).

All identifiers are SYNTHETIC.
"""

from pathlib import Path

from app.audit_report.compiler import AuditReportCompiler
from app.audit_trail.resolver import AuditTrailResolver
from app.excel_export.models import W3CAnnotationRecord, W3CBody, W3CSelector, W3CTarget
from app.excel_export.provenance import build_w3c_annotation_for_node
from app.excel_export.repository import ModelRepository
from app.extraction.locator import HtmlLocator, PdfLocator
from app.extraction.models import ConfidenceBand
from app.formula_engine.models import FormulaInputNode, FormulaNode, FormulaNodeType
from app.review.models import ReviewItem, ReviewStatus
from app.review.repository import ReviewRepository, make_review_id

BOX = {"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 220.0}
HTML = HtmlLocator(
    cik="9999999",
    accession="0009999999-26-000001",
    document="synthetic-20260630.htm",
    element_path="/html/body/table[1]/tr[2]/td[2]",
)


def _leaf(locator: PdfLocator | HtmlLocator) -> FormulaNode:
    return FormulaNode(
        node_id="leaf_0_synthetic",
        label="Synthetic adjustment",
        node_type=FormulaNodeType.leaf,
        source_node=FormulaInputNode(
            node_id="in-0", normalized_label="Synthetic adjustment", value="1,000",
            label="Reconciliation > 2026 > Synthetic adjustment", record_index=0, locator=locator,
        ),
    )


def test_canonical_locator_key_is_stable_across_representations() -> None:
    from app.extraction.locator import canonical_locator_key

    pdf_model = PdfLocator(page=3, bbox=BOX, source_file="synthetic.pdf")
    pdf_dict = {"source_file": "synthetic.pdf", "type": "pdf", "bbox": {"y1": 220, "x1": 300, "y0": 200, "x0": 100}, "page": 3}
    assert canonical_locator_key(pdf_model) == canonical_locator_key(pdf_dict)
    assert canonical_locator_key(HTML) == canonical_locator_key(HTML.model_dump())
    # The derived source_file alias and the URL do not change identity; the element does.
    with_url = HTML.model_copy(update={"url": "https://www.sec.gov/Archives/edgar/data/9999999/000999999926000001/synthetic-20260630.htm"})
    assert canonical_locator_key(with_url) == canonical_locator_key(HTML)
    other_cell = HTML.model_copy(update={"element_path": "/html/body/table[1]/tr[3]/td[2]"})
    assert canonical_locator_key(other_cell) != canonical_locator_key(HTML)
    assert canonical_locator_key(pdf_model) != canonical_locator_key(HTML)


def test_w3c_record_carries_locator_and_html_text_quote() -> None:
    html_anno = build_w3c_annotation_for_node("job-x", "Source_Inputs", "B2", _leaf(HTML))
    assert html_anno.locator == HTML
    assert html_anno.target.selector is not None
    refined = html_anno.target.selector.refinedBy
    assert refined is not None and refined.type == "TextQuoteSelector"
    assert refined.exact == "1,000"

    pdf = PdfLocator(page=3, bbox=BOX, source_file="synthetic.pdf")
    pdf_anno = build_w3c_annotation_for_node("job-x", "Source_Inputs", "B3", _leaf(pdf))
    assert pdf_anno.locator == pdf
    assert pdf_anno.target.selector is not None and pdf_anno.target.selector.refinedBy is not None
    assert pdf_anno.target.selector.refinedBy.type == "BoundingBox"


def test_audit_trail_finds_the_live_review_item_for_an_html_leaf(tmp_path: Path) -> None:
    job_id = "job-html-trail"
    review_id = make_review_id(job_id, HTML.document, 1, None, locator=HTML)
    ReviewRepository(data_dir=tmp_path).save_review_items(
        job_id,
        [
            ReviewItem(
                id=review_id, value="1,000", label="Synthetic adjustment", locator=HTML,
                confidence_band=ConfidenceBand.needs_review, confidence_score=0.9, status=ReviewStatus.locked,
            )
        ],
    )
    anno = build_w3c_annotation_for_node(job_id, "Source_Inputs", "B2", _leaf(HTML))
    ModelRepository(data_dir=tmp_path).save_provenance_records(job_id, [anno])

    chain = AuditTrailResolver(data_dir=tmp_path).resolve_by_cell(job_id, "Source_Inputs", "B2")
    assert chain.is_found, chain.error_detail
    [component] = chain.components
    assert component.review_status == "locked"


def test_audit_report_tolerates_a_selector_without_bounding_box(tmp_path: Path) -> None:
    hardcode = W3CAnnotationRecord(
        id="urn:footnote:provenance:job-x:Source_Inputs:B9",
        job_id="job-x", sheet_name="Source_Inputs", cell_coord="B9", node_id="hardcode_b9",
        body=W3CBody(value="5", label="Synthetic override"),
        target=W3CTarget(source="urn:footnote:sec:0009999999-26-000001:synthetic-20260630.htm",
                         selector=W3CSelector(type="XPathSelector", value="/html/body/p[1]")),
    )
    overrides = AuditReportCompiler(data_dir=tmp_path)._compile_manual_overrides("job-x", [], [], [hardcode])
    assert [o.item_id for o in overrides] == ["Source_Inputs!B9"]
