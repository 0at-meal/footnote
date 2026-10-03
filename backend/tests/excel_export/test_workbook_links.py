"""
AUD-018: every hyperlink written into a workbook must resolve.

- Local links (PDF source, cell provenance) are requested through the real app and must return 200.
- SEC links must be well-formed EDGAR Archives URLs that include the CIK (decision D9); they are
  checked for shape only, because live SEC requests need SEC_USER_AGENT (not configured here).

The workbook comes from the real pipeline on a SYNTHETIC PDF and the real POST /models/{job}/generate
route; only the LLM classifier is stubbed. HTML locator values below are SYNTHETIC (not a real filing).
"""

import re
from pathlib import Path
from unittest.mock import MagicMock

import openpyxl
from app.classification.models import ClassifierRawResponse
from app.config import public_base_url
from app.excel_export.provenance import (
    build_w3c_annotation_for_node,
    format_source_deep_link,
)
from app.extraction.html.extractor import HtmlExtractor
from app.extraction.locator import HtmlLocator
from app.formula_engine.models import FormulaInputNode, FormulaNode
from app.ingestion.repository import JobRepository
from app.job_runner import process_queued_job
from app.main import app
from fastapi.testclient import TestClient

from tests.fixtures.synthetic.pdfs import SYNTHETIC_EBITDA_BRIDGE, write_synthetic_pdf

SEC_ARCHIVES = re.compile(r"^https://www\.sec\.gov/Archives/edgar/data/[1-9]\d*/\d{18}/[^/#?]+(#:~:text=\S+)?$")

# SYNTHETIC identifiers: shaped like EDGAR values, not taken from any filing.
SYN_CIK = "0009999999"
SYN_ACCESSION = "0009999999-26-000001"
SYN_DOCUMENT = "synthetic-20260630.htm"


def _workbook_links(path: Path) -> list[str]:
    wb = openpyxl.load_workbook(path)
    links = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.hyperlink is not None and cell.hyperlink.target:
                    links.append(cell.hyperlink.target)
    return links


def test_every_local_workbook_link_returns_200(tmp_path: Path) -> None:
    repo = JobRepository()  # the session's isolated data dir (tests/conftest.py), same as the app's
    pdf = write_synthetic_pdf(tmp_path / "synthetic_bridge_links.pdf", [SYNTHETIC_EBITDA_BRIDGE])
    job = repo.save_job(
        filename="synthetic_bridge_links.pdf",
        content=pdf.read_bytes(),
        target_metric="Adjusted EBITDA",
        filing_year=2025,
        workflow_pack="non_gaap_bridge",
    )
    classifier = MagicMock()
    classifier.classify.return_value = ClassifierRawResponse(label="Other", confidence=0.5)
    process_queued_job(job.job_id, repo, classifier_client=classifier)

    client = TestClient(app)
    generated = client.post(f"/models/{job.job_id}/generate")
    assert generated.status_code == 200, generated.text
    links = _workbook_links(Path(generated.json()["file_path"]))
    assert links, "workbook has no hyperlinks to check"

    base = public_base_url()
    failures = []
    for link in sorted(set(links)):
        assert link.startswith(base), f"unexpected link target {link}"
        resp = client.get(link.removeprefix(base))
        if resp.status_code != 200:
            failures.append(f"{resp.status_code} {link}")
    assert failures == []


def test_every_capital_structure_workbook_link_returns_200(tmp_path: Path) -> None:
    """Same check for the capital_structure workbook (Debt_Tranches provenance links)."""
    from app.footnote.models import DebtSchedule, DebtTranche
    from app.footnote.repository import DebtScheduleRepository

    repo = JobRepository()
    pdf = write_synthetic_pdf(tmp_path / "synthetic_debt_links.pdf", [SYNTHETIC_EBITDA_BRIDGE])
    job = repo.save_job(
        filename="synthetic_debt_links.pdf",
        content=pdf.read_bytes(),
        target_metric="Adjusted EBITDA",
        filing_year=2025,
        workflow_pack="capital_structure",
    )
    # SYNTHETIC debt schedule (not filing data).
    DebtScheduleRepository().save_debt_schedule(
        DebtSchedule(
            job_id=job.job_id,
            footnote_title="Synthetic Note: Debt",
            tranches=[
                DebtTranche(
                    id="t1", instrument_name="Synthetic Term Loan", principal_amount=100.0, principal_text="100",
                    interest_rate=5.0, rate_text="5.0%", maturity_year=2030, senior_subordinated="senior",
                    is_floating=False, spread=None, benchmark=None, page=1,
                    bbox={"x0": 100.0, "y0": 100.0, "x1": 200.0, "y1": 120.0},
                )
            ],
            total_debt=100.0,
            weighted_avg_rate=5.0,
            is_confirmed=False,
        )
    )

    client = TestClient(app)
    generated = client.post(f"/models/{job.job_id}/generate")
    assert generated.status_code == 200, generated.text
    links = _workbook_links(Path(generated.json()["file_path"]))
    assert links, "workbook has no hyperlinks to check"
    base = public_base_url()
    failures = [
        f"{resp.status_code} {link}"
        for link in sorted(set(links))
        if (resp := client.get(link.removeprefix(base))).status_code != 200
    ]
    assert failures == []


