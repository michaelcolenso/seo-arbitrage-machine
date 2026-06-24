"""The Agent Bridge: an abstract runtime broker for cognitive tasks.

DataSiteForge never hard-codes an LLM provider.  Instead, components that need
intelligence (schema discovery, monetisation evaluation, content reinforcement)
serialise a structured :class:`AgentRequest` and hand it to :class:`AgentBridge`.
The bridge routes the request over one of three transports:

* ``mcp``   — POST a JSON-RPC 2.0 envelope to a Model Context Protocol endpoint.
* ``stdio`` — write a newline-delimited JSON frame to stdout for the orchestrating
  agent (e.g. Claude Code) to intercept, then read the reply frame from stdin.
* ``mock``  — load a deterministic response from ``<mock_dir>/<task_type>.json``.

When no real runtime is attached (``settings.agent_runtime_attached`` is false),
the bridge transparently falls back to ``mock``.  Every failure mode is caught
and surfaced as ``AgentResponse(ok=False, error=...)`` — the bridge never raises
into caller code, satisfying the defensive-failure-isolation mandate.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import IO, Any

import httpx
from pydantic import BaseModel, Field

from .config import AgentTransport, Settings, get_settings
from .telemetry import get_logger, log_event

_log = get_logger("agent_bridge")

# JSON-RPC 2.0 protocol constant.
_JSONRPC_VERSION = "2.0"


class AgentRequest(BaseModel):
    """A structured cognitive task dispatched to the agent runtime."""

    task_type: str = Field(description="Logical operation, e.g. 'schema_discovery'.")
    payload: dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)

    def to_jsonrpc(self) -> dict[str, Any]:
        """Render the request as a JSON-RPC 2.0 envelope."""
        return {
            "jsonrpc": _JSONRPC_VERSION,
            "id": self.request_id,
            "method": self.task_type,
            "params": self.payload,
        }


class AgentResponse(BaseModel):
    """The result of an :class:`AgentRequest`.

    ``ok`` is the single source of truth for success; callers should branch on it
    rather than inspecting ``error`` or ``result`` directly.
    """

    request_id: str
    ok: bool
    transport: AgentTransport
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

    @classmethod
    def success(
        cls, request_id: str, transport: AgentTransport, result: dict[str, Any]
    ) -> AgentResponse:
        return cls(request_id=request_id, ok=True, transport=transport, result=result)

    @classmethod
    def failure(
        cls, request_id: str, transport: AgentTransport, error: str
    ) -> AgentResponse:
        return cls(request_id=request_id, ok=False, transport=transport, error=error)


class AgentBridgeError(RuntimeError):
    """Raised internally by transport handlers; never escapes :meth:`AgentBridge.request`."""


class AgentBridge:
    """Routes cognitive tasks to the orchestrating agent or to mock fallbacks."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        stdout: IO[str] | None = None,
        stdin: IO[str] | None = None,
    ) -> None:
        self.settings: Settings = settings or get_settings()
        # Injectable streams keep the stdio transport unit-testable.
        self._stdout: IO[str] = stdout if stdout is not None else sys.stdout
        self._stdin: IO[str] = stdin if stdin is not None else sys.stdin

    # -- public API --------------------------------------------------------

    def resolve_transport(self) -> AgentTransport:
        """Pick the effective transport, honouring the mock-fallback rule."""
        if not self.settings.agent_runtime_attached:
            return "mock"
        return self.settings.agent_transport

    def request(self, task_type: str, payload: dict[str, Any] | None = None) -> AgentResponse:
        """Dispatch a cognitive task and return a never-raising response."""
        return self.send(AgentRequest(task_type=task_type, payload=payload or {}))

    def send(self, req: AgentRequest) -> AgentResponse:
        """Dispatch a pre-built request, preserving its ``request_id``."""
        transport = self.resolve_transport()
        log_event(
            _log,
            "agent.request",
            request_id=req.request_id,
            task_type=req.task_type,
            transport=transport,
        )
        try:
            if transport == "mcp":
                result = self._request_mcp(req)
            elif transport == "stdio":
                result = self._request_stdio(req)
            else:
                result = self._request_mock(req)
            response = AgentResponse.success(req.request_id, transport, result)
            log_event(_log, "agent.response.ok", request_id=req.request_id, transport=transport)
            return response
        except Exception as exc:  # noqa: BLE001 — bridge must never propagate
            log_event(
                _log,
                "agent.response.error",
                level=40,  # logging.ERROR
                request_id=req.request_id,
                transport=transport,
                error=str(exc),
            )
            return AgentResponse.failure(req.request_id, transport, str(exc))

    # -- transport handlers ------------------------------------------------

    def _request_mcp(self, req: AgentRequest) -> dict[str, Any]:
        url = self.settings.mcp_server_url
        if not url:
            raise AgentBridgeError("agent_transport=mcp but DSF_MCP_SERVER_URL is unset")
        try:
            with httpx.Client(timeout=self.settings.agent_timeout_seconds) as client:
                http_response = client.post(url, json=req.to_jsonrpc())
                http_response.raise_for_status()
                body = http_response.json()
        except httpx.HTTPError as exc:
            raise AgentBridgeError(f"MCP transport HTTP error: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise AgentBridgeError(f"MCP transport returned invalid JSON: {exc}") from exc
        return self._unwrap_jsonrpc(body)

    def _request_stdio(self, req: AgentRequest) -> dict[str, Any]:
        frame = json.dumps(req.to_jsonrpc(), separators=(",", ":"))
        try:
            self._stdout.write(frame + "\n")
            self._stdout.flush()
            line = self._stdin.readline()
        except (OSError, ValueError) as exc:
            raise AgentBridgeError(f"stdio transport I/O error: {exc}") from exc
        if not line:
            raise AgentBridgeError("stdio transport received no response frame (EOF)")
        try:
            body = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AgentBridgeError(f"stdio transport returned invalid JSON: {exc}") from exc
        return self._unwrap_jsonrpc(body)

    def _request_mock(self, req: AgentRequest) -> dict[str, Any]:
        mock_dir = self.settings.mock_dir
        if mock_dir is None:
            raise AgentBridgeError("mock_dir is not configured")
        mock_file: Path = mock_dir / f"{req.task_type}.json"
        if not mock_file.is_file():
            raise AgentBridgeError(
                f"no mock fixture for task_type={req.task_type!r} at {mock_file}"
            )
        try:
            data = json.loads(mock_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AgentBridgeError(f"failed to load mock {mock_file}: {exc}") from exc
        if not isinstance(data, dict):
            raise AgentBridgeError(f"mock {mock_file} must contain a JSON object")
        return data

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _unwrap_jsonrpc(body: dict[str, Any]) -> dict[str, Any]:
        """Extract the ``result`` payload from a JSON-RPC 2.0 response envelope."""
        if not isinstance(body, dict):
            raise AgentBridgeError("agent response was not a JSON object")
        if "error" in body and body["error"]:
            raise AgentBridgeError(f"agent returned JSON-RPC error: {body['error']}")
        result = body.get("result", {})
        if not isinstance(result, dict):
            raise AgentBridgeError("agent JSON-RPC 'result' was not an object")
        return result
