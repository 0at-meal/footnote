"""
Architecture boundary tests.

Enforces:
1. Only ``ingestion/edgar/`` may perform network I/O.
2. No module imports an LLM SDK: numbers are extracted deterministically.
3. Layering: ``extraction/`` and ``classification/`` never import ``ingestion/``;
   ``store/`` imports neither; ``analytics/``, ``api/`` and ``export/`` never
   import ``ingestion/`` or ``pipeline/``;
   ``classification/`` never imports ``extraction/``.
4. Track A (ADR-011): ``agent/`` never imports ``ingestion/`` or ``pipeline/``
   and never calls a store write method.
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


def test_store_is_independent_of_ingestion_and_extraction() -> None:
    assert _violations("store", ("app.ingestion", "app.extraction")) == []


def test_analytics_and_api_never_fetch() -> None:
    """Served numbers come from stored observations, never from a live fetch."""
    assert _violations("analytics", ("app.ingestion", "app.pipeline")) == []
    assert _violations("api", ("app.ingestion", "app.pipeline")) == []
    assert _violations("export", ("app.ingestion", "app.pipeline")) == []


# Store methods that write; the agent's tools only read (ADR-011).
STORE_WRITES = (
    "add_failure",
    "upsert_issuer",
    "add_filing",
    "add_bridge",
    "set_label",
    "start_run",
    "finish_run",
    "tx",
    "execute",
    "executescript",
    "commit",
)


def test_agent_never_fetches_or_writes() -> None:
    assert _violations("agent", ("app.ingestion", "app.pipeline")) == []
    root = _get_app_root()
    found: list[str] = []
    for py_file in (root / "agent").rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in STORE_WRITES:
                found.append(
                    f"{py_file.relative_to(root).as_posix()} uses .{node.attr}"
                )
            if isinstance(node, ast.ImportFrom) and any(
                a.name == "category_for" for a in node.names
            ):
                found.append(
                    f"{py_file.name} imports category_for (writes label memory)"
                )
    assert found == []
