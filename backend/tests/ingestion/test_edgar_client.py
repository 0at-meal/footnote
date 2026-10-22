"""
Unit and contract tests for SEC EDGAR Client.
"""

import time
from pathlib import Path

import httpx
import pytest
from app.ingestion.edgar.circuit_breaker import CircuitBreaker, CircuitState
from app.ingestion.edgar.client import EdgarClient
from app.ingestion.edgar.models import (
    EdgarCircuitBreakerOpenError,
    EdgarClientError,
    EdgarCompanyNotFoundError,
    EdgarRateLimitError,
    ForeignFilerUnsupportedError,
)
from app.ingestion.edgar.rate_limiter import TokenBucketRateLimiter

# All HTTP below is mocked. Ticker -> CIK mappings are real; accession numbers,
# dates and document names are illustrative and do not refer to real filings.

# Sample mock data for company_tickers.json
MOCK_TICKERS = {
    "0": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
    "1": {"cik_str": 1652044, "ticker": "GOOG", "title": "Alphabet Inc."},
    "2": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "3": {"cik_str": 1067983, "ticker": "BRK-A", "title": "BERKSHIRE HATHAWAY INC"},
    "4": {"cik_str": 1090872, "ticker": "BABA", "title": "Alibaba Group Holding Ltd"},
}

# Sample mock data for Alphabet submissions CIK0001652044.json
MOCK_GOOGL_SUBMISSIONS = {
    "cik": "0001652044",
    "entityType": "operating",
    "sic": "7370",
    "name": "Alphabet Inc.",
    "tickers": ["GOOGL", "GOOG"],
    "filings": {
        "recent": {
            "accessionNumber": [
                "0001652044-24-000088",
                "0001652044-24-000065",
                "0001652044-24-000033",
                "0001652044-24-000010",
                "0001652044-24-000005",
            ],
            "filingDate": [
                "2024-10-30",
                "2024-07-24",
                "2024-04-26",
                "2024-02-01",
                "2024-01-30",
            ],
            "reportDate": [
                "2024-09-30",
                "2024-06-30",
                "2024-03-31",
                "2023-12-31",
                "2024-01-30",
            ],
            "form": [
                "10-Q",
                "10-Q",
                "10-Q",
                "10-K",
                "8-K",
            ],
            "primaryDocument": [
                "goog-20240930.htm",
                "goog-20240630.htm",
                "goog-20240331.htm",
                "goog-20231231.htm",
                "goog-20240130.htm",
            ],
            "primaryDocDescription": [
                "10-Q",
                "10-Q",
                "10-Q",
                "10-K",
                "8-K",
            ],
        }
    },
}

# Sample mock data for Foreign Filer submissions (e.g. Alibaba 20-F / 6-K)
MOCK_FOREIGN_SUBMISSIONS = {
    "cik": "0001090872",
    "entityType": "foreign",
    "name": "Alibaba Group Holding Ltd",
    "tickers": ["BABA"],
    "filings": {
        "recent": {
            "accessionNumber": ["0001090872-24-000010", "0001090872-24-000005"],
            "filingDate": ["2024-06-25", "2024-05-15"],
            "reportDate": ["2024-03-31", "2024-03-31"],
            "form": ["20-F", "6-K"],
            "primaryDocument": ["baba-20240331.htm", "baba-6k.htm"],
            "primaryDocDescription": ["20-F", "6-K"],
        }
    },
}


class MockTransport(httpx.BaseTransport):
    def __init__(
        self, doc_content: bytes = b"<html>Sample EDGAR Document</html>"
    ) -> None:
        self.doc_content = doc_content
        self.request_count = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.request_count += 1
        url_str = str(request.url)

        if "company_tickers.json" in url_str:
            return httpx.Response(200, json=MOCK_TICKERS)
        elif "CIK0001652044.json" in url_str:
            return httpx.Response(200, json=MOCK_GOOGL_SUBMISSIONS)
        elif "CIK0001090872.json" in url_str:
            return httpx.Response(200, json=MOCK_FOREIGN_SUBMISSIONS)
        elif "0001652044-24-000005-index.htm" in url_str:
            index_html = """
            <html>
                <table class="tableFile">
                    <tr><td>EX-99.1</td><td><a href="goog-ex991.htm">goog-ex991.htm</a></td><td>Press Release Q4 2023</td></tr>
                </table>
            </html>
            """
            return httpx.Response(200, text=index_html)
        elif url_str.endswith((".htm", ".pdf")):
            return httpx.Response(
                200, content=self.doc_content, headers={"Content-Type": "text/html"}
            )

        return httpx.Response(404, text="Not Found")


