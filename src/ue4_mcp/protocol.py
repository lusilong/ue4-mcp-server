"""
A tiny, dependency-free MCP (Model Context Protocol) server over stdio.

Speaks newline-delimited JSON-RPC 2.0 on stdin/stdout — the standard MCP
stdio transport — using only the Python standard library. Works on
Python 3.8+ (the official ``mcp`` PyPI package requires 3.10+).

Implements the protocol subset used by opencode / Claude Desktop / Cursor:

    initialize, initialized, ping,
    tools/list, tools/call,
    resources/list, resources/read
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

PROTOCOL_VERSION = "2025-03-26"     # current MCP spec version
SERVER_NAME = "ue4-mcp"
SERVER_VERSION = "0.1.0"
CAPABILITIES = {"tools": {}, "resources": {}}


@dataclass
class Tool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[..., str]
    title: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title or self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass
class Resource:
    uri: str
    name: str
    mime_type: str
    reader: Callable[[], str]

    def to_dict(self) -> Dict[str, Any]:
        return {"uri": self.uri, "name": self.name, "mimeType": self.mime_type}


# ── helpers ───────────────────────────────────────────────────────────────────────

def _send(obj: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _error(req_id: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
    err = {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
    if data is not None:
        err["error"]["data"] = data
    return err


# ── main stdio loop ───────────────────────────────────────────────────────────────

def serve_stdio(tools: List[Tool] = (), resources: List[Resource] = ()) -> None:
    """Block on stdin, responding to each request over stdout.

    Returns when stdin reaches EOF (client exited or pipe closed).
    """
    tools_by_name = {t.name: t for t in tools}
    resources_by_uri = {r.uri: r for r in resources}

    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):
            continue

        method = msg.get("method")
        req_id = msg.get("id")
        params = msg.get("params") or {}
        is_notification = req_id is None

        # ── lifecycle ──
        if method == "initialize":
            client_ver = params.get("protocolVersion", PROTOCOL_VERSION)
            _send({"jsonrpc": "2.0", "id": req_id, "result": {
                "protocolVersion": client_ver,
                "capabilities": CAPABILITIES,
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}}})

        elif method in ("notifications/initialized", "initialized"):
            continue

        elif method == "ping":
            _send({"jsonrpc": "2.0", "id": req_id, "result": {}})

        # ── tools ──
        elif method == "tools/list":
            _send({"jsonrpc": "2.0", "id": req_id,
                   "result": {"tools": [t.to_dict() for t in tools]}})

        elif method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            tool = tools_by_name.get(name)
            if tool is None:
                _send(_error(req_id, -32602, f"Unknown tool: {name}"))
                continue
            try:
                text = tool.handler(**args)
                _send({"jsonrpc": "2.0", "id": req_id, "result": {
                    "content": [{"type": "text", "text": text}], "isError": False}})
            except Exception as exc:  # noqa: BLE001
                _send({"jsonrpc": "2.0", "id": req_id, "result": {
                    "content": [{"type": "text", "text": f"error: {exc}"}],
                    "isError": True}})

        # ── resources ──
        elif method == "resources/list":
            _send({"jsonrpc": "2.0", "id": req_id,
                   "result": {"resources": [r.to_dict() for r in resources]}})

        elif method == "resources/read":
            uri = params.get("uri")
            res = resources_by_uri.get(uri)
            if res is None:
                _send(_error(req_id, -32002, f"Resource not found: {uri}"))
                continue
            try:
                text = res.reader()
                _send({"jsonrpc": "2.0", "id": req_id, "result": {
                    "contents": [{"uri": uri, "mimeType": res.mime_type, "text": text}]}})
            except Exception as exc:  # noqa: BLE001
                _send(_error(req_id, -32603, f"Failed to read {uri}: {exc}"))

        # ── unknown ──
        else:
            if not is_notification:
                _send(_error(req_id, -32601, f"Method not found: {method}"))
