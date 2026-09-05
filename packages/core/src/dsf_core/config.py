"""Centralised configuration for DataSiteForge.

All settings are sourced (in order of precedence) from explicit constructor
arguments, environment variables prefixed with ``DSF_``, a local ``.env`` file,
and finally the defaults declared here.  Path settings resolve to sensible
locations under the workspace ``data/`` directory when left unset.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ExecutionMode = Literal["agent", "standalone"]
AgentTransport = Literal["mcp", "stdio", "mock"]


def find_workspace_root(start: Path | None = None) -> Path:
    """Locate the workspace root by walking upward for the uv workspace marker.

    Falls back to the current working directory if no marker is found, which is
    the common case when the CLI is launched from the repository root.
    """
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file():
            try:
                text = pyproject.read_text(encoding="utf-8")
            except OSError:
                continue
            if "[tool.uv.workspace]" in text:
                return candidate
    return Path.cwd().resolve()


class Settings(BaseSettings):
    """Strongly-typed application settings.

    Environment variables use the ``DSF_`` prefix, e.g. ``DSF_EXECUTION_MODE``.
    """

    model_config = SettingsConfigDict(
        env_prefix="DSF_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    execution_mode: ExecutionMode = Field(
        default="standalone",
        description="Whether an orchestrating agent runtime is expected to be attached.",
    )
    is_production: bool = Field(
        default=False,
        description="When false the Agent Bridge always falls back to file-driven mocks.",
    )
    agent_transport: AgentTransport = Field(
        default="mock",
        description="Transport used to reach the orchestrating agent.",
    )
    mcp_server_url: str | None = Field(
        default=None,
        description="JSON-RPC / MCP endpoint, used only when agent_transport == 'mcp'.",
    )
    agent_timeout_seconds: float = Field(default=60.0, gt=0)

    # Cloudflare deploy + verified HTTP analytics.
    cloudflare_api_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DSF_CLOUDFLARE_API_TOKEN", "CLOUDFLARE_API_TOKEN"),
    )
    cloudflare_account_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DSF_CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_ACCOUNT_ID"),
    )

    # Search Console access is read-only. OAuth refresh remains an external concern;
    # the platform accepts a short-lived bearer token through the runtime environment
    # and never persists it in SQLite.
    google_search_console_access_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "DSF_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN",
            "GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN",
            "GSC_ACCESS_TOKEN",
        ),
    )

    # Ahrefs real metrics are applied only after the cheap million-row discovery pass.
    ahrefs_api_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DSF_AHREFS_API_TOKEN", "AHREFS_API_TOKEN"),
        description="Ahrefs API v3 token; when set, Scout can attach verified keyword metrics.",
    )

    api_token: str | None = Field(
        default=None,
        description=(
            "When set, the control-plane API requires this token via an "
            "'Authorization: Bearer <token>' or 'X-API-Key' header. Unset = open (dev)."
        ),
    )

    data_dir: Path | None = Field(default=None)
    sqlite_path: Path | None = Field(default=None)
    duckdb_path: Path | None = Field(default=None)
    mock_dir: Path | None = Field(default=None)

    @field_validator(
        "mcp_server_url",
        "cloudflare_api_token",
        "cloudflare_account_id",
        "google_search_console_access_token",
        "api_token",
        "ahrefs_api_token",
    )
    @classmethod
    def _clean_secret(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def _resolve_paths(self) -> Settings:
        data_dir = self.data_dir or (find_workspace_root() / "data")
        self.data_dir = data_dir.resolve()
        if self.sqlite_path is None:
            self.sqlite_path = self.data_dir / "state.sqlite"
        if self.duckdb_path is None:
            self.duckdb_path = self.data_dir / "analytics.duckdb"
        if self.mock_dir is None:
            self.mock_dir = self.data_dir / "mocks"
        self.sqlite_path = self.sqlite_path.resolve()
        self.duckdb_path = self.duckdb_path.resolve()
        self.mock_dir = self.mock_dir.resolve()
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlite_url(self) -> str:
        return f"sqlite:///{self.sqlite_path}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def agent_runtime_attached(self) -> bool:
        if not self.is_production or self.execution_mode != "agent":
            return False
        if self.agent_transport == "mcp":
            return bool(self.mcp_server_url)
        if self.agent_transport == "stdio":
            return True
        return False

    def ensure_directories(self) -> None:
        assert self.data_dir is not None
        assert self.sqlite_path is not None
        assert self.duckdb_path is not None
        assert self.mock_dir is not None
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.mock_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.duckdb_path.parent.mkdir(parents=True, exist_ok=True)


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
