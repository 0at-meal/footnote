"""
SEC EDGAR Client for direct filing ingestion and submissions API (FN-020).

Implements:
- Ticker-to-CIK resolution with 10-digit zero padding.
- SEC Submissions API parsing returning typed FilingRef.
- Exhibit discovery (including EX-99.1 for FN-022).
- Token-bucket rate limiting (<= 10 req/s per SEC fair access).
- Retries with backoff and CircuitBreaker.
- Immutable accession-based disk caching.
- Explicit ForeignFilerUnsupportedError on 20-F, 40-F, 6-K (Invariant I3).
"""

import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

from app.ingestion.edgar.circuit_breaker import CircuitBreaker
from app.ingestion.edgar.models import (
    EdgarClientError,
    EdgarCompanyNotFoundError,
    EdgarFilingNotFoundError,
    EdgarRateLimitError,
    FilingDocument,
    FilingExhibit,
    FilingRef,
    ForeignFilerUnsupportedError,
)
from app.ingestion.edgar.rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger(__name__)

DEFAULT_SEC_USER_AGENT = os.environ.get(
    "SEC_USER_AGENT", "Footnote Research analyst@footnoteresearch.com"
)
FOREIGN_FORMS = {"20-F", "20-F/A", "40-F", "40-F/A", "6-K", "6-K/A"}


