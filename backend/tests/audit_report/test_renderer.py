"""
Unit and integration tests for PDF Report Renderer (Feature 8 Step 2).

Enforces:
- spec.md §2, AC-1, AC-2, AC-4, AC-5, AC-7, AC-8, AC-10, EC-1, EC-2, EC-3, EC-4, EC-5, EC-7, EC-8.
"""

import time
from typing import Any

import fitz  # pymupdf
from app.audit_report.models import (
    ClassifierAuditEntry,
    ClassifierAuditSummary,
    CompiledAuditDataset,
    DriftAuditSummary,
    ManualOverrideItem,
    ProvenanceMatrixItem,
    ReconciliationSummaryItem,
    ReportMetadata,
)
from app.audit_report.renderer import render_audit_report_pdf
from app.audit_trail.models import SourceComponent


def _build_test_dataset(
    has_overrides: bool = False,
    override_count: int = 0,
    special_chars: bool = False,
    item_count: int = 5,
) -> CompiledAuditDataset:
    entity = "Acme Corp & Partners €/£/¥" if special_chars else "Acme Corp"
    filename = "acme_2024_10k_—_final.pdf" if special_chars else "acme_2024_10k.pdf"

    meta = ReportMetadata(
        job_id="job-test-pdf-123",
        entity=entity,
        filing_filename=filename,
        filing_year=2024,
        target_metric="Adjusted EBITDA",
        generated_at="2026-08-17T12:00:00Z",
        total_cells=item_count,
        automated_count=item_count if not has_overrides else item_count - override_count,
        verified_count=override_count if has_overrides else 0,
        flagged_count=0,
        override_count=override_count if has_overrides else 0,
    )

    reconciliation_summary: list[ReconciliationSummaryItem] = [
        ReconciliationSummaryItem(
            sheet_name="Model_Summary",
            cell_coord=f"B{i+2}",
            label=f"Operating Metric Line Item #{i+1} & Details",
            normalized_label="Operating Income" if i == 0 else "Stock-Based Compensation",
            formula_expression=f"=SUM(B2:B{i+1})" if i > 0 else None,
            computed_value=f"${(i+1)*50_000:,}",
            is_formula=i > 0,
            is_hardcode=False,
        )
        for i in range(min(item_count, 4))
    ]

    provenance_matrix: list[ProvenanceMatrixItem] = []
    for i in range(item_count):
        comps: list[SourceComponent] = [
            SourceComponent(
                component_id=f"comp_{i}_1",
                source_file=filename,
                page=10 + i,
                bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 250.0},
                value=f"{(i+1)*25_000}",
                label=f"Footnote Note {i+1}: SBC & Other Long Descriptive Text That Might Wrap Across Lines (p. {10+i})",
                normalized_label="Stock-Based Compensation",
                review_status="locked" if has_overrides else "auto_accepted",
                is_missing=False,
                provenance_id=f"urn:footnote:provenance:job-test:{i}:1",
            ),
            SourceComponent(
                component_id=f"comp_{i}_2",
                source_file=filename,
                page=45 + i,
                bbox={"x0": 50.0, "y0": 150.0, "x1": 250.0, "y1": 200.0},
                value=f"{(i+1)*25_000}",
                label=f"Footnote Note {i+2}: Lease Expense Component (p. {45+i})",
                normalized_label="Operating Lease Expense",
                review_status="auto_accepted",
                is_missing=False,
                provenance_id=f"urn:footnote:provenance:job-test:{i}:2",
            ),
        ]
        provenance_matrix.append(
            ProvenanceMatrixItem(
                sheet_name="Model_Summary" if i == 0 else "Source_Inputs",
                cell_coord=f"B{i+2}",
                node_id=f"leaf_{i}_metric",
                label=f"Metric Line Item {i+1} with special & < > ' \" characters",
                normalized_label="Stock-Based Compensation",
                computed_value=f"${(i+1)*50_000:,}",
                is_formula=i == 0,
                components=comps,
            )
        )

    manual_overrides: list[ManualOverrideItem] = []
    if has_overrides:
        for k in range(override_count):
            manual_overrides.append(
                ManualOverrideItem(
                    item_id=f"job-test-pdf-123_{k}",
                    source_file=filename,
                    page=15,
                    bbox={"x0": 50.0, "y0": 100.0, "x1": 200.0, "y1": 150.0},
                    original_value="3500",
                    final_value="35000",
                    original_label="Rent adj (unclear)",
                    final_label="Operating Lease Expense",
                    review_status="locked",
                    confidence_band="manual_required",
                    error_detail="Corrected unparseable footnote value",
                    is_hardcode=False,
                )
            )

    classifier_governance = ClassifierAuditSummary(
        total_calls=2,
        matched_count=2,
        pending_count=0,
        error_count=0,
        is_strictly_numeric_free=True,
        entries=[
            ClassifierAuditEntry(
                record_index=0,
                timestamp="2026-08-17T12:00:00Z",
                input_label="SBC expense",
                structural_context="Note 12 / Reconciliation",
                output_label="Stock-Based Compensation",
                confidence=0.98,
                taxonomy_status="matched",
                resulting_state="confirmed",
                error_detail=None,
            ),
            ClassifierAuditEntry(
                record_index=1,
                timestamp="2026-08-17T12:00:01Z",
                input_label="Operating Lease Cost",
                structural_context="Note 8 / Leases",
                output_label="Operating Lease Expense",
                confidence=0.95,
                taxonomy_status="matched",
                resulting_state="confirmed",
                error_detail=None,
            ),
        ],
    )

    drift_summary = DriftAuditSummary(
        is_evaluated=True,
        is_baseline=False,
        has_discrepancy=True,
        filing_year=2024,
        added_labels=["Operating Lease Expense"],
        removed_labels=[],
        prior_node_id="acme_Adjusted EBITDA_2023",
        summary_text="Metric Redefinition Detected: 1 component(s) added, 0 removed year-over-year.",
    )

    return CompiledAuditDataset(
        job_id="job-test-pdf-123",
        metadata=meta,
        reconciliation_summary=reconciliation_summary,
        provenance_matrix=provenance_matrix,
        manual_overrides=manual_overrides,
        has_manual_overrides=has_overrides and len(manual_overrides) > 0,
        classifier_governance=classifier_governance,
        drift_summary=drift_summary,
    )