def _html_leaf(locator: HtmlLocator) -> FormulaNode:
    source = FormulaInputNode(
        node_id="input-1",
        record_index=0,
        value="1,000",
        label="Synthetic adjustment",
        normalized_label="Synthetic adjustment",
        page=1,
        bbox={"x0": 0.0, "y0": 0.0, "x1": 1000.0, "y1": 1000.0},
        source_file=SYN_DOCUMENT,
        locator=locator,
    )
    return FormulaNode(node_id="leaf-1", label="Synthetic adjustment", node_type="leaf", source_node=source)


def test_sec_document_url_includes_cik_and_text_fragment() -> None:
    from app.excel_export.provenance import sec_document_url

    url = sec_document_url(SYN_CIK, SYN_ACCESSION, SYN_DOCUMENT, text="Net income, 1,000")
    assert url is not None
    assert SEC_ARCHIVES.match(url), url
    assert url.startswith("https://www.sec.gov/Archives/edgar/data/9999999/000999999926000001/synthetic-20260630.htm")
    # Text-fragment syntax characters inside the quoted text are percent-encoded.
    assert url.endswith("#:~:text=Net%20income%2C%201%2C000")
    hyphen = sec_document_url(SYN_CIK, SYN_ACCESSION, SYN_DOCUMENT, text="Pre-tax income")
    assert hyphen is not None and hyphen.endswith("#:~:text=Pre%2Dtax%20income")


def test_sec_document_url_without_cik_is_none() -> None:
    from app.excel_export.provenance import sec_document_url

    assert sec_document_url(None, SYN_ACCESSION, SYN_DOCUMENT) is None


def test_html_source_deep_link_uses_cik() -> None:
    loc = HtmlLocator(cik=SYN_CIK, accession=SYN_ACCESSION, document=SYN_DOCUMENT, element_path="/html/body/table[1]/tr[2]/td[2]")
    link = format_source_deep_link("job-x", node=_html_leaf(loc))
    assert link is not None and SEC_ARCHIVES.match(link), link
    assert "/data/9999999/" in link


def test_html_source_deep_link_without_cik_or_url_is_not_invented() -> None:
    """No CIK means no valid Archives URL; the old builders produced a 404 link instead (I3)."""
    loc = HtmlLocator(accession=SYN_ACCESSION, document=SYN_DOCUMENT, element_path="/html/body/table[1]/tr[2]/td[2]")
    assert format_source_deep_link("job-x", node=_html_leaf(loc)) is None
    anno = build_w3c_annotation_for_node("job-x", "Source_Inputs", "A2", _html_leaf(loc))
    assert not anno.target.source.startswith("http"), anno.target.source


def test_html_extractor_builds_archives_url_with_cik() -> None:
    html = (
        "<html><body><p>Reconciliation of Net Income to Adjusted EBITDA</p><table>"
        "<tr><td></td><td>2025</td></tr>"
        "<tr><td>Net income</td><td>1,000</td></tr>"
        "<tr><td>Depreciation</td><td>200</td></tr>"
        "<tr><td>Adjusted EBITDA</td><td>1,200</td></tr>"
        "</table></body></html>"
    )
    result = HtmlExtractor().extract(html, accession=SYN_ACCESSION, document_name=SYN_DOCUMENT, cik=SYN_CIK)
    assert result.records, result.not_found_reason
    for rec in result.records:
        assert rec.locator is not None and rec.locator.type == "html"
        assert rec.locator.cik == SYN_CIK
        assert rec.locator.url is not None and SEC_ARCHIVES.match(rec.locator.url), rec.locator.url