class EdgarClient:
    """
    Client for interacting with SEC EDGAR APIs and document repositories.
    """

    def __init__(
        self,
        user_agent: str | None = None,
        cache_dir: Path | str | None = None,
        rate_limiter: TokenBucketRateLimiter | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        http_client: httpx.Client | None = None,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ) -> None:
        self.user_agent = user_agent or DEFAULT_SEC_USER_AGENT
        if "@" not in self.user_agent or " " not in self.user_agent:
            # SEC fair access requires Sample Company AdminContact@<sample company domain>.com
            logger.warning("SEC_USER_AGENT may not meet SEC guidelines: %s", self.user_agent)

        self.cache_dir = Path(cache_dir or os.environ.get("EDGAR_CACHE_DIR", "data/edgar_cache"))
        self.rate_limiter = rate_limiter or TokenBucketRateLimiter(rate=10.0, capacity=10.0)
        self.circuit_breaker = circuit_breaker or CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
        self._http_client = http_client
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

        self._ticker_map: dict[str, str] = {}
        self._ticker_map_loaded = False

    def _get_headers(self, host: str = "data.sec.gov") -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Host": host,
        }

    def _request_with_retry(
        self,
        url: str,
        host: str = "data.sec.gov",
        timeout: float = 15.0,
    ) -> httpx.Response:
        """Executes an HTTP GET with rate-limiting, circuit-breaking, and backoff retries."""
        last_exception: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            # Check rate limiter and circuit breaker
            self.rate_limiter.acquire(tokens=1.0)
            self.circuit_breaker.before_request()

            try:
                if self._http_client is not None:
                    res = self._http_client.get(
                        url,
                        headers=self._get_headers(host=host),
                        timeout=timeout,
                    )
                else:
                    with httpx.Client(
                        headers=self._get_headers(host=host),
                        timeout=timeout,
                        follow_redirects=True,
                    ) as client:
                        res = client.get(url)

                if res.status_code == 429:
                    self.circuit_breaker.record_failure()
                    raise EdgarRateLimitError(f"SEC EDGAR returned 429 Too Many Requests for URL: {url}")

                if res.status_code >= 500:
                    self.circuit_breaker.record_failure()
                    res.raise_for_status()

                # Success
                self.circuit_breaker.record_success()
                return res

            except (httpx.RequestError, httpx.HTTPStatusError, EdgarRateLimitError) as exc:
                last_exception = exc
                if attempt == self.max_retries:
                    self.circuit_breaker.record_failure()
                    break
                sleep_sec = self.backoff_factor * (2 ** (attempt - 1))
                logger.warning(
                    "EDGAR request failed (attempt %d/%d): %s. Backing off for %.2fs",
                    attempt,
                    self.max_retries,
                    exc,
                    sleep_sec,
                )
                time.sleep(sleep_sec)

        raise EdgarClientError(f"Failed to fetch {url} after {self.max_retries} retries: {last_exception}")

    def load_ticker_map(self, force_refresh: bool = False) -> dict[str, str]:
        """Loads and caches SEC ticker to 10-digit CIK dictionary."""
        if self._ticker_map_loaded and not force_refresh:
            return self._ticker_map

        url = "https://www.sec.gov/files/company_tickers.json"
        res = self._request_with_retry(url, host="www.sec.gov")
        if res.status_code != 200:
            raise EdgarClientError(f"Unable to load company_tickers.json, status {res.status_code}")

        data: dict[str, Any] = res.json()
        mapping: dict[str, str] = {}
        for entry in data.values():
            if isinstance(entry, dict):
                ticker = str(entry.get("ticker", "")).strip().upper()
                cik_int = entry.get("cik_str")
                if ticker and cik_int is not None:
                    cik10 = str(cik_int).zfill(10)
                    mapping[ticker] = cik10
                    # Also normalize ticker with dot/dash variations: BRK.A <-> BRK-A
                    if "-" in ticker:
                        mapping[ticker.replace("-", ".")] = cik10
                    elif "." in ticker:
                        mapping[ticker.replace(".", "-")] = cik10

        self._ticker_map = mapping
        self._ticker_map_loaded = True
        return self._ticker_map

    def resolve_cik(self, ticker_or_cik: str) -> str:
        """
        Resolves a ticker symbol or raw CIK to a 10-digit zero-padded CIK string.
        """
        raw = ticker_or_cik.strip()
        if not raw:
            raise EdgarCompanyNotFoundError("Empty ticker or CIK provided")

        if raw.isdigit():
            return raw.zfill(10)

        # Check ticker map
        clean_ticker = raw.upper()
        if not self._ticker_map_loaded:
            self.load_ticker_map()

        if clean_ticker in self._ticker_map:
            return self._ticker_map[clean_ticker]

        # Alternative formats: BRK-B vs BRK.B
        alt1 = clean_ticker.replace("-", ".")
        if alt1 in self._ticker_map:
            return self._ticker_map[alt1]
        alt2 = clean_ticker.replace(".", "-")
        if alt2 in self._ticker_map:
            return self._ticker_map[alt2]

        raise EdgarCompanyNotFoundError(f"Ticker or CIK '{ticker_or_cik}' not found on EDGAR.")

    def get_submissions(self, cik: str) -> dict[str, Any]:
        """
        Fetches the Submissions API payload for a given CIK.
        """
        cik10 = self.resolve_cik(cik)
        url = f"https://data.sec.gov/submissions/CIK{cik10}.json"
        res = self._request_with_retry(url, host="data.sec.gov")
        if res.status_code == 404:
            raise EdgarCompanyNotFoundError(f"No EDGAR submissions found for CIK {cik10}")
        if res.status_code != 200:
            raise EdgarClientError(f"EDGAR Submissions API returned status {res.status_code} for CIK {cik10}")

        data: dict[str, Any] = res.json()
        return data

    def get_filings(
        self,
        ticker_or_cik: str,
        forms: list[str] | None = None,
        limit: int = 50,
    ) -> list[FilingRef]:
        """
        Retrieves filings for a given company, checking for foreign filer status and returning typed FilingRef.

        Args:
            ticker_or_cik: Company ticker (e.g. 'GOOGL', 'AAPL') or CIK.
            forms: Optional list of form types to filter (e.g. ['10-K', '10-Q', '8-K', '10-K/A', '10-Q/A']).
            limit: Maximum filings to return.

        Returns:
            List of FilingRef objects.

        Raises:
            ForeignFilerUnsupportedError: If the entity is a foreign filer (Invariant I3).
        """
        cik10 = self.resolve_cik(ticker_or_cik)
        submissions = self.get_submissions(cik10)

        # Check foreign filer in entity metadata or recent filings
        filings_data = submissions.get("filings", {})
        recent = filings_data.get("recent", {})

        accession_list: list[str] = recent.get("accessionNumber", [])
        forms_list: list[str] = recent.get("form", [])
        filing_dates: list[str] = recent.get("filingDate", [])
        report_dates: list[str] = recent.get("reportDate", [])
        primary_docs: list[str] = recent.get("primaryDocument", [])

        # Check if the company primarily files 20-F or 6-K or 40-F
        foreign_count = sum(1 for f in forms_list if f in FOREIGN_FORMS)
        domestic_count = sum(1 for f in forms_list if f in {"10-K", "10-Q", "8-K", "10-K/A", "10-Q/A"})
        if foreign_count > 0 and domestic_count == 0:
            raise ForeignFilerUnsupportedError(
                f"Company {ticker_or_cik} (CIK {cik10}) is a foreign filer (filing forms: {set(forms_list) & FOREIGN_FORMS}). "
                "Foreign filers (Forms 20-F, 40-F, 6-K) are unsupported per Invariant I3: US GAAP standard required."
            )

        filing_refs: list[FilingRef] = []
        cik_int = int(cik10)

        # Build exhibit lookups if available
        # Note: recent may contain items
        target_forms = set(forms) if forms else None

        for idx, acc in enumerate(accession_list):
            form_type = forms_list[idx] if idx < len(forms_list) else ""
            if form_type in FOREIGN_FORMS:
                if target_forms and form_type in target_forms:
                    raise ForeignFilerUnsupportedError(
                        f"Form {form_type} for CIK {cik10} is a foreign filing unsupported per Invariant I3."
                    )
                continue

            if target_forms and form_type not in target_forms:
                continue

            filed_at = filing_dates[idx] if idx < len(filing_dates) else ""
            period = report_dates[idx] if idx < len(report_dates) else None
            primary_doc = primary_docs[idx] if idx < len(primary_docs) else ""
            
            acc_nodash = acc.replace("-", "")
            primary_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{primary_doc}"

            # Filing year parsing
            filing_year: int | None = None
            if period and len(period) >= 4 and period[:4].isdigit():
                filing_year = int(period[:4])
            elif filed_at and len(filed_at) >= 4 and filed_at[:4].isdigit():
                filing_year = int(filed_at[:4])

            # Exhibit list placeholder - can be populated on exhibit discovery
            filing_ref = FilingRef(
                cik=cik10,
                accession=acc,
                form=form_type,
                period=period,
                filed_at=filed_at,
                primary_url=primary_url,
                primary_document=primary_doc,
                exhibits=[],
                is_amendment=form_type.endswith("/A"),
                filing_year=filing_year,
            )
            filing_refs.append(filing_ref)
            if len(filing_refs) >= limit:
                break

        return filing_refs

    def get_filing_directory_index(self, filing: FilingRef) -> list[FilingExhibit]:
        """
        Discovers exhibits and files in the filing accession directory.
        Fetches {accession}-index.htm or directory index.
        """
        cik_int = int(filing.cik)
        acc_nodash = filing.accession.replace("-", "")
        # The SEC directory listing or index page
        index_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{filing.accession}-index.htm"

        exhibits: list[FilingExhibit] = []
        try:
            res = self._request_with_retry(index_url, host="www.sec.gov")
            if res.status_code == 200:
                html = res.text
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                for tr in soup.find_all("tr"):
                    cells = tr.find_all(["td", "th"])
                    if not cells:
                        continue
                    cell_texts = [c.get_text(strip=True) for c in cells]
                    a_tag = tr.find("a", href=True)
                    if not a_tag:
                        continue
                    href = str(a_tag["href"])
                    filename = href.split("/")[-1]

                    # Detect exhibit type
                    ex_num = None
                    for txt in cell_texts:
                        m = re.search(r"\b(EX(?:HIBIT)?-?[\d\.]+)\b", txt, re.IGNORECASE)
                        if m:
                            ex_num = m.group(1).upper().replace("EXHIBIT-", "EX-").replace("EXHIBIT", "EX-")
                            break
                    
                    if not ex_num and ("ex99" in filename.lower() or "ex-99" in filename.lower()):
                        ex_num = "EX-99.1"

                    if ex_num:
                        # Find description text among cells
                        desc = ""
                        for txt in cell_texts:
                            if txt != ex_num and txt != filename and txt != a_tag.get_text(strip=True) and len(txt) > len(desc):
                                desc = txt
                        if not desc:
                            desc = a_tag.get_text(strip=True)

                        full_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{filename}"
                        exhibits.append(
                            FilingExhibit(
                                exhibit_number=ex_num,
                                filename=filename,
                                description=desc or filename,
                                url=full_url,
                            )
                        )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not fetch filing directory index for %s: %s", filing.accession, exc)

        filing.exhibits = exhibits
        return exhibits

    def get_document(
        self,
        accession: str,
        document_name: str,
        cik: str | None = None,
    ) -> FilingDocument:
        """
        Retrieves a document from local accession cache, or fetches from SEC EDGAR.
        Accession documents are immutable; once cached, local disk copy is returned.
        """
        # 1. Check local disk cache
        cache_file = self.cache_dir / accession / document_name
        if cache_file.exists():
            content = cache_file.read_bytes()
            content_type = "application/pdf" if document_name.lower().endswith(".pdf") else "text/html"
            url = f"local://{accession}/{document_name}"
            return FilingDocument(
                accession=accession,
                document_name=document_name,
                content=content,
                content_type=content_type,
                url=url,
            )

        if not cik:
            raise EdgarClientError(f"CIK required to fetch un-cached document '{document_name}' for accession {accession}")

        cik_int = int(cik)
        acc_nodash = accession.replace("-", "")
        doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{document_name}"

        res = self._request_with_retry(doc_url, host="www.sec.gov")
        if res.status_code == 404:
            raise EdgarFilingNotFoundError(f"Document {document_name} not found in accession {accession}")
        if res.status_code != 200:
            raise EdgarClientError(f"EDGAR returned status {res.status_code} fetching {doc_url}")

        content = res.content
        # 2. Write to immutable cache
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(content)

        content_type = res.headers.get("content-type", "text/html")
        return FilingDocument(
            accession=accession,
            document_name=document_name,
            content=content,
            content_type=content_type,
            url=doc_url,
        )
