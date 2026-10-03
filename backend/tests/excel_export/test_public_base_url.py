"""AUD-034 / D9: workbook links use PUBLIC_BASE_URL, never a hard-coded localhost."""

from pathlib import Path

import openpyxl
import pytest
from app.classification.models import StatementType
from app.excel_export.generator import generate_workbook
from app.extraction.locator import PdfLocator
from app.extraction.models import ConfidenceBand
from app.formula_engine.reader import read_formula_inputs_from_review
from app.formula_engine.tree import build_formula_tree
from app.review.models import ReviewItem, ReviewStatus

BASE = "https://footnote.example.test"


def _item(item_id: str, label: str, value: str, page: int) -> ReviewItem:
    bbox = {"x0": 50.0, "y0": 100.0, "x1": 250.0, "y1": 130.0}
    return ReviewItem(
        id=item_id,
        value=value,
        label=label,
        normalized_label=label,
        statement_type=StatementType.non_gaap_bridge,
        page=page,
        bbox=bbox,
        source_file="synthetic.pdf",
        confidence_band=ConfidenceBand.auto_accepted,
        confidence_score=0.99,
        flags=[],
        status=ReviewStatus.locked,
        locator=PdfLocator(page=page, bbox=bbox, source_file="synthetic.pdf"),
    )


def test_workbook_links_use_public_base_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUBLIC_BASE_URL", BASE + "/")
    batch = read_formula_inputs_from_review(
        [_item("a", "Net Income", "410", 2), _item("b", "Stock-Based Compensation", "64", 2)],
        include_unreviewed=True,
    )
    tree = build_formula_tree(batch, target_metric="Adjusted EBITDA")
    result = generate_workbook(tree, job_id="job-base-url", output_dir=tmp_path)
    assert result.is_success, result.error_detail

    wb = openpyxl.load_workbook(next((tmp_path / "models").glob("*.xlsx")))
    targets: list[str] = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.hyperlink is not None and cell.hyperlink.target:
                    targets.append(cell.hyperlink.target)
                if isinstance(cell.value, str) and cell.value.startswith("=HYPERLINK("):
                    targets.append(cell.value.split('"')[1])
    assert targets, "expected provenance links in the workbook"
    assert not [t for t in targets if "localhost" in t]
    assert all(t.startswith(BASE + "/") for t in targets), targets[:5]