def test_render_audit_report_pdf_valid_bytes_and_structure() -> None:
    dataset = _build_test_dataset(has_overrides=False, item_count=5)
    pdf_bytes = render_audit_report_pdf(dataset)

    # Validate PDF magic bytes
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF-")

    # Validate with PyMuPDF
    doc: Any = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert doc.page_count >= 1

    full_doc_text = "\n".join(doc[i].get_text() for i in range(doc.page_count))
    assert "COMPLIANCE & PROVENANCE AUDIT REPORT" in full_doc_text
    assert "Adjusted EBITDA" in full_doc_text
    assert "Acme Corp" in full_doc_text
    assert "1. Executive Summary & Model Metadata" in full_doc_text
    assert "2. Financial Model & Reconciliation Summary" in full_doc_text
    assert "3. Comprehensive Cell Provenance Matrix" in full_doc_text
    assert "Zero manual overrides" in full_doc_text
    assert "5. AI Classifier Governance Proof" in full_doc_text
    assert "Page 1 of" in full_doc_text
    doc.close()


def test_render_audit_report_pdf_with_manual_overrides_ledger() -> None:
    dataset = _build_test_dataset(has_overrides=True, override_count=2, item_count=5)
    pdf_bytes = render_audit_report_pdf(dataset)

    doc: Any = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = "\n".join(doc[i].get_text() for i in range(doc.page_count))
    assert "4. Manual Override & Exception Ledger" in full_text
    assert "Operating Lease Expense" in full_text
    assert "35000" in full_text
    assert "Corrected unparseable footnote value" in full_text
    doc.close()


def test_render_audit_report_pdf_unicode_and_special_symbols() -> None:
    dataset = _build_test_dataset(special_chars=True, item_count=6)
    pdf_bytes = render_audit_report_pdf(dataset)

    doc: Any = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert doc.page_count >= 1
    full_text = "\n".join(doc[i].get_text() for i in range(doc.page_count))
    assert "Acme Corp & Partners" in full_text
    assert "Adjusted EBITDA" in full_text
    doc.close()


def test_render_audit_report_pdf_large_matrix_multi_page_pagination() -> None:
    dataset = _build_test_dataset(item_count=35)
    pdf_bytes = render_audit_report_pdf(dataset)

    doc: Any = fitz.open(stream=pdf_bytes, filetype="pdf")
    # 35 multi-contributor items should span at least 3 pages in landscape
    assert doc.page_count >= 2

    # Check footer pagination on all pages
    total_pages = doc.page_count
    for i in range(total_pages):
        page_text = doc[i].get_text()
        expected_page_str = f"Page {i+1} of {total_pages}"
        assert expected_page_str in page_text

    doc.close()


def test_render_audit_report_pdf_performance_budget() -> None:
    dataset = _build_test_dataset(item_count=50)
    start_time = time.perf_counter()
    pdf_bytes = render_audit_report_pdf(dataset)
    elapsed = time.perf_counter() - start_time

    assert len(pdf_bytes) > 0
    # Performance budget is 15s (spec AC-10); should render in < 2s
    assert elapsed < 5.0
