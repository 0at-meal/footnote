"""
Unit tests for SEC EDGAR Direct Integration (Step D).

Tests:
- search_company with mocked SEC company tickers JSON
- get_filings with mocked submissions JSON
- fetch_filing_pdf with valid and invalid PDF bytes
- 404 handling surfacing as structured error
- router endpoints GET /upload/edgar/search, GET /upload/edgar/filings/{cik}, POST /upload/edgar
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from app.ingestion.company_repository import CompanyRepository
from app.ingestion.edgar_client import (
    EdgarCompanyNotFoundError,
    EdgarFetchError,
    fetch_filing_pdf,
    get_filings,
    search_company,
)
from app.ingestion.models import EdgarCompanyResult, EdgarFiling
from app.ingestion.repository import JobRepository
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

MOCK_COMPANY_TICKERS = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
    "2": {"cik_str": 1018724, "ticker": "AMZN", "title": "AMAZON COM INC"},
}

MOCK_SUBMISSIONS = {
    "cik": "0000320193",
    "entityType": "operating",
    "sic": "3571",
    "name": "Apple Inc.",
    "tickers": ["AAPL"],
    "filings": {
        "recent": {
            "accessionNumber": [
                "0000320193-24-000106",
                "0000320193-24-000069",
                "0000320193-23-000106",
            ],
            "filingDate": ["2024-11-01", "2024-08-02", "2023-11-03"],
            "reportDate": ["2024-09-28", "2024-06-29", "2023-09-30"],
            "form": ["10-K", "10-Q", "10-K"],
            "primaryDocument": [
                "aapl-20240928.pdf",
                "aapl-20240629.pdf",
                "aapl-20230930.pdf",
            ],
            "primaryDocDescription": [
                "FORM 10-K ANNUAL REPORT",
                "FORM 10-Q QUARTERLY REPORT",
                "FORM 10-K ANNUAL REPORT",
            ],
        }
    },
}

SAMPLE_VALID_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF"


def test_search_company_by_ticker() -> None:
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = MOCK_COMPANY_TICKERS

    mock_http = MagicMock(spec=httpx.Client)
    mock_http.get.return_value = mock_res

    results = search_company("AAPL", client=mock_http)
    assert len(results) == 1
    assert results[0].cik == "0000320193"
    assert results[0].company_name == "Apple Inc."
    assert results[0].ticker == "AAPL"


def test_search_company_by_name_substring() -> None:
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = MOCK_COMPANY_TICKERS

    mock_http = MagicMock(spec=httpx.Client)
    mock_http.get.return_value = mock_res

    results = search_company("microsoft", client=mock_http)
    assert len(results) == 1
    assert results[0].ticker == "MSFT"


def test_get_filings_success() -> None:
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = MOCK_SUBMISSIONS

    mock_http = MagicMock(spec=httpx.Client)
    mock_http.get.return_value = mock_res

    filings = get_filings("320193", client=mock_http)
    assert len(filings) == 3
    assert filings[0].accession_number == "0000320193-24-000106"
    assert filings[0].form_type == "10-K"
    assert filings[0].filing_year == 2024


def test_get_filings_form_type_filter() -> None:
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = MOCK_SUBMISSIONS

    mock_http = MagicMock(spec=httpx.Client)
    mock_http.get.return_value = mock_res

    filings_10k = get_filings("320193", form_type="10-K", client=mock_http)
    assert len(filings_10k) == 2
    assert all(f.form_type == "10-K" for f in filings_10k)


def test_get_filings_404_raises_company_not_found() -> None:
    mock_res = MagicMock()
    mock_res.status_code = 404

    mock_http = MagicMock(spec=httpx.Client)
    mock_http.get.return_value = mock_res

    with pytest.raises(EdgarCompanyNotFoundError):
        get_filings("9999999999", client=mock_http)


def test_fetch_filing_pdf_success() -> None:
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.content = SAMPLE_VALID_PDF

    mock_http = MagicMock(spec=httpx.Client)
    mock_http.get.return_value = mock_res

    pdf_bytes = fetch_filing_pdf(
        accession_number="0000320193-24-000106",
        cik="320193",
        primary_document="aapl-20240928.pdf",
        client=mock_http,
    )
    assert pdf_bytes.startswith(b"%PDF")


def test_fetch_filing_pdf_invalid_bytes_raises_fetch_error() -> None:
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.content = b"<html>Not a PDF</html>"

    mock_http = MagicMock(spec=httpx.Client)
    mock_http.get.return_value = mock_res

    with pytest.raises(EdgarFetchError):
        fetch_filing_pdf(
            accession_number="0000320193-24-000106",
            cik="320193",
            client=mock_http,
        )


def test_edgar_search_endpoint() -> None:
    with patch("app.ingestion.router.search_company") as mock_search:
        mock_search.return_value = [
            EdgarCompanyResult(
                cik="0000320193", company_name="Apple Inc.", ticker="AAPL"
            )
        ]
        res = client.get("/upload/edgar/search?q=AAPL")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["ticker"] == "AAPL"


def test_edgar_filings_endpoint() -> None:
    with patch("app.ingestion.router.get_filings") as mock_get:
        mock_get.return_value = [
            EdgarFiling(
                accession_number="0000320193-24-000106",
                form_type="10-K",
                filing_date="2024-11-01",
                report_date="2024-09-28",
                primary_document="aapl-20240928.pdf",
                description="10-K",
                filing_year=2024,
            )
        ]
        res = client.get("/upload/edgar/filings/0000320193")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["form_type"] == "10-K"


def test_edgar_submit_endpoint(tmp_path: Path) -> None:
    job_repo = JobRepository(data_dir=tmp_path)
    company_repo = CompanyRepository(data_dir=tmp_path)

    from app.ingestion.router import get_company_repository, get_repository

    app.dependency_overrides[get_repository] = lambda: job_repo
    app.dependency_overrides[get_company_repository] = lambda: company_repo

    try:
        with (
            patch(
                "app.ingestion.router.fetch_filing_pdf", return_value=SAMPLE_VALID_PDF
            ),
            patch("app.ingestion.router.process_queued_job"),
        ):
            res = client.post(
                "/upload/edgar",
                json={
                    "cik": "0000320193",
                    "accession_number": "0000320193-24-000106",
                    "target_metric": "Adjusted EBITDA",
                    "filing_year": 2024,
                    "company_name": "Apple Inc.",
                    "primary_document": "aapl-20240928.pdf",
                },
            )
            assert res.status_code == 200
            job_data = res.json()
            assert job_data["status"] == "queued"
            assert job_data["target_metric"] == "Adjusted EBITDA"
            assert job_data["filing_year"] == 2024
            assert job_data["company_id"] is not None

            jobs = job_repo.list_jobs()
            assert len(jobs) == 1
            assert jobs[0].job_id == job_data["job_id"]
    finally:
        app.dependency_overrides.clear()