# 1. Rate Limiter Tests
def test_rate_limiter_burst_and_refill() -> None:
    limiter = TokenBucketRateLimiter(rate=50.0, capacity=5.0)
    # Burst 5 tokens
    for _ in range(5):
        assert limiter.try_acquire(1.0) is True

    # Next immediate acquire should fail
    assert limiter.try_acquire(1.0) is False

    # After sleeping, tokens refill
    time.sleep(0.05)  # 0.05s * 50 tokens/s = ~2.5 tokens
    assert limiter.try_acquire(1.0) is True


def test_rate_limiter_timeout_raises_error() -> None:
    limiter = TokenBucketRateLimiter(rate=1.0, capacity=1.0)
    assert limiter.acquire(1.0, timeout=0.1) is True

    with pytest.raises(EdgarRateLimitError):
        # Needs 1 token, rate is 1.0 token/s, so wait time is 1.0s > timeout 0.1s
        limiter.acquire(1.0, timeout=0.1)


# 2. Circuit Breaker Tests
def test_circuit_breaker_transitions() -> None:
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.1)
    assert cb.get_state() == CircuitState.CLOSED

    # Record 2 failures -> remains CLOSED
    cb.record_failure()
    cb.record_failure()
    assert cb.get_state() == CircuitState.CLOSED

    # 3rd failure -> trips OPEN
    cb.record_failure()
    assert cb.get_state() == CircuitState.OPEN

    with pytest.raises(EdgarCircuitBreakerOpenError):
        cb.before_request()

    # Sleep past recovery_timeout -> moves to HALF_OPEN
    time.sleep(0.12)
    assert cb.get_state() == CircuitState.HALF_OPEN

    # Success in HALF_OPEN resets to CLOSED
    cb.record_success()
    assert cb.get_state() == CircuitState.CLOSED


# 3. EdgarClient Tests
TEST_USER_AGENT = "Footnote Tests tests@example.com"


def test_missing_user_agent_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(EdgarClientError, match="SEC_USER_AGENT"):
        EdgarClient()


def test_get_filings_googl(tmp_path: Path) -> None:
    transport = MockTransport()
    http_client = httpx.Client(transport=transport)
    client = EdgarClient(
        user_agent=TEST_USER_AGENT,
        cache_dir=tmp_path / "edgar_cache",
        http_client=http_client,
    )

    # Acceptance requirement: get_filings("GOOGL") returns latest 10-Q and 10-K with correct periods
    filings = client.get_filings("GOOGL")
    assert len(filings) > 0

    # Check 10-Q
    q_filings = [f for f in filings if f.form == "10-Q"]
    assert len(q_filings) >= 1
    latest_10q = q_filings[0]
    assert latest_10q.accession == "0001652044-24-000088"
    assert latest_10q.period == "2024-09-30"
    assert latest_10q.cik == "0001652044"
    assert latest_10q.primary_document == "goog-20240930.htm"
    assert (
        "https://www.sec.gov/Archives/edgar/data/1652044/000165204424000088/goog-20240930.htm"
        == latest_10q.primary_url
    )

    # Check 10-K
    k_filings = [f for f in filings if f.form == "10-K"]
    assert len(k_filings) >= 1
    latest_10k = k_filings[0]
    assert latest_10k.accession == "0001652044-24-000010"
    assert latest_10k.period == "2023-12-31"
    assert latest_10k.filing_year == 2023


def test_share_classes_and_ticker_variations(tmp_path: Path) -> None:
    transport = MockTransport()
    http_client = httpx.Client(transport=transport)
    client = EdgarClient(
        user_agent=TEST_USER_AGENT,
        cache_dir=tmp_path / "edgar_cache",
        http_client=http_client,
    )

    # Both GOOG and GOOGL resolve to CIK 0001652044
    assert client.resolve_cik("GOOGL") == "0001652044"
    assert client.resolve_cik("GOOG") == "0001652044"

    # Berkshire share class variation BRK.A vs BRK-A
    assert client.resolve_cik("BRK-A") == "0001067983"
    assert client.resolve_cik("BRK.A") == "0001067983"

    # Numeric CIK padding
    assert client.resolve_cik("320193") == "0000320193"


