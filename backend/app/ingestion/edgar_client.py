"""
SEC EDGAR API Client for Direct Filing Ingestion (Feature 1, Step D).

Adheres to:
- CONSTITUTION §1.1: mypy --strict typing compliance.
- CONSTITUTION §3.8: Ingestion isolation boundary (no imports from extraction/classification/etc).
- SEC Rate & Header Requirements: User-Agent header in SEC compliant format.
"""

import logging
import os
from typing import Any

import httpx

from app.ingestion.models import EdgarCompanyResult, EdgarFiling
from app.ingestion.validation import validate_pdf_bytes

logger = logging.getLogger(__name__)

SEC_USER_AGENT = os.environ.get(
    "SEC_USER_AGENT", "Footnote Research analyst@footnoteresearch.com"
)
SEC_HEADERS: dict[str, str] = {
    "User-Agent": SEC_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}
SEC_WWW_HEADERS: dict[str, str] = {
    "User-Agent": SEC_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov",
}
SEC_EFTS_HEADERS: dict[str, str] = {
    "User-Agent": SEC_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
    "Host": "efts.sec.gov",
}


class EdgarClientError(Exception):
    """Base exception for SEC EDGAR API errors."""


class EdgarCompanyNotFoundError(EdgarClientError):
    """Raised when a company or CIK is not found on EDGAR."""


class EdgarFilingNotFoundError(EdgarClientError):
    """Raised when a requested filing or document is not found."""


class EdgarFetchError(EdgarClientError):
    """Raised when filing bytes cannot be retrieved or fail PDF validation."""


def search_company(
    query: str, client: httpx.Client | None = None
) -> list[EdgarCompanyResult]:
    """
    Search for a company by name, ticker, or CIK using the SEC company tickers directory or EFTS search.

    Args:
        query: Ticker symbol, CIK, or company name search term.
        client: Optional pre-configured httpx.Client for testing.

    Returns:
        List of matching EdgarCompanyResult records.
    """
    clean_q = query.strip()
    if not clean_q:
        return []

    q_upper = clean_q.upper()
    results: list[EdgarCompanyResult] = []

    # 1. Fetch SEC Company Tickers directory
    try:
        if client is not None:
            res = client.get(
                "https://www.sec.gov/files/company_tickers.json",
                headers=SEC_WWW_HEADERS,
                timeout=10.0,
            )
        else:
            with httpx.Client(headers=SEC_WWW_HEADERS, timeout=10.0) as http:
                res = http.get("https://www.sec.gov/files/company_tickers.json")

        if res.status_code == 200:
            data: dict[str, Any] = res.json()
            # Schema is {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
            for entry in data.values():
                if not isinstance(entry, dict):
                    continue
                ticker = str(entry.get("ticker", "")).upper()
                title = str(entry.get("title", ""))
                cik_val = str(entry.get("cik_str", "")).zfill(10)

                if (
                    q_upper == ticker
                    or clean_q.lower() in title.lower()
                    or clean_q.lstrip("0") == str(entry.get("cik_str", ""))
                ):
                    results.append(
                        EdgarCompanyResult(
                            cik=cik_val,
                            company_name=title,
                            ticker=ticker,
                        )
                    )
                    if len(results) >= 20:
                        break
    except Exception as err:  # noqa: BLE001
        logger.warning("SEC company tickers fetch failed: %s", err)

    return results


