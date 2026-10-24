"""
Contract tests for the A-18 MCP server, over the synthetic fixture store of the
A-02 tests. Messages are JSON-RPC 2.0 lines, as an MCP client sends them.
"""

import io
import json
from pathlib import Path
from typing import Any

import pytest
from app.agent.mcp_server import PROTOCOL_VERSIONS, FootnoteMCP, serve
from app.agent.tools import AgentTools

from tests.tools.test_agent_keys import Fixture, quarterly_issuer


@pytest.fixture
def server(tmp_path: Path) -> FootnoteMCP:
    fx = Fixture(tmp_path / "s.db")
    quarterly_issuer(fx, "0000000001", "FIXT", 100)
    return FootnoteMCP(fx.store)


def call(server: FootnoteMCP, method: str, params: dict[str, Any] | None = None) -> Any:
    response = server.handle(
        {"jsonrpc": "2.0", "id": 7, "method": method, "params": params}
    )
    assert response is not None and response["id"] == 7
    return response


def test_initialize_negotiates_the_protocol(server: FootnoteMCP) -> None:
    r = call(server, "initialize", {"protocolVersion": "2025-03-26"})["result"]
    assert r["protocolVersion"] == "2025-03-26"
    assert r["capabilities"] == {"tools": {"listChanged": False}}
    assert r["serverInfo"]["name"] == "footnote"
    unknown = call(server, "initialize", {"protocolVersion": "1999-01-01"})["result"]
    assert unknown["protocolVersion"] == PROTOCOL_VERSIONS[0]


def test_tools_list_matches_the_agent_tools(server: FootnoteMCP) -> None:
    tools = call(server, "tools/list")["result"]["tools"]
    assert [t["name"] for t in tools] == AgentTools(server.tools.store).names
    for t in tools:
        assert t["inputSchema"]["type"] == "object"
        assert t["annotations"]["readOnlyHint"] is True


def test_tools_call_and_compute_share_one_session(server: FootnoteMCP) -> None:
    r = call(
        server,
        "tools/call",
        {"name": "get_quarters", "arguments": {"ticker": "FIXT", "limit": 4}},
    )["result"]
    assert r["isError"] is False and r["structuredContent"]["status"] == "ok"
    vids = [v["vid"] for v in r["structuredContent"]["values"]]
    assert json.loads(r["content"][0]["text"]) == r["structuredContent"]
    s = call(
        server,
        "tools/call",
        {"name": "compute", "arguments": {"op": "sum", "vids": vids}},
    )["result"]
    assert s["structuredContent"]["values"][0]["value"] == "560"
    bad = call(
        server,
        "tools/call",
        {"name": "compute", "arguments": {"op": "sum", "vids": ["obs:x"]}},
    )["result"]
    assert bad["isError"] is True


def test_errors_and_notifications(server: FootnoteMCP) -> None:
    assert call(server, "resources/list")["error"]["code"] == -32601
    assert call(server, "tools/call", {"name": "drop_table"})["error"]["code"] == -32602
    assert (
        server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    )
    invalid = server.handle({"id": 1, "method": "ping"})
    assert invalid is not None and invalid["error"]["code"] == -32600


def test_stdio_loop(server: FootnoteMCP) -> None:
    lines = "\n".join(
        [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            "{not json",
            json.dumps([1, 2]),
        ]
    )
    out = io.StringIO()
    serve(server, io.StringIO(lines + "\n"), out)
    replies = [json.loads(x) for x in out.getvalue().splitlines()]
    assert replies[0] == {"jsonrpc": "2.0", "id": 1, "result": {}}
    assert [r["error"]["code"] for r in replies[1:]] == [-32700, -32600]
