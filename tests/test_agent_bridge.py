"""Tests for the Agent Bridge broker and its transports."""

from __future__ import annotations

import io
import json
from pathlib import Path

from dsf_core.agent_bridge import AgentBridge, AgentRequest
from dsf_core.config import Settings, reload_settings


def test_mock_transport_returns_fixture(write_mock) -> None:
    write_mock("schema_discovery", {"schema": {"fields": []}, "confidence": 0.5})
    settings = reload_settings()
    bridge = AgentBridge(settings)

    response = bridge.request("schema_discovery", {"probe": True})

    assert response.ok is True
    assert response.transport == "mock"
    assert response.result["confidence"] == 0.5


def test_mock_missing_fixture_is_failure(isolated_env: Path) -> None:
    settings = reload_settings()
    bridge = AgentBridge(settings)

    response = bridge.request("does_not_exist")

    assert response.ok is False
    assert response.transport == "mock"
    assert "no mock fixture" in (response.error or "")


def test_standalone_forces_mock_even_when_transport_is_mcp(isolated_env: Path) -> None:
    # Not production -> runtime not attached -> mock fallback regardless of transport.
    settings = Settings(
        agent_transport="mcp",
        mcp_server_url="http://127.0.0.1:9/rpc",
        is_production=False,
        mock_dir=isolated_env / "mocks",
        data_dir=isolated_env,
    )
    bridge = AgentBridge(settings)
    assert bridge.resolve_transport() == "mock"


def test_stdio_transport_roundtrip(isolated_env: Path) -> None:
    settings = Settings(
        execution_mode="agent",
        is_production=True,
        agent_transport="stdio",
        data_dir=isolated_env,
        mock_dir=isolated_env / "mocks",
    )
    assert settings.agent_runtime_attached is True

    request = AgentRequest(task_type="evaluation", payload={"x": 1})
    # The "agent" replies with a JSON-RPC envelope echoing a result.
    reply = json.dumps(
        {"jsonrpc": "2.0", "id": request.request_id, "result": {"ok_value": 42}}
    )
    stdin = io.StringIO(reply + "\n")
    stdout = io.StringIO()
    bridge = AgentBridge(settings, stdout=stdout, stdin=stdin)

    response = bridge.send(request)

    assert response.ok is True
    assert response.transport == "stdio"
    assert response.result == {"ok_value": 42}
    # The request frame must have been written to stdout.
    written = json.loads(stdout.getvalue().strip())
    assert written["method"] == "evaluation"
    assert written["id"] == request.request_id


def test_stdio_jsonrpc_error_becomes_failure(isolated_env: Path) -> None:
    settings = Settings(
        execution_mode="agent",
        is_production=True,
        agent_transport="stdio",
        data_dir=isolated_env,
        mock_dir=isolated_env / "mocks",
    )
    reply = json.dumps({"jsonrpc": "2.0", "id": "x", "error": {"code": -1, "message": "boom"}})
    bridge = AgentBridge(settings, stdout=io.StringIO(), stdin=io.StringIO(reply + "\n"))

    response = bridge.request("evaluation")

    assert response.ok is False
    assert "boom" in (response.error or "")
