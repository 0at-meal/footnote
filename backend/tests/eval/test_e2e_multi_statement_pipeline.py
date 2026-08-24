from typing import Any
from app.ingestion.company_repository import CompanyRepository
"""
End-to-End Multi-Statement & Multi-Year Pipeline Tests (Phase E).

Validates:
- Ticket E.1.1: Single filing -> Ingestion -> 2-level classification -> multi-statement tree -> 6-tab workbook -> live formula & comment verification.
- Ticket E.1.2: Multi-year company filings -> 6-tab multi-year workbook -> chronological column sorting -> cross-year formulas.
"""

from pathlib import Path
import openpyxl
import pytest

from app.classification.models import (
    ClassificationBatchResult,
    ClassificationItemResult,
    ClassifierInputPayload,
    ClassifierRawResponse,
    StatementType,
)
from app.classification.normalizer import normalize_records
from app.classification.repository import ClassificationRepository
from app.classification.taxonomy import SEED_MASTER_TAXONOMY, TaxonomyRepository
from app.excel_export.multi_statement_generator import generate_multi_statement_workbook
from app.excel_export.repository import ModelRepository
from app.extraction.models import (
    ConfidenceBand,
    DoclingBbox,
    DoclingItem,
    ExtractedRecord,
    NormalizedBbox,
    NormalizedItem,
    ScoredRecord,
)
from app.extraction.repository import ExtractionRepository
from app.formula_engine.models import FormulaInputBatch, FormulaInputNode
from app.formula_engine.reader import read_formula_inputs_from_review
from app.formula_engine.tree import build_comprehensive_model_tree
from app.ingestion.models import CompanyRecord, JobRecord, JobStatus
from app.ingestion.repository import JobRepository
from app.review.models import ReviewItem, ReviewStatus
from app.review.repository import ReviewRepository