def test_foreign_filer_explicit_rejection(tmp_path: Path) -> None:
    transport = MockTransport()
    http_client = httpx.Client(transport=transport)
    client = EdgarClient(
        user_agent=TEST_USER_AGENT,
        cache_dir=tmp_path / "edgar_cache",
        http_client=http_client,
    )

    # Alibaba (BABA) files Form 20-F / 6-K. Must explicitly raise ForeignFilerUnsupportedError
    with pytest.raises(ForeignFilerUnsupportedError) as exc_info:
        client.get_filings("BABA")

    assert "Foreign filers" in str(exc_info.value)
    assert "unsupported" in str(exc_info.value)


def test_accession_caching_immutable(tmp_path: Path) -> None:
    transport = MockTransport(
        doc_content=b"<html>Financial Statements 10-Q Content</html>"
    )
    http_client = httpx.Client(transport=transport)
    client = EdgarClient(
        user_agent=TEST_USER_AGENT,
        cache_dir=tmp_path / "edgar_cache",
        http_client=http_client,
    )

    accession = "0001652044-24-000088"
    doc_name = "goog-20240930.htm"
    cik = "0001652044"

    # First fetch: requests from transport
    initial_count = transport.request_count
    doc1 = client.get_document(accession=accession, document_name=doc_name, cik=cik)
    assert doc1.content == b"<html>Financial Statements 10-Q Content</html>"
    assert transport.request_count > initial_count

    # Second fetch: served strictly from disk cache, transport not called again
    count_after_first = transport.request_count
    doc2 = client.get_document(accession=accession, document_name=doc_name, cik=cik)
    assert doc2.content == b"<html>Financial Statements 10-Q Content</html>"
    assert transport.request_count == count_after_first


def test_exhibit_discovery_ex99_1(tmp_path: Path) -> None:
    transport = MockTransport()
    http_client = httpx.Client(transport=transport)
    client = EdgarClient(
        user_agent=TEST_USER_AGENT,
        cache_dir=tmp_path / "edgar_cache",
        http_client=http_client,
    )

    filings = client.get_filings("GOOGL", forms=["8-K"])
    assert len(filings) >= 1
    filing_8k = filings[0]

    exhibits = client.get_filing_directory_index(filing_8k)
    assert len(exhibits) >= 1
    ex99 = next((e for e in exhibits if e.exhibit_number == "EX-99.1"), None)
    assert ex99 is not None
    assert ex99.filename == "goog-ex991.htm"
    assert "Press Release" in (ex99.description or "")


def test_cached_document_keeps_sec_url(tmp_path: Path) -> None:
    client = EdgarClient(
        user_agent=TEST_USER_AGENT,
        cache_dir=tmp_path / "edgar_cache",
        http_client=httpx.Client(transport=MockTransport()),
    )
    args = {
        "accession": "0001652044-24-000088",
        "document_name": "goog-20240930.htm",
        "cik": "0001652044",
    }
    first = client.get_document(**args)
    cached = client.get_document(**args)
    expected = "https://www.sec.gov/Archives/edgar/data/1652044/000165204424000088/goog-20240930.htm"
    assert first.url == expected
    assert cached.url == expected


