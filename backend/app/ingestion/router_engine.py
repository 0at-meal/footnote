"""
Unified Ingestion Router Engine (FN-024).

Implements:
1. One entry point accepting (ticker+period, accession, or uploaded file).
2. Routing cascade: EDGAR HTML/iXBRL -> 8-K EX-99.1 -> PDF fallback.
3. Explicit failure reasons recorded on every route attempt (Invariant I3).
4. Extended parser_used tracking ('ixbrl_html', 'docling', 'pymupdf', 'mixed').
5. Version stamping: extractor_version, classifier_version, taxonomy_version.
6. Idempotent caching by (accession, pack, versions).
7. Per-user concurrency enforcement.
"""

import logging
import threading
from collections import defaultdict
from collections.abc import Callable

from pydantic import BaseModel, Field

from app.extraction.html.extractor import HtmlExtractor
from app.extraction.models import ExtractedRecord
from app.ingestion.edgar.client import EdgarClient
from app.ingestion.edgar.models import FilingRef
from app.ingestion.exhibit_99.differ import merge_dedupe_bridges
from app.ingestion.exhibit_99.extractor import Exhibit99Extractor
from app.ingestion.exhibit_99.models import BridgeDiffReport

logger = logging.getLogger(__name__)

EXTRACTOR_VERSION = "2.0.0"
CLASSIFIER_VERSION = "1.5.0"
TAXONOMY_VERSION = "2026.1"


class RouteAttempt(BaseModel):
    """Log of a routing stage execution attempt with explicit status and reason."""

    route: str
    status: str  # 'success', 'failed', 'skipped'
    reason: str | None = None


class IngestionRequest(BaseModel):
    """Unified input request for ingestion."""

    ticker: str | None = None
    period: str | None = None
    accession: str | None = None
    form: str | None = None
    file_bytes: bytes | None = None
    filename: str | None = None
    workflow_pack: str = "non_gaap_bridge"
    target_metric: str = "Adjusted EBITDA"
    user_id: str = "default_user"


class IngestionResult(BaseModel):
    """Authoritative output of the ingestion router."""

    status: str  # 'success', 'failed', 'rejected'
    accession: str
    parser_used: str  # 'ixbrl_html', 'docling', 'pymupdf', 'mixed'
    records: list[ExtractedRecord] = Field(default_factory=list)
    route_history: list[RouteAttempt] = Field(default_factory=list)
    failure_reason: str | None = None
    cached: bool = False
    extractor_version: str = EXTRACTOR_VERSION
    classifier_version: str = CLASSIFIER_VERSION
    taxonomy_version: str = TAXONOMY_VERSION
    diff_report: BridgeDiffReport | None = None