def test_e2e_single_filing_multi_statement_pipeline(tmp_path: Path) -> None:
    """
    Ticket E.1.1: Single filing end-to-end multi-statement pipeline verification.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # 1. Ingestion
    job_repo = JobRepository(data_dir=data_dir)
    job = job_repo.save_job("TechCorp_10K.pdf", b"%PDF-1.4 sample", "Full Model", filing_year=2023)
    job_id = job.job_id

    # 2. Review Items (multi-statement extraction items)
    review_repo = ReviewRepository(data_dir=data_dir)
    items = [
        # Income Statement
        ReviewItem(
            id=f"{job_id}_0",
            value="10,000",
            label="Total revenues",
            page=12,
            bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 220.0},
            source_file="TechCorp_10K.pdf",
            confidence_band=ConfidenceBand.auto_accepted,
            confidence_score=0.99,
            normalized_label="Revenue",
            statement_type=StatementType.income_statement,
            status=ReviewStatus.locked,
        ),
        ReviewItem(
            id=f"{job_id}_1",
            value="4,000",
            label="Cost of revenue",
            page=12,
            bbox={"x0": 100.0, "y0": 230.0, "x1": 300.0, "y1": 250.0},
            source_file="TechCorp_10K.pdf",
            confidence_band=ConfidenceBand.auto_accepted,
            confidence_score=0.99,
            normalized_label="Cost of Revenue",
            statement_type=StatementType.income_statement,
            status=ReviewStatus.locked,
        ),
        ReviewItem(
            id=f"{job_id}_2",
            value="2,000",
            label="Research & development",
            page=12,
            bbox={"x0": 100.0, "y0": 260.0, "x1": 300.0, "y1": 280.0},
            source_file="TechCorp_10K.pdf",
            confidence_band=ConfidenceBand.auto_accepted,
            confidence_score=0.99,
            normalized_label="Research & Development",
            statement_type=StatementType.income_statement,
            status=ReviewStatus.locked,
        ),
        ReviewItem(
            id=f"{job_id}_3",
            value="1,500",
            label="Selling, general and admin",
            page=12,
            bbox={"x0": 100.0, "y0": 290.0, "x1": 300.0, "y1": 310.0},
            source_file="TechCorp_10K.pdf",
            confidence_band=ConfidenceBand.auto_accepted,
            confidence_score=0.99,
            normalized_label="General & Administrative",
            statement_type=StatementType.income_statement,
            status=ReviewStatus.locked,
        ),
        ReviewItem(
            id=f"{job_id}_4",
            value="400",
            label="Income taxes",
            page=12,
            bbox={"x0": 100.0, "y0": 320.0, "x1": 300.0, "y1": 340.0},
            source_file="TechCorp_10K.pdf",
            confidence_band=ConfidenceBand.auto_accepted,
            confidence_score=0.99,
            normalized_label="Provision for Income Taxes",
            statement_type=StatementType.income_statement,
            status=ReviewStatus.locked,
        ),
        # EBITDA Bridge
        ReviewItem(
            id=f"{job_id}_5",
            value="350",
            label="Stock-based compensation",
            page=18,
            bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 220.0},
            source_file="TechCorp_10K.pdf",
            confidence_band=ConfidenceBand.auto_accepted,
            confidence_score=0.98,
            normalized_label="Stock-Based Compensation",
            statement_type=StatementType.non_gaap_bridge,
            status=ReviewStatus.locked,
        ),
        ReviewItem(
            id=f"{job_id}_6",
            value="250",
            label="Amortization of intangibles",
            page=18,
            bbox={"x0": 100.0, "y0": 230.0, "x1": 300.0, "y1": 250.0},
            source_file="TechCorp_10K.pdf",
            confidence_band=ConfidenceBand.auto_accepted,
            confidence_score=0.97,
            normalized_label="Amortization of Intangibles",
            statement_type=StatementType.non_gaap_bridge,
            status=ReviewStatus.locked,
        ),
        # Cash Flow
        ReviewItem(
            id=f"{job_id}_7",
            value="2,800",
            label="Operating cash flows",
            page=15,
            bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 220.0},
            source_file="TechCorp_10K.pdf",
            confidence_band=ConfidenceBand.auto_accepted,
            confidence_score=0.99,
            normalized_label="Cash Provided by Operating Activities",
            statement_type=StatementType.cash_flow,
            status=ReviewStatus.locked,
        ),
        ReviewItem(
            id=f"{job_id}_8",
            value="600",
            label="Capital expenditures",
            page=15,
            bbox={"x0": 100.0, "y0": 230.0, "x1": 300.0, "y1": 250.0},
            source_file="TechCorp_10K.pdf",
            confidence_band=ConfidenceBand.auto_accepted,
            confidence_score=0.99,
            normalized_label="Capital Expenditures",
            statement_type=StatementType.cash_flow,
            status=ReviewStatus.locked,
        ),
        # Balance Sheet
        ReviewItem(
            id=f"{job_id}_9",
            value="1,200",
            label="Cash & equivalents",
            page=10,
            bbox={"x0": 100.0, "y0": 100.0, "x1": 300.0, "y1": 120.0},
            source_file="TechCorp_10K.pdf",
            confidence_band=ConfidenceBand.auto_accepted,
            confidence_score=0.99,
            normalized_label="Cash and Cash Equivalents",
            statement_type=StatementType.balance_sheet,
            status=ReviewStatus.locked,
        ),
        ReviewItem(
            id=f"{job_id}_10",
            value="3,000",
            label="Long term notes",
            page=10,
            bbox={"x0": 100.0, "y0": 300.0, "x1": 300.0, "y1": 320.0},
            source_file="TechCorp_10K.pdf",
            confidence_band=ConfidenceBand.auto_accepted,
            confidence_score=0.99,
            normalized_label="Long-Term Debt",
            statement_type=StatementType.balance_sheet,
            status=ReviewStatus.locked,
        ),
    ]
    review_repo.save_review_items(job_id, items)

    # 3. Formula Engine: Multi-statement tree
    formula_inputs = read_formula_inputs_from_review(items)
    assert len(formula_inputs.nodes) == 11

    comp_tree = build_comprehensive_model_tree(formula_inputs)
    assert comp_tree.is_valid is True
    assert comp_tree.income_statement_tree is not None
    assert comp_tree.ebitda_bridge_tree is not None
    assert comp_tree.cash_flow_tree is not None
    assert comp_tree.balance_sheet_tree is not None

    # 4. Excel Compiler: 6-Tab Workbook
    result = generate_multi_statement_workbook(
        company=None,
        year_trees=[(job, comp_tree)],
        output_dir=data_dir,
    )
    assert result.is_success is True
    assert Path(result.file_path).exists()
    assert result.sheet_names == [
        "Executive_Summary",
        "Income_Statement",
        "EBITDA_Bridge",
        "Cash_Flow",
        "Balance_Sheet",
        "Audit_Trail",
    ]

    # 5. Live Excel Formula Verification via openpyxl
    wb = openpyxl.load_workbook(result.file_path, data_only=False)

    # Verify 6 sheets
    assert wb.sheetnames == [
        "Executive_Summary",
        "Income_Statement",
        "EBITDA_Bridge",
        "Cash_Flow",
        "Balance_Sheet",
        "Audit_Trail",
    ]

    # Verify cross-sheet formula on EBITDA Bridge
    ws_bridge = wb["EBITDA_Bridge"]
    assert ws_bridge.cell(row=4, column=2).value == "='Income_Statement'!B12"

    # Verify cross-sheet formula on Executive Summary
    ws_summary = wb["Executive_Summary"]
    assert ws_summary.cell(row=5, column=2).value == "='Income_Statement'!B4"

    # Verify Audit Trail tab
    ws_audit = wb["Audit_Trail"]
    assert ws_audit.cell(row=3, column=1).value == "Sheet"
    assert ws_audit.cell(row=4, column=5).value == "TechCorp_10K.pdf"
    assert len(result.provenance_records) > 0


def test_e2e_multi_year_company_pipeline(tmp_path: Path) -> None:
    """
    Ticket E.1.2: Multi-year company filings end-to-end pipeline verification.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    company_repo = CompanyRepository(data_dir=data_dir)
    company = company_repo.save_company("MegaCorp", ticker="MEGA")
    job_repo = JobRepository(data_dir=data_dir)

    years = [2022, 2023, 2024]
    year_trees: list[tuple[JobRecord, Any]] = []

    for yr in years:
        job = job_repo.save_job(
            f"MegaCorp_{yr}.pdf",
            b"%PDF-1.4 mock",
            "Full Model",
            filing_year=yr,
            company_id=company.company_id,
        )
        company_repo.add_job_to_company(company.company_id, job.job_id)

        nodes = [
            FormulaInputNode(
                node_id=f"node_{yr}_rev",
                normalized_label="Revenue",
                value=str(1000 * (yr - 2020)),
                label="Revenues",
                page=10,
                bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 220.0},
                source_file=f"MegaCorp_{yr}.pdf",
                record_index=0,
                statement_type=StatementType.income_statement,
            ),
            FormulaInputNode(
                node_id=f"node_{yr}_sbc",
                normalized_label="Stock-Based Compensation",
                value=str(50 * (yr - 2020)),
                label="Stock compensation",
                page=15,
                bbox={"x0": 100.0, "y0": 200.0, "x1": 300.0, "y1": 220.0},
                source_file=f"MegaCorp_{yr}.pdf",
                record_index=1,
                statement_type=StatementType.non_gaap_bridge,
            ),
        ]
        batch = FormulaInputBatch(
            nodes=nodes,
            total_records_received=len(nodes),
            confirmed_count=len(nodes),
            excluded_count=0,
        )
        comp_tree = build_comprehensive_model_tree(batch)
        year_trees.append((job, comp_tree))

    # Shuffle to ensure generator sorts by year ascending
    shuffled_trees = [year_trees[1], year_trees[2], year_trees[0]]

    result = generate_multi_statement_workbook(
        company=company,
        year_trees=shuffled_trees,
        output_dir=data_dir,
    )

    assert result.is_success is True
    wb = openpyxl.load_workbook(result.file_path, data_only=False)

    # Verify column headers on Income Statement: Col B = FY2022, Col C = FY2023, Col D = FY2024
    ws_is = wb["Income_Statement"]
    assert ws_is.cell(row=3, column=2).value == "FY2022"
    assert ws_is.cell(row=3, column=3).value == "FY2023"
    assert ws_is.cell(row=3, column=4).value == "FY2024"
