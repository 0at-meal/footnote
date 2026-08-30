"""
Unit tests for Narrative Section Extraction, Diffing, and Endpoints (Step G).

Tests:
- Tokenization and deterministic diffing with difflib.
- Zero-diff on identical text (similarity = 1.0).
- Insertion, deletion, replacement token handling and token counts.
- Section extraction from text and structured records.
- Router endpoints GET /narrative/{job_id}/sections and POST /narrative/{company_id}/diff.
"""

from pathlib import Path

from app.ingestion.repository import JobRepository
from app.main import app
from app.narrative.differ import diff_narrative_sections, tokenize_narrative_text
from app.narrative.extractor import (
    extract_narrative_sections_from_text,
)
from app.narrative.models import NarrativeSection
from app.narrative.repository import NarrativeRepository
from app.narrative.router import get_job_repository, get_narrative_repository
from fastapi.testclient import TestClient

client = TestClient(app)


def test_tokenize_narrative_text() -> None:
    tokens = tokenize_narrative_text("Revenue increased by 15% in 2024.")
    assert "Revenue" in tokens
    assert "15%" in tokens
    assert "2024." in tokens


def test_diff_narrative_sections_identical() -> None:
    text = (
        "Total revenue was $1,500 million for the fiscal year ended December 31, 2024."
    )
    s1 = NarrativeSection(
        job_id="job-1",
        item_number="Item 7",
        title="Item 7. MD&A",
        text=text,
    )
    s2 = NarrativeSection(
        job_id="job-2",
        item_number="Item 7",
        title="Item 7. MD&A",
        text=text,
    )

    diff = diff_narrative_sections(s1, s2)
    assert diff.similarity_ratio == 1.0
    assert diff.added_tokens == 0
    assert diff.removed_tokens == 0
    assert diff.unchanged_tokens > 0
    assert all(t.type == "equal" for t in diff.tokens)


def test_diff_narrative_sections_modifications() -> None:
    s_early = NarrativeSection(
        job_id="job-2023",
        item_number="Item 7",
        title="Item 7. MD&A",
        text="We expect macroeconomic headwinds to moderate in the fourth quarter.",
    )
    s_late = NarrativeSection(
        job_id="job-2024",
        item_number="Item 7",
        title="Item 7. MD&A",
        text="We expect macroeconomic headwinds and supply constraints to persist into 2025.",
    )

    diff = diff_narrative_sections(s_early, s_late, company_id="comp-1")
    assert diff.similarity_ratio < 1.0
    assert diff.added_tokens > 0
    assert diff.removed_tokens > 0

    inserted_texts = [t.text for t in diff.tokens if t.type == "insert"]
    deleted_texts = [t.text for t in diff.tokens if t.type == "delete"]

    assert any(
        "supply constraints" in txt or "persist" in txt for txt in inserted_texts
    )
    assert any("moderate" in txt or "fourth" in txt for txt in deleted_texts)


def test_extract_narrative_sections_from_text() -> None:
    doc = """
    PART I
    Item 1. Business
    We design semiconductors.

    Item 1A. Risk Factors
    Our operations are subject to global supply chain disruptions and geopolitical risks.

    Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations
    Net revenues increased 25% year-over-year driven by cloud data center demand.

    Item 8. Financial Statements
    Consolidated Balance Sheets.
    """

    sections = extract_narrative_sections_from_text("job-doc", doc)
    assert len(sections) == 2

    mda = next((s for s in sections if s.item_number == "Item 7"), None)
    assert mda is not None
    assert "Net revenues increased 25%" in mda.text

    rf = next((s for s in sections if s.item_number == "Item 1A"), None)
    assert rf is not None
    assert "supply chain disruptions" in rf.text


def test_narrative_router_endpoints(tmp_path: Path) -> None:
    job_repo = JobRepository(data_dir=tmp_path)
    job1 = job_repo.save_job(
        filename="filing2023.pdf",
        content=b"%PDF-1.4 2023",
        target_metric="Adjusted EBITDA",
        filing_year=2023,
    )
    job2 = job_repo.save_job(
        filename="filing2024.pdf",
        content=b"%PDF-1.4 2024",
        target_metric="Adjusted EBITDA",
        filing_year=2024,
    )

    narrative_repo = NarrativeRepository(data_dir=tmp_path)

    # Save sections
    s1 = NarrativeSection(
        job_id=job1.job_id,
        item_number="Item 7",
        title="Item 7. MD&A",
        text="Operating margin expanded 150 basis points.",
    )
    s2 = NarrativeSection(
        job_id=job2.job_id,
        item_number="Item 7",
        title="Item 7. MD&A",
        text="Operating margin contracted 50 basis points due to higher SG&A costs.",
    )
    narrative_repo.save_sections(job1.job_id, [s1])
    narrative_repo.save_sections(job2.job_id, [s2])

    app.dependency_overrides[get_job_repository] = lambda: job_repo
    app.dependency_overrides[get_narrative_repository] = lambda: narrative_repo

    try:
        # 1. GET /narrative/{job_id}/sections
        res1 = client.get(f"/narrative/{job1.job_id}/sections")
        assert res1.status_code == 200
        sections_data = res1.json()
        assert len(sections_data) == 1
        assert sections_data[0]["item_number"] == "Item 7"

        # 2. POST /narrative/{company_id}/diff
        diff_res = client.post(
            "/narrative/comp-test/diff",
            json={
                "earlier_job_id": job1.job_id,
                "later_job_id": job2.job_id,
                "item_number": "Item 7",
            },
        )
        assert diff_res.status_code == 200
        diff_data = diff_res.json()
        assert diff_data["earlier_job_id"] == job1.job_id
        assert diff_data["later_job_id"] == job2.job_id
        assert diff_data["added_tokens"] > 0
        assert diff_data["removed_tokens"] > 0
    finally:
        app.dependency_overrides.clear()
