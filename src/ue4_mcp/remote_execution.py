"""UE4/5 Remote Execution client — discovers and talks to the editor over UDP+HTTP."""
import json
import socket
import struct
import time
import logging

log = logging.getLogger("ue4-mcp")

# ── protocol constants (matches Engine/Plugins/Experimental/PythonScriptPlugin) ──
_MAGIC       = b"ue_py"
_VERSION     = 1
_DISCOVER_PORT = 6766          # UDP broadcast port (DefaultEngine.ini)
_EXEC_PATH     = "/remote/exec"
_TIMEOUT_S     = 3.0            # seconds to wait for discovery / exec reply


class Endpoint:
    """Resolved UE4 remote-execution endpoint."""
    __slots__ = ("addr", "port", "auth", "node_id", "machine", "username")

    def __init__(self, addr: str, port: int, auth: str,
                 node_id: str = "", machine: str = "", username: str = ""):
        self.addr = addr
        self.port = port
        self.auth = auth
        self.node_id = node_id
        self.machine = machine
        self.username = username

    def __repr__(self):
        return f"Endpoint({self.addr}:{self.port} node={self.node_id!r})"


# ── UDP discovery ───────────────────────────────────────────────────────────────

def _discover_once(timeout: float = _TIMEOUT_S) -> Endpoint | None:
    """Send one UDP broadcast and return the first valid reply."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    msg = json.dumps({"Type": "icast", "Version": _VERSION}).encode()
    try:
        sock.sendto(msg, ("<broadcast>", _DISCOVER_PORT))
        data, _ = sock.recvfrom(4096)
        resp = json.loads(data.decode())
        if resp.get("Type") == "icr" and "Addr" in resp:
            return Endpoint(
                addr=resp["Addr"],
                port=int(resp["Port"]),
                auth=resp.get("Auth", ""),
                node_id=resp.get("NodeId", ""),
                machine=resp.get("Machine", ""),
                username=resp.get("UserName", ""),
            )
    except (socket.timeout, json.JSONDecodeError, KeyError, OSError) as exc:
        log.debug("discovery attempt failed: %s", exc)
    finally:
        sock.close()
    return None


def discover(retries: int = 5, delay: float = 0.5) -> Endpoint:
    """Try to discover a UE4 editor on the local network.

    Raises RuntimeError if no endpoint is found after *retries* attempts.
    """
    for i in range(retries):
        ep = _discover_once()
        if ep is not None:
            log.info("discovered %s", ep)
            return ep
        if i < retries - 1:
            time.sleep(delay)
    raise RuntimeError(
        f"Could not discover a UE4/5 editor after {retries} attempts.  "
        "Make sure the editor is running with Remote Execution enabled "
        "(DefaultEngine.ini → [PythonScriptPlugin] bRemoteExecution=True)."
    )


# ── HTTP command execution ─────────────────────────────────────────────────────

def run_command(endpoint: Endpoint, code: str, *,
                mode: str = "exec",
                timeout: float = _TIMEOUT_S) -> str:
    """Send *code* to the UE4 editor and return its stdout/stderr.

    *mode* is one of ``"exec"`` (run a file-like block) or ``"eval"``
    (return the expression value).
    """
    from urllib.request import Request, urlopen
    from urllib.error import URLError

    body = json.dumps({
        "Type":    1,
        "Version": _VERSION,
        "Magic":   _MAGIC.hex(),
        "Results": -1,
        "Flags":   0,
        "Path":    "",
        "Output":  -1,
        "Exec":    code,
    }).encode()

    url = f"http://{endpoint.addr}:{endpoint.port}{_EXEC_PATH}"
    req = Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if endpoint.auth:
        req.add_header("Authorization", f"Bearer {endpoint.auth}")

    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
    except (URLError, socket.timeout, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Remote execution request failed: {exc}") from exc

    result_code = data.get("Results", -1)
    output = data.get("Output", "")
    if result_code != 0:
        raise RuntimeError(f"UE4 returned error code {result_code}:\n{output}")
    return output


# ── convenience wrapper ────────────────────────────────────────────────────────

class UE4Client:
    """High-level client that auto-discovers and caches the endpoint."""

    def __init__(self, retries: int = 5):
        self._ep: Endpoint | None = None
        self._retries = retries

    @property
    def endpoint(self) -> Endpoint:
        if self._ep is None:
            self._ep = discover(retries=self._retries)
        return self._ep

    def run_python(self, code: str, **kw) -> str:
        """Execute *code* in the editor and return its output."""
        return run_command(self.endpoint, code, **kw)

    def reset(self):
        self._ep = None
