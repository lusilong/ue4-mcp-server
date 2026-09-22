"""
UE4 MCP core: a tiny, dependency-free MCP stdio server plus a UE4
Remote-Execution client. Every tool talks to the *running* UE editor via
UDP discovery + HTTP POST -- no `unreal` import is needed on the host,
which is what keeps the whole thing installable on a plain Python.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import sys
import time as _time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

log = logging.getLogger("ue4_mcp")

PROTOCOL_VERSION = "2025-03-26"   # MCP spec version this server implemented.
SERVER_NAME = "ue4-mcp"
SERVER_VERSION = "0.1.0"

# JsonRPC requests come in one-per-line over stdio (MCP stdio transport).


# ── minimal tool/resource registry ────────────────────────────────────────────────

@dataclass
class Tool:
    name: str
    description: str
    input_schema: Dict[str, Any]          # JSON Schema (object)
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
    mime_type: str = "text/plain"
    handler: Callable[[], str] = field(default=lambda: "")

    def to_dict(self) -> Dict[str, Any]:
        return {"uri": self.uri, "name": self.name, "mimeType": self.mime_type}

    def read(self) -> str:
        return self.handler()


# ── UE4 Remote Execution (wire) ───────────────────────────────────────────────────

_MAGIC = bytes.fromhex("21894ed8")


def _discover(timeout: float = 4.0) -> Optional[Tuple[str, int, str]]:
    """Find a running UE editor via its broadcast endpoint."""
    ep = None
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    try:
        sock.sendto(b'{"Type":"icast","Version":1}', ("<broadcast>", 6766))
        data, _addr = sock.recvfrom(65535)
        reply = json.loads(data.decode("utf-8", "replace"))
        if reply.get("Type") == "icr":
            ep = (reply["Addr"], int(reply["Port"]), reply.get("Auth", ""))
    except (socket.timeout, OSError, ValueError, KeyError):
        log.debug("discovery: no editor reply", exc_info=True)
    finally:
        sock.close()
    return ep


def _http_exec(addr: str, port: int, auth: str, code: str,
               timeout: float = 60.0) -> str:
    import urllib.request as ureq

    body = json.dumps({
        "Type": 1, "Version": 1, "Magic": _MAGIC.hex(),
        "Results": -1, "Flags": 0, "Path": "",
        "Output": -1, "Exec": code,
    }).encode()
    req = ureq.Request(f"http://{addr}:{port}/remote/exec", data=body,
                       method="POST")
    req.add_header("Content-Type", "application/json")
    if auth:
        req.add_header("Authorization", f"Bearer {auth}")
    try:
        with ureq.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Remote exec failed: {exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    out = payload.get("Output", "")
    if payload.get("Results", 0) not in (0, 1):
        out += f"\n[exit={payload.get('Results')}]" if out else ""
    return out


def run_in_editor(code: str) -> str:
    """Discover the editor and run `code` in it, returning stdout."""
    ep = _discover()
    if ep is None:
        raise RuntimeError(
            "No UE editor found. Start it with PythonScriptPlugin + "
            "remote execution enabled and try again.")
    return _http_exec(*ep, code)


# ── helpers for building code handed to the editor ───────────────────────────────

def _exec(code: str) -> str:
    return run_in_editor("import unreal\n" + code)
