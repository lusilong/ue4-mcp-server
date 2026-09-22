"""
UE4 editor bridge through the engine's own Remote Execution protocol.

The editor side (running inside UE4) exposes a Python command channel via
the PythonScriptPlugin. The engine ships a pure-standard-library client
(``remote_execution.py``) that does UDP multicast discovery + a TCP command
connection — we load *that* file at runtime and drive it, so we never
reimplement the wire format ourselves and never need the ``unreal`` Python
module on the host.

Everything below runs from the plain Python 3 interpreter of the MCP host.
"""
from __future__ import annotations

import importlib.util
import logging
import os
import sys
import time as _time
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("ue4-mcp")

# ── settings ────────────────────────────────────────────────────────────────────────

# Path of the engine's own remote_execution.py. Set the env var to override.
_REX_FILE_ENV = "UE4_REMOTE_EXECUTION_FILE"
_REX_CANDIDATES = (
    "/home/lsl/software/carla_src/UnrealEngine/Engine/Plugins/"
    "Experimental/PythonScriptPlugin/Content/Python/remote_execution.py",
    "/home/lsl/software/carla_src/UnrealEngine/Engine/Plugins/"
    "Experimental/PythonScriptPlugin/Content/Python/remote_execution.py",
)
_REX_SAMPLE_CODE = "import unreal\nprint('hello from " + "editor')\n"

# Local TCP endpoint this client listens on for the editor to connect back;
# must match the PythonScriptPlugin listener, kept on the loopback interface.
_COMMAND_ENDPOINT = ("127.0.0.1", 6777)
_DISCOVER_TIMEOUT = 4.0     # seconds to wait for the editor to answer discovery
_EXEC_TIMEOUT = 90.0        # seconds to wait for a remote command to finish

_rex_module: Any = None     # engine's remote_execution module
_client: Any = None         # engine's RemoteExecution client instance
_endpoint: Optional[Tuple[str, int, str]] = None   # (addr, port, auth)


def _load_rex() -> Any:
    """Import the engine-shipped ``remote_execution`` module (stdlib)."""
    global _rex_module
    if _rex_module is not None:
        return _rex_module

    path = os.environ.get(_REX_FILE_ENV) or ""
    if not path:
        for cand in _REX_CANDIDATES:
            if os.path.isfile(cand):
                path = cand
                break
    if not path:
        raise RuntimeError(
            "engine remote_execution.py not found. Set UE4_REMOTE_EXECUTION_FILE "
            "to the engine's remote_execution.py path and retry.")

    spec = importlib.util.spec_from_file_location("ue4_remote_execution", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    _rex_module = mod
    log.info("loaded engine remote_execution.py from %s", path)
    return mod


def _connect(timeout: float = _DISCOVER_TIMEOUT) -> None:
    """Discover the editor and open one command channel, reusing it later."""
    global _endpoint, _client
    if _client is not None:
        return

    rex = _load_rex()
    cfg = rex.RemoteExecutionConfig()
    cfg.command_endpoint = _COMMAND_ENDPOINT
    client = rex.RemoteExecution(cfg)

    try:
        client.start()
        deadline = _time.monotonic() + timeout
        while _time.monotonic() < deadline:
            if client.remote_nodes:
                break
            _time.sleep(0.25)
        if not client.remote_nodes:
            raise RuntimeError(
                "No UE4 editor answered. Start the editor with PythonScriptPlugin "
                "remote execution enabled and try again.")

        node_id = client.remote_nodes[0]["node_id"]
        client.open_command_connection(node_id)
        _client = client
        log.info("connected to editor node=%s", node_id)
    except Exception as exc:  # noqa: BLE001
        try:
            client.stop()
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(f"Could not reach UE4 editor: {exc}") from exc


def run_in_editor(code: str) -> str:
    """Execute *code* in the running editor and return its stdout/stderr."""
    _connect()
    rex = _load_rex()

    result = _client.run_command(
        code,
        unattended=True,
        exec_mode=rex.MODE_EXEC_FILE,
        raise_on_failure=False,
    )
    out = "".join(chunk.get("output", "") for chunk in result.get("output", []))
    if not result.get("success"):
        out = out.rstrip() + f"\n[error={result.get('result')}]"
    return out or "(no output)"
