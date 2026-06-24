# datasiteforge-core

Foundation package for **DataSiteForge**.

Provides:

- `dsf_core.config` — Pydantic v2 settings (`Settings`, `get_settings`).
- `dsf_core.telemetry` — `rich`-based structured logging.
- `dsf_core.agent_bridge` — the Agent Bridge broker (MCP / stdio / mock transports).
- `dsf_core.cli` — the `seo-platform` command-line entry point.