def get_filings(
    cik: str,
    form_type: str | None = None,
    limit: int = 10,
    client: httpx.Client | None = None,
) -> list[EdgarFiling]:
    """
    Retrieve SEC filing history for a specific company CIK from data.sec.gov.

    Args:
        cik: Central Index Key (CIK) with or without leading zeroes.
        form_type: Optional form type filter (e.g. '10-K', '10-Q').
        limit: Maximum number of filings to return.
        client: Optional pre-configured httpx.Client for testing.

    Returns:
        List of EdgarFiling records sorted by filing date descending.
    """
    clean_cik = cik.strip().zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{clean_cik}.json"

    try:
        if client is not None:
            res = client.get(url, headers=SEC_HEADERS, timeout=10.0)
        else:
            with httpx.Client(headers=SEC_HEADERS, timeout=10.0) as http:
                res = http.get(url)

        if res.status_code == 404:
            raise EdgarCompanyNotFoundError(f"CIK {cik} not found on SEC EDGAR")
        if res.status_code != 200:
            raise EdgarClientError(
                f"SEC EDGAR returned HTTP {res.status_code} for CIK {clean_cik}"
            )

        data: dict[str, Any] = res.json()
        filings_block = data.get("filings", {})
        recent = filings_block.get("recent", {})

        accession_numbers: list[str] = recent.get("accessionNumber", [])
        forms: list[str] = recent.get("form", [])
        filing_dates: list[str] = recent.get("filingDate", [])
        report_dates: list[str] = recent.get("reportDate", [])
        primary_docs: list[str] = recent.get("primaryDocument", [])
        primary_descs: list[str] = recent.get("primaryDocDescription", [])

        filings: list[EdgarFiling] = []
        target_form_upper = form_type.strip().upper() if form_type else None

        for idx in range(len(accession_numbers)):
            f_type = forms[idx] if idx < len(forms) else ""
            if target_form_upper and f_type.upper() != target_form_upper:
                continue

            acc_num = accession_numbers[idx]
            f_date = filing_dates[idx] if idx < len(filing_dates) else ""
            r_date = report_dates[idx] if idx < len(report_dates) else None
            p_doc = primary_docs[idx] if idx < len(primary_docs) else ""
            p_desc = primary_descs[idx] if idx < len(primary_descs) else None

            filing_year: int | None = None
            date_to_parse = r_date or f_date
            if date_to_parse and len(date_to_parse) >= 4:
                try:
                    filing_year = int(date_to_parse[:4])
                except ValueError:
                    filing_year = None

            filings.append(
                EdgarFiling(
                    accession_number=acc_num,
                    form_type=f_type,
                    filing_date=f_date,
                    report_date=r_date,
                    primary_document=p_doc,
                    description=p_desc,
                    filing_year=filing_year,
                )
            )
            if len(filings) >= limit:
                break

        return filings

    except EdgarClientError:
        raise
    except Exception as err:
        logger.error("Failed to retrieve filings for CIK %s: %s", clean_cik, err)
        raise EdgarClientError(f"Error communicating with SEC EDGAR: {err}") from err


def fetch_filing_pdf(
    accession_number: str,
    cik: str,
    primary_document: str | None = None,
    client: httpx.Client | None = None,
) -> bytes:
    """
    Download raw PDF filing binary from SEC EDGAR archives and validate structure.

    Args:
        accession_number: EDGAR accession number (e.g. '0000320193-24-000106').
        cik: Central Index Key (CIK).
        primary_document: Optional primary document filename (e.g. 'aapl-20240928.pdf').
        client: Optional pre-configured httpx.Client for testing.

    Returns:
        Validated raw PDF bytes.

    Raises:
        EdgarFilingNotFoundError: If filing is not found on EDGAR (HTTP 404).
        EdgarFetchError: If download fails or bytes are not a valid PDF.
    """
    acc_clean = accession_number.replace("-", "")
    try:
        cik_int = str(int(cik))
    except ValueError as val_err:
        raise EdgarFetchError(f"Invalid CIK: {cik}") from val_err

    # Possible archive URLs for the document
    urls_to_try: list[str] = []
    if primary_document:
        urls_to_try.append(
            f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{primary_document}"
        )
    urls_to_try.append(
        f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{accession_number}.pdf"
    )

    downloaded_bytes: bytes | None = None
    last_status = 0

    for url in urls_to_try:
        try:
            if client is not None:
                res = client.get(url, headers=SEC_WWW_HEADERS, timeout=15.0)
            else:
                with httpx.Client(headers=SEC_WWW_HEADERS, timeout=15.0) as http:
                    res = http.get(url)

            last_status = res.status_code
            if res.status_code == 200 and res.content:
                downloaded_bytes = res.content
                break
        except Exception as net_err:  # noqa: BLE001
            logger.warning("Error trying EDGAR archive URL %s: %s", url, net_err)

    if downloaded_bytes is None:
        if last_status == 404:
            raise EdgarFilingNotFoundError(
                f"Filing {accession_number} for CIK {cik} not found on SEC EDGAR (HTTP 404)"
            )
        raise EdgarFetchError(
            f"Could not retrieve filing binary for {accession_number} (Status: {last_status})"
        )

    # Validate PDF bytes integrity
    validation_res = validate_pdf_bytes(
        filename=primary_document or f"{accession_number}.pdf",
        content=downloaded_bytes,
    )
    if not validation_res.accepted:
        raise EdgarFetchError(
            f"EDGAR file is not a valid PDF: {validation_res.error_message}"
        )

    return downloaded_bytes
