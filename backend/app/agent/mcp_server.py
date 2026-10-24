"""
A-18: Footnote's read-only MCP server (stdio, JSON-RPC 2.0).

Exposes the agent's tools (A-09, A-10) to any MCP client: ``initialize``,
``tools/list``, ``tools/call`` and ``ping``. One server process is one tool
session, so a ``compute`` call can use vids returned by earlier calls. Nothing
is written to the store, and nothing touches the network: messages arrive on
stdin and leave on stdout, one JSON object per line.

Inside Footnote's own agent the provenance gate guarantees no number is typed by
a model. An external MCP client's model is outside that gate: results carry the
vid, the as-reported string, the checks and the sec.gov source of every value so
the client can cite them, but what it writes is its own.

Usage (from ``backend/``)::

    python -m app.agent.mcp_server --db ../var/footnote.db
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO

from app.agent.tools import AgentTools, tool_specs
from app.store.db import Store

SERVER = {"name": "footnote", "version": "0.1.0"}
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602


class FootnoteMCP:
    def __init__(self, store: Store) -> None:
        self.tools = AgentTools(store)

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """One JSON-RPC message in; a response out, or None for a notification."""
        if message.get("jsonrpc") != "2.0" or not isinstance(
            message.get("method"), str
        ):
            return _error(
                message.get("id"), INVALID_REQUEST, "not a JSON-RPC 2.0 request"
            )
        method, params = message["method"], message.get("params") or {}
        if "id" not in message:  # notifications (e.g. notifications/initialized)
            return None
        rid = message["id"]
        if method == "initialize":
            asked = params.get("protocolVersion")
            version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
            return _result(
                rid,
                {
                    "protocolVersion": version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": SERVER,
                    "instructions": (
                        "Footnote: verified, point-in-time EBITDA bridges of US-listed "
                        "issuers. Every value has a vid, its as-reported string, its "
                        "tie-out checks and a sec.gov source. Use compute for arithmetic."
                    ),
                },
            )
        if method == "ping":
            return _result(rid, {})
        if method == "tools/list":
            return _result(
                rid,
                {
                    "tools": [
                        {
                            "name": s["name"],
                            "description": s["description"],
                            "inputSchema": s["input_schema"],
                            "annotations": {
                                "readOnlyHint": True,
                                "openWorldHint": False,
                            },
                        }
                        for s in tool_specs()
                    ]
                },
            )
        if method == "tools/call":
            name, args = params.get("name"), params.get("arguments") or {}
            if not isinstance(name, str) or not isinstance(args, dict):
                return _error(
                    rid, INVALID_PARAMS, "tools/call needs a name and arguments"
                )
            if name not in self.tools.names:
                return _error(rid, INVALID_PARAMS, f"unknown tool {name!r}")
            result = self.tools.call(name, args).for_model()
            return _result(
                rid,
                {
                    "content": [
                        {"type": "text", "text": json.dumps(result, default=str)}
                    ],
                    "structuredContent": json.loads(json.dumps(result, default=str)),
                    "isError": result["status"] == "invalid",
                },
            )
        return _error(rid, METHOD_NOT_FOUND, f"method {method!r} not supported")


def _result(rid: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _error(rid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def serve(server: FootnoteMCP, stdin: TextIO, stdout: TextIO) -> None:
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            response: dict[str, Any] | None = _error(None, PARSE_ERROR, str(exc))
        else:
            response = (
                server.handle(message)
                if isinstance(message, dict)
                else _error(None, INVALID_REQUEST, "batches are not supported")
            )
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    if not args.db.exists():
        print(f"no store at {args.db}", file=sys.stderr)
        return 1
    serve(FootnoteMCP(Store(args.db)), sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
