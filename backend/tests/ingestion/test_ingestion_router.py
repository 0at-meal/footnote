"""
Decision-table unit tests for Unified Ingestion Router (FN-024).
"""


from app.extraction.locator import PdfLocator
from app.extraction.models import ExtractedRecord
from app.ingestion.edgar.models import FilingDocument, FilingExhibit, FilingRef
from app.ingestion.router_engine import (
    CLASSIFIER_VERSION,
    EXTRACTOR_VERSION,
    TAXONOMY_VERSION,
    IngestionRequest,
    IngestionRouter,
)

HTML_WITH_RECON = """
<html><body>
<h1>Form 10-Q</h1>
<p>Reconciliation of Net Income to Adjusted EBITDA</p>
<table>
    <tr><th>Metric</th><th>Q3 2024</th></tr>
    <tr><td>Net Income</td><td>25,000</td></tr>
    <tr><td>Depreciation</td><td>2,000</td></tr>
    <tr><td>Adjusted EBITDA</td><td>27,000</td></tr>
</table>
</body></html>
"""

HTML_WITHOUT_RECON = """
<html><body>
<h1>Form 10-Q</h1>
<p>General Corporate Information</p>
<table>
    <tr><th>Employee</th><th>Department</th></tr>
    <tr><td>Alice</td><td>Finance</td></tr>
</table>
</body></html>
"""


class MockEdgarClient:
    def __init__(
        self,
        primary_html: str = HTML_WITH_RECON,
        has_ex99: bool = False,
        ex99_html: str = "",
        has_pdf: bool = False,
    ) -> None:
        self.primary_html = primary_html
        self.has_ex99 = has_ex99
        self.ex99_html = ex99_html
        self.has_pdf = has_pdf

    def get_filings(self, ticker: str, forms: list[str] | None = None) -> list[FilingRef]:
        exhibits: list[FilingExhibit] = []
        if self.has_ex99:
            exhibits.append(
                FilingExhibit(
                    exhibit_number="EX-99.1",
                    filename="ex991.htm",
                    url="https://sec.gov/ex991.htm",
                )
            )
        if self.has_pdf:
            exhibits.append(
                FilingExhibit(
                    exhibit_number="EX-PDF",
                    filename="filing.pdf",
                    url="https://sec.gov/filing.pdf",
                )
            )

        filing_10q = FilingRef(
            cik="0001652044",
            accession="0001652044-24-000088",
            form="10-Q",
            period="2024-09-30",
            filed_at="2024-10-30",
            primary_url="https://sec.gov/primary.htm",
            primary_document="primary.htm",
            exhibits=exhibits,
        )

        filing_8k = FilingRef(
            cik="0001652044",
            accession="0001652044-24-000005",
            form="8-K",
            period="2024-09-30",
            filed_at="2024-10-29",
            primary_url="https://sec.gov/8k.htm",
            primary_document="8k.htm",
            exhibits=exhibits,
        )
        return [filing_10q, filing_8k]

    def get_document(self, accession: str, document_name: str, cik: str | None = None) -> FilingDocument:
        if "ex99" in document_name:
            content = self.ex99_html.encode("utf-8")
        elif document_name.endswith(".pdf"):
            content = b"%PDF-1.4 dummy pdf bytes"
        else:
            content = self.primary_html.encode("utf-8")

        return FilingDocument(
            accession=accession,
            document_name=document_name,
            content=content,
            url=f"https://sec.gov/{accession}/{document_name}",
        )

    def get_filing_directory_index(self, filing: FilingRef) -> list[FilingExhibit]:
        return filing.exhibits


def mock_pdf_extractor(pdf_bytes: bytes, filename: str, target_metric: str = "") -> list[ExtractedRecord]:
    loc = PdfLocator(page=1, bbox={"x0": 10.0, "y0": 20.0, "x1": 30.0, "y1": 40.0}, source_file=filename)
    return [
        ExtractedRecord(
            value="27,000",
            label="PDF Reconciliation > Adjusted EBITDA",
            page=1,
            bbox={"x0": 10.0, "y0": 20.0, "x1": 30.0, "y1": 40.0},
            source_file=filename,
            locator=loc,
        )
    ]


# ── Decision-Table Test Cases ───────────────────────────────────────────────

