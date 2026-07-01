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


def test_cloudflare_accepts_standard_env_names(monkeypatch) -> None:
    # The standard Cloudflare/wrangler env var names are accepted as aliases.
    monkeypatch.delenv("DSF_CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("DSF_CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok-standard")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-standard")
    settings = Settings()
    assert settings.cloudflare_api_token == "tok-standard"
    assert settings.cloudflare_account_id == "acct-standard"


def test_cloudflare_dsf_prefix_takes_precedence(monkeypatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "standard")
    monkeypatch.setenv("DSF_CLOUDFLARE_API_TOKEN", "dsf")
    assert Settings().cloudflare_api_token == "dsf"


def test_secret_whitespace_is_stripped() -> None:
    # Env vars often carry a trailing newline; it must not reach wrangler/API.
    settings = Settings(cloudflare_api_token="  tok123\n", cloudflare_account_id="acct456\n")
    assert settings.cloudflare_api_token == "tok123"
    assert settings.cloudflare_account_id == "acct456"