class _MissingIndexTransport(MockTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("-index.htm"):
            return httpx.Response(404, text="Not Found")
        return super().handle_request(request)


def test_directory_index_failure_raises(tmp_path: Path) -> None:
    client = EdgarClient(
        user_agent=TEST_USER_AGENT,
        cache_dir=tmp_path / "edgar_cache",
        http_client=httpx.Client(transport=_MissingIndexTransport()),
    )
    filing = client.get_filings("GOOGL", forms=["8-K"])[0]
    # A failed index fetch must raise, not masquerade as "no exhibits".
    with pytest.raises(EdgarClientError, match="status 404"):
        client.get_filing_directory_index(filing)


class _IndexTransport(MockTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("-index.htm"):
            return httpx.Response(
                200,
                text='<table><tr><td><a href="acme-ex99.htm">acme-ex99.htm</a></td></tr></table>',
            )
        return super().handle_request(request)


def test_exhibit_number_not_guessed_from_filename(tmp_path: Path) -> None:
    client = EdgarClient(
        user_agent=TEST_USER_AGENT,
        cache_dir=tmp_path / "edgar_cache",
        http_client=httpx.Client(transport=_IndexTransport()),
    )
    filing = client.get_filings("GOOGL", forms=["8-K"])[0]
    exhibits = client.get_filing_directory_index(filing)
    assert [e.exhibit_number for e in exhibits] == ["EX-99"]


class _RealLayoutIndexTransport(MockTransport):
    """EDGAR index column order: Seq | Description | Document | Type | Size."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("-index.htm"):
            row = (
                "<tr><td>2</td><td>PRESS RELEASE</td>"
                '<td><a href="/Archives/x/acme-ex991.htm">acme-ex991.htm</a></td>'
                "<td>EX-99.1</td><td>120000</td></tr>"
            )
            return httpx.Response(200, text=f"<table>{row}</table>")
        return super().handle_request(request)


def test_exhibit_type_read_from_type_column_not_filename(tmp_path: Path) -> None:
    client = EdgarClient(
        user_agent=TEST_USER_AGENT,
        cache_dir=tmp_path / "edgar_cache",
        http_client=httpx.Client(transport=_RealLayoutIndexTransport()),
    )
    filing = client.get_filings("GOOGL", forms=["8-K"])[0]
    exhibits = client.get_filing_directory_index(filing)
    assert len(exhibits) == 1
    assert exhibits[0].exhibit_number == "EX-99.1"
    assert exhibits[0].filename == "acme-ex991.htm"
    assert exhibits[0].description == "PRESS RELEASE"


class _CompanyFactsTransport(MockTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "companyfacts/CIK0001652044.json" in url:
            return httpx.Response(200, json={"cik": 1652044, "facts": {"us-gaap": {}}})
        if "companyfacts/" in url:
            return httpx.Response(404, text="Not Found")
        return super().handle_request(request)


def test_get_company_facts(tmp_path: Path) -> None:
    client = EdgarClient(
        user_agent=TEST_USER_AGENT,
        cache_dir=tmp_path / "edgar_cache",
        http_client=httpx.Client(transport=_CompanyFactsTransport()),
    )
    facts = client.get_company_facts("GOOGL")
    assert facts["facts"] == {"us-gaap": {}}
    with pytest.raises(EdgarCompanyNotFoundError):
        client.get_company_facts("320193")


def test_get_filings_filters_8k_items(tmp_path: Path) -> None:
    """P1-05: only 8-Ks reporting a wanted item are kept; items are recorded."""
    transport = MockTransport()
    client = EdgarClient(
        user_agent=TEST_USER_AGENT,
        cache_dir=tmp_path / "edgar_cache",
        http_client=httpx.Client(transport=transport),
    )
    submissions = {
        "filings": {
            "recent": {
                "accessionNumber": ["0000000001-26-000003", "0000000001-26-000002"],
                "filingDate": ["2026-07-30", "2026-06-01"],
                "reportDate": ["2026-07-30", "2026-06-01"],
                "form": ["8-K", "8-K"],
                "primaryDocument": ["a.htm", "b.htm"],
                "items": ["2.02,9.01", "5.07"],
            }
        }
    }
    got = client.get_filings(
        "1", forms=["8-K"], items=["2.02"], submissions=submissions
    )
    assert [f.accession for f in got] == ["0000000001-26-000003"]
    assert got[0].items == ["2.02", "9.01"]
    assert transport.request_count == 0  # the given payload is used as-is


def test_directory_index_is_cached(tmp_path: Path) -> None:
    transport = MockTransport()
    client = EdgarClient(
        user_agent=TEST_USER_AGENT,
        cache_dir=tmp_path / "edgar_cache",
        http_client=httpx.Client(transport=transport),
    )
    filing = client.get_filings("GOOGL", forms=["8-K"])[0]
    first = client.get_filing_directory_index(filing)
    count = transport.request_count
    second = client.get_filing_directory_index(filing)
    assert transport.request_count == count
    assert first == second