class IngestionRouter:
    """
    Unified router directing documents through EDGAR HTML/iXBRL, 8-K EX-99.1, or PDF fallback.
    """

    def __init__(
        self,
        edgar_client: EdgarClient | None = None,
        html_extractor: HtmlExtractor | None = None,
        exhibit99_extractor: Exhibit99Extractor | None = None,
        pdf_extractor_fn: Callable[..., list[ExtractedRecord]] | None = None,
        max_concurrency_per_user: int = 5,
    ) -> None:
        self.edgar_client = edgar_client
        self.html_extractor = html_extractor or HtmlExtractor()
        self.exhibit99_extractor = exhibit99_extractor or Exhibit99Extractor(self.html_extractor)
        self.pdf_extractor_fn = pdf_extractor_fn
        self.max_concurrency_per_user = max_concurrency_per_user

        self._active_users: dict[str, int] = defaultdict(int)
        self._cache: dict[str, IngestionResult] = {}
        self._lock = threading.Lock()

    def _get_cache_key(self, accession_or_file: str, workflow_pack: str) -> str:
        return f"{accession_or_file}:{workflow_pack}:{EXTRACTOR_VERSION}:{CLASSIFIER_VERSION}:{TAXONOMY_VERSION}"

    def route(self, request: IngestionRequest) -> IngestionResult:
        """
        Executes routing with concurrency checking, caching, and fallback cascade.
        """
        user_id = request.user_id or "default_user"

        # 1. Check per-user concurrency limit
        with self._lock:
            if self._active_users[user_id] >= self.max_concurrency_per_user:
                return IngestionResult(
                    status="rejected",
                    accession=request.accession or "unknown",
                    parser_used="none",
                    failure_reason=(
                        f"Per-user concurrency limit of {self.max_concurrency_per_user} "
                        f"exceeded for user '{user_id}'."
                    ),
                )
            self._active_users[user_id] += 1

        try:
            return self._execute_route(request)
        finally:
            with self._lock:
                self._active_users[user_id] = max(0, self._active_users[user_id] - 1)

    def _execute_route(self, request: IngestionRequest) -> IngestionResult:
        accession_or_file = request.accession or request.filename or (
            f"{request.ticker}_{request.period}" if request.ticker and request.period else "manual_upload"
        )
        cache_key = self._get_cache_key(accession_or_file, request.workflow_pack)

        # 2. Idempotency cache lookup
        with self._lock:
            if cache_key in self._cache:
                cached_res = self._cache[cache_key].model_copy()
                cached_res.cached = True
                return cached_res

        route_history: list[RouteAttempt] = []

        # Find filings via EDGAR if ticker+period or accession provided
        primary_filing: FilingRef | None = None
        release_filing: FilingRef | None = None

        if self.edgar_client and (request.ticker or request.accession):
            try:
                if request.ticker:
                    filings = self.edgar_client.get_filings(
                        request.ticker,
                        forms=["10-K", "10-Q", "8-K", "10-K/A", "10-Q/A"],
                    )
                    # Filter by period if requested
                    if request.period:
                        matching_periodic = [f for f in filings if f.form in ("10-K", "10-Q") and f.period == request.period]
                        if matching_periodic:
                            primary_filing = matching_periodic[0]
                        # Look for 8-K around or matching the period
                        matching_8k = [f for f in filings if f.form.startswith("8-K") and (f.period == request.period or f.filed_at[:7] in (request.period or ""))]
                        if matching_8k:
                            release_filing = matching_8k[0]
                elif request.accession:
                    # Look up by accession
                    primary_filing = FilingRef(
                        cik="0000000000",
                        accession=request.accession,
                        form=request.form or "10-Q",
                        filed_at="2024-01-01",
                        primary_url="",
                        primary_document=request.filename or "primary.htm",
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Error fetching EDGAR filings for routing: %s", exc)

        html_records: list[ExtractedRecord] = []
        release_records: list[ExtractedRecord] = []

        # ── Route 1: EDGAR HTML / iXBRL primary ────────────────────────────────
        if primary_filing and self.edgar_client:
            try:
                doc = self.edgar_client.get_document(
                    accession=primary_filing.accession,
                    document_name=primary_filing.primary_document,
                    cik=primary_filing.cik,
                )
                html_res = self.html_extractor.extract(
                    html_content=doc.content,
                    accession=primary_filing.accession,
                    document_name=primary_filing.primary_document,
                    url=doc.url,
                    target_metric=request.target_metric,
                    workflow_pack=request.workflow_pack,
                )
                if html_res.status == "success" and html_res.records:
                    html_records = html_res.records
                    route_history.append(
                        RouteAttempt(route="edgar_html", status="success")
                    )
                else:
                    route_history.append(
                        RouteAttempt(
                            route="edgar_html",
                            status="failed",
                            reason=html_res.not_found_reason or "No non-GAAP reconciliation found in HTML",
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                route_history.append(
                    RouteAttempt(route="edgar_html", status="failed", reason=str(exc))
                )
        elif request.file_bytes and (request.filename or "").lower().endswith((".htm", ".html")):
            try:
                html_res = self.html_extractor.extract(
                    html_content=request.file_bytes,
                    accession=request.accession or "local_accession",
                    document_name=request.filename or "upload.htm",
                    target_metric=request.target_metric,
                    workflow_pack=request.workflow_pack,
                )
                if html_res.status == "success" and html_res.records:
                    html_records = html_res.records
                    route_history.append(RouteAttempt(route="edgar_html", status="success"))
                else:
                    route_history.append(
                        RouteAttempt(
                            route="edgar_html",
                            status="failed",
                            reason=html_res.not_found_reason or "No non-GAAP reconciliation found in uploaded HTML",
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                route_history.append(
                    RouteAttempt(route="edgar_html", status="failed", reason=str(exc))
                )
        else:
            route_history.append(
                RouteAttempt(
                    route="edgar_html",
                    status="skipped",
                    reason="No HTML / iXBRL primary document available for request",
                )
            )

        # ── Route 2: 8-K EX-99.1 earnings release ─────────────────────────────
        if release_filing and self.edgar_client:
            try:
                self.edgar_client.get_filing_directory_index(release_filing)
                ex99 = next(
                    (e for e in release_filing.exhibits if e.exhibit_number in ("EX-99.1", "EX-99")),
                    None,
                )
                if ex99:
                    doc99 = self.edgar_client.get_document(
                        accession=release_filing.accession,
                        document_name=ex99.filename,
                        cik=release_filing.cik,
                    )
                    release_records = self.exhibit99_extractor.extract_from_content(
                        content=doc99.content,
                        filename=ex99.filename,
                        accession=release_filing.accession,
                        url=doc99.url,
                        target_metric=request.target_metric,
                    )
                    if release_records:
                        route_history.append(RouteAttempt(route="ex_99_1", status="success"))
                    else:
                        route_history.append(
                            RouteAttempt(
                                route="ex_99_1",
                                status="failed",
                                reason=f"No reconciliation tables found in EX-99.1 ({ex99.filename})",
                            )
                        )
                else:
                    route_history.append(
                        RouteAttempt(
                            route="ex_99_1",
                            status="skipped",
                            reason=f"8-K {release_filing.accession} does not contain EX-99.1 exhibit",
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                route_history.append(
                    RouteAttempt(route="ex_99_1", status="failed", reason=str(exc))
                )
        else:
            route_history.append(
                RouteAttempt(
                    route="ex_99_1",
                    status="skipped",
                    reason="No 8-K earnings release identified for period",
                )
            )

        # If both HTML primary and release records exist, merge with diffing
        if html_records and release_records:
            cik_str = primary_filing.cik if primary_filing else ""
            period_str = request.period or (primary_filing.period or "") if primary_filing else ""
            merged = merge_dedupe_bridges(
                release_records=release_records,
                filing_records=html_records,
                cik=cik_str,
                period=period_str,
                release_accession=release_filing.accession if release_filing else "",
                filing_accession=primary_filing.accession if primary_filing else "",
            )
            result = IngestionResult(
                status="success",
                accession=primary_filing.accession if primary_filing else accession_or_file,
                parser_used="mixed",
                records=merged.canonical_records + merged.guidance_records,
                route_history=route_history,
                diff_report=merged.diff_report,
            )
            with self._lock:
                self._cache[cache_key] = result
            return result

        if html_records:
            result = IngestionResult(
                status="success",
                accession=primary_filing.accession if primary_filing else accession_or_file,
                parser_used="ixbrl_html",
                records=html_records,
                route_history=route_history,
            )
            with self._lock:
                self._cache[cache_key] = result
            return result

        if release_records:
            result = IngestionResult(
                status="success",
                accession=release_filing.accession if release_filing else accession_or_file,
                parser_used="ixbrl_html",
                records=release_records,
                route_history=route_history,
            )
            with self._lock:
                self._cache[cache_key] = result
            return result

        # ── Route 3: PDF fallback ─────────────────────────────────────────────
        pdf_bytes = request.file_bytes if request.file_bytes and (request.filename or "").lower().endswith(".pdf") else None
        if pdf_bytes is None and self.edgar_client and primary_filing:
            # Check if PDF available in directory
            try:
                self.edgar_client.get_filing_directory_index(primary_filing)
                pdf_ex = next((e for e in primary_filing.exhibits if e.filename.lower().endswith(".pdf")), None)
                if pdf_ex:
                    pdf_doc = self.edgar_client.get_document(
                        accession=primary_filing.accession,
                        document_name=pdf_ex.filename,
                        cik=primary_filing.cik,
                    )
                    pdf_bytes = pdf_doc.content
            except Exception as exc:  # noqa: BLE001
                logger.debug("Failed locating PDF on EDGAR: %s", exc)

        if pdf_bytes and self.pdf_extractor_fn:
            try:
                pdf_records = self.pdf_extractor_fn(
                    pdf_bytes=pdf_bytes,
                    filename=request.filename or "filing.pdf",
                    target_metric=request.target_metric,
                )
                if pdf_records:
                    route_history.append(RouteAttempt(route="pdf_fallback", status="success"))
                    result = IngestionResult(
                        status="success",
                        accession=accession_or_file,
                        parser_used="docling",
                        records=pdf_records,
                        route_history=route_history,
                    )
                    with self._lock:
                        self._cache[cache_key] = result
                    return result
                else:
                    route_history.append(
                        RouteAttempt(
                            route="pdf_fallback",
                            status="failed",
                            reason="PDF extraction completed but found 0 candidate records",
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                route_history.append(
                    RouteAttempt(route="pdf_fallback", status="failed", reason=str(exc))
                )
        else:
            route_history.append(
                RouteAttempt(
                    route="pdf_fallback",
                    status="failed" if pdf_bytes else "skipped",
                    reason="No PDF file available or PDF extractor not configured",
                )
            )

        # ── All routes exhausted ──────────────────────────────────────────────
        failure_summary = "; ".join([f"{a.route}: {a.status} ({a.reason or 'no detail'})" for a in route_history])
        result = IngestionResult(
            status="failed",
            accession=accession_or_file,
            parser_used="none",
            failure_reason=f"All ingestion routes exhausted: {failure_summary}",
            route_history=route_history,
        )
        with self._lock:
            self._cache[cache_key] = result
        return result
