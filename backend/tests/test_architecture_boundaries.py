"""
Architecture boundary tests.

Enforces:
1. Only ``ingestion/edgar/`` may perform network I/O.
2. No module imports an LLM SDK: numbers are extracted deterministically.
3. Layering: ``extraction/`` and ``classification/`` never import ``ingestion/``;
   ``classification/`` never imports ``extraction/``.
"""

import ast
from pathlib import Path

NETWORK_MODULES = ("httpx", "requests", "urllib.request", "socket", "aiohttp")
LLM_MODULES = ("groq", "openai", "anthropic", "ollama", "langchain")


def _get_app_root() -> Path:
    return Path(__file__).parent.parent / "app"


def _extract_imported_modules(file_path: Path) -> list[str]:
    """Parse a python file into an AST and return all imported module names."""
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _violations(
    package: str, forbidden: tuple[str, ...], exclude: str | None = None
) -> list[str]:
    root = _get_app_root()
    found: list[str] = []
    for py_file in (root / package).rglob("*.py"):
        rel = py_file.relative_to(root).as_posix()
        if exclude and rel.startswith(exclude):
            continue
        for mod in _extract_imported_modules(py_file):
            if any(mod == f or mod.startswith(f + ".") for f in forbidden):
                found.append(f"{rel} imports '{mod}'")
    return found


def test_only_edgar_client_does_network_io() -> None:
    assert _violations(".", NETWORK_MODULES, exclude="ingestion/edgar/") == []


def test_no_llm_sdk_imports() -> None:
    assert _violations(".", LLM_MODULES) == []


def test_extraction_and_classification_do_not_import_ingestion() -> None:
    assert _violations("extraction", ("app.ingestion",)) == []
    assert _violations("classification", ("app.ingestion",)) == []


def test_classification_does_not_import_extraction() -> None:
    assert _violations("classification", ("app.extraction",)) == []