def test_decision_1_primary_html_success() -> None:
    client = MockEdgarClient(primary_html=HTML_WITH_RECON)
    router = IngestionRouter(edgar_client=client)

    req = IngestionRequest(ticker="GOOGL", period="2024-09-30")
    res = router.route(req)

    assert res.status == "success"
    assert res.parser_used == "ixbrl_html"
    assert len(res.records) > 0
    assert res.extractor_version == EXTRACTOR_VERSION
    assert res.classifier_version == CLASSIFIER_VERSION
    assert res.taxonomy_version == TAXONOMY_VERSION

    # Route attempt verification
    assert any(a.route == "edgar_html" and a.status == "success" for a in res.route_history)


def test_decision_2_fallback_to_ex99_1_success() -> None:
    # Primary HTML has no reconciliation, but 8-K EX-99.1 has it
    client = MockEdgarClient(
        primary_html=HTML_WITHOUT_RECON,
        has_ex99=True,
        ex99_html=HTML_WITH_RECON,
    )
    router = IngestionRouter(edgar_client=client)

    req = IngestionRequest(ticker="GOOGL", period="2024-09-30")
    res = router.route(req)

    assert res.status == "success"
    assert res.parser_used == "ixbrl_html"
    assert len(res.records) > 0

    # Invariant I3: explicit failure recorded on edgar_html, success on ex_99_1
    html_attempt = next(a for a in res.route_history if a.route == "edgar_html")
    assert html_attempt.status == "failed"
    assert "No non-GAAP reconciliation" in (html_attempt.reason or "")

    ex99_attempt = next(a for a in res.route_history if a.route == "ex_99_1")
    assert ex99_attempt.status == "success"


def test_decision_3_fallback_to_pdf_success() -> None:
    # Both HTML and EX-99 fail, but PDF exists
    client = MockEdgarClient(
        primary_html=HTML_WITHOUT_RECON,
        has_ex99=False,
        has_pdf=True,
    )
    router = IngestionRouter(
        edgar_client=client,
        pdf_extractor_fn=mock_pdf_extractor,
    )

    req = IngestionRequest(ticker="GOOGL", period="2024-09-30")
    res = router.route(req)

    assert res.status == "success"
    assert res.parser_used == "docling"
    assert len(res.records) == 1

    # Route history check
    attempts = {a.route: a.status for a in res.route_history}
    assert attempts["edgar_html"] == "failed"
    assert attempts["ex_99_1"] == "skipped"
    assert attempts["pdf_fallback"] == "success"


def test_decision_4_all_routes_fail_explicit_reasons_invariant_i3() -> None:
    # All routes fail
    client = MockEdgarClient(
        primary_html=HTML_WITHOUT_RECON,
        has_ex99=False,
        has_pdf=False,
    )
    router = IngestionRouter(
        edgar_client=client,
        pdf_extractor_fn=None,
    )

    req = IngestionRequest(ticker="GOOGL", period="2024-09-30")
    res = router.route(req)

    assert res.status == "failed"
    assert res.parser_used == "none"
    assert "All ingestion routes exhausted" in (res.failure_reason or "")
    for attempt in res.route_history:
        assert attempt.reason is not None


def test_decision_5_both_html_and_release_diffing_mixed() -> None:
    # Both primary HTML and 8-K have reconciliation
    client = MockEdgarClient(
        primary_html=HTML_WITH_RECON,
        has_ex99=True,
        ex99_html=HTML_WITH_RECON,
    )
    router = IngestionRouter(edgar_client=client)

    req = IngestionRequest(ticker="GOOGL", period="2024-09-30")
    res = router.route(req)

    assert res.status == "success"
    assert res.parser_used == "mixed"
    assert res.diff_report is not None


def test_idempotency_returns_cached_result() -> None:
    client = MockEdgarClient(primary_html=HTML_WITH_RECON)
    router = IngestionRouter(edgar_client=client)

    req = IngestionRequest(ticker="GOOGL", period="2024-09-30")
    res1 = router.route(req)
    assert res1.cached is False

    # Second request with identical parameters returns cached result
    res2 = router.route(req)
    assert res2.cached is True
    assert res2.accession == res1.accession
    assert len(res2.records) == len(res1.records)


def test_per_user_concurrency_limit() -> None:
    client = MockEdgarClient(primary_html=HTML_WITH_RECON)
    router = IngestionRouter(edgar_client=client, max_concurrency_per_user=1)

    # Artificially hold a lock/concurrency slot for user "alice"
    router._active_users["alice"] = 1

    req = IngestionRequest(ticker="GOOGL", period="2024-09-30", user_id="alice")
    res = router.route(req)

    assert res.status == "rejected"
    assert "concurrency limit" in (res.failure_reason or "").lower()
