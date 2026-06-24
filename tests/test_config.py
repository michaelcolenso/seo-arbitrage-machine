"""Tests for the Pydantic settings layer."""

from __future__ import annotations

from pathlib import Path

from dsf_core.config import Settings, reload_settings


def test_defaults_resolve_paths(isolated_env: Path) -> None:
    settings = reload_settings()
    assert settings.execution_mode == "standalone"
    assert settings.is_production is False
    assert settings.agent_transport == "mock"
    assert settings.data_dir == isolated_env.resolve()
    assert settings.sqlite_path == (isolated_env / "state.sqlite").resolve()
    assert settings.duckdb_path == (isolated_env / "analytics.duckdb").resolve()
    assert settings.sqlite_url == f"sqlite:///{settings.sqlite_path}"


def test_runtime_not_attached_in_standalone(isolated_env: Path) -> None:
    settings = reload_settings()
    assert settings.agent_runtime_attached is False


def test_runtime_attached_requires_production_agent_and_endpoint() -> None:
    attached = Settings(
        execution_mode="agent",
        is_production=True,
        agent_transport="mcp",
        mcp_server_url="http://127.0.0.1:9/rpc",
    )
    assert attached.agent_runtime_attached is True

    # Missing endpoint -> not attached even in production agent mode.
    missing_url = Settings(
        execution_mode="agent",
        is_production=True,
        agent_transport="mcp",
        mcp_server_url=None,
    )
    assert missing_url.agent_runtime_attached is False


def test_empty_secret_strings_become_none() -> None:
    settings = Settings(cloudflare_api_token="", mcp_server_url="  ")
    assert settings.cloudflare_api_token is None
    assert settings.mcp_server_url is None
