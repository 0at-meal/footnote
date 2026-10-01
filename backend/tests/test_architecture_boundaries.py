"""
Architecture boundary and invariant enforcement tests (FN-002).

Enforces:
1. Invariant I1: Classification models contain no numeric fields.
2. Invariant I2: Formula engine is pure with zero I/O imports.
3. Dependency isolation: Classifier must not import formula engine or excel export.
4. Dependency isolation: Formula engine must not import ingestion, excel export, or audit.
"""

import ast
from pathlib import Path


def _get_app_root() -> Path:
    return Path(__file__).parent.parent / "app"


def _extract_imported_modules(file_path: Path) -> list[str]:
    """Parse a python file into an AST and return all top-level imported module names."""
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_classifier_does_not_import_downstream_modules() -> None:
    """Classifier must not import formula engine, excel export, or review internals."""
    classification_dir = _get_app_root() / "classification"
    forbidden_prefixes = (
        "app.formula_engine",
        "app.excel_export",
        "app.audit_trail",
        "app.audit_report",
    )

    for py_file in classification_dir.glob("*.py"):
        imported = _extract_imported_modules(py_file)
        for mod in imported:
            for forbidden in forbidden_prefixes:
                assert not mod.startswith(
                    forbidden
                ), f"Boundary violation: {py_file.name} imports forbidden module '{mod}'"


def test_formula_engine_does_not_import_io_or_downstream() -> None:
    """Formula engine must remain pure: no network, no database, no excel export."""
    formula_dir = _get_app_root() / "formula_engine"
    forbidden_modules = (
        "app.excel_export",
        "app.ingestion",
        "app.audit_trail",
        "app.audit_report",
        "requests",
        "httpx",
        "urllib",
        "socket",
        "sqlite3",
        "aiohttp",
    )

    for py_file in formula_dir.glob("*.py"):
        imported = _extract_imported_modules(py_file)
        for mod in imported:
            for forbidden in forbidden_modules:
                assert not mod.startswith(
                    forbidden
                ), f"Purity violation: {py_file.name} in formula_engine imports '{mod}'"


def test_invariant_i1_classifier_has_no_numeric_fields() -> None:
    """Invariant I1: Classifier models must not expose numeric fields for financial values."""
    from app.classification.models import (
        ClassifiedRecord,
        ClassifierInputPayload,
        ClassifierRawResponse,
        DecisionLogEntry,
    )

    # ClassifierInputPayload carries only label and surrounding text
    for field_name in ClassifierInputPayload.model_fields:
        assert field_name not in ("value", "amount", "numeric_value", "number")

    # ClassifierRawResponse output is strictly categorical (label + confidence score)
    assert "value" not in ClassifierRawResponse.model_fields
    assert "amount" not in ClassifierRawResponse.model_fields

    # DecisionLogEntry logs the classification label decisions without financial figures
    assert "value" not in DecisionLogEntry.model_fields
    assert "amount" not in DecisionLogEntry.model_fields

    # ClassifiedRecord classification fields are non-numeric
    assert ClassifiedRecord.model_fields["normalized_label"].annotation in (str, str | None)
