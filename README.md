# DataSiteForge (DSF)

An agent-native engine that transforms public datasets into hyper-optimized,
zero-hosting-cost, high-utility programmatic web applications (interactive
calculators, B2B directories, local lead-generation search engines).

> **Status:** Foundation (Phase 0 + Phase 1) implemented. Later phases — Scout,
> Evaluator, Astro compiler, Cloudflare deployer, telemetry optimizer, and the
> FastAPI/dashboard control plane — are scaffolded for but not yet built.

## Architecture

DataSiteForge never hard-codes an LLM provider. Cognitive work (schema discovery,
monetisation evaluation, content reinforcement) is routed through an **Agent
Bridge** that speaks MCP / JSON-RPC over HTTP, exchanges newline-delimited frames
over stdio with an orchestrating agent (e.g. Claude Code), or falls back to
deterministic file-driven mocks when no runtime is attached.

## Monorepo layout

```
pyproject.toml          # root uv workspace
packages/
  core/                 # settings, telemetry, Agent Bridge, the seo-platform CLI
  engine/               # SQLModel state store + thread-safe DuckDB analytics broker
  scout/                # arbitrage miner + multi-source candidate discovery
  compiler/             # Astro hydration compiler; ships the directory/calculator
                        #   themes as package data under src/dsf_compiler/templates/
apps/                   # (reserved) FastAPI api + operator dashboard — Phase 8
data/                   # generated state stores + agent mock fixtures
scripts/                # standalone verification / fleet scripts
```

## Requirements

- Python ≥ 3.11
- [`uv`](https://docs.astral.sh/uv/) for workspace + dependency management

## Quickstart

```bash
# Resolve and install the whole workspace
uv sync

# Inspect the CLI
uv run seo-platform --help

# Initialise the storage engines, then check their status
uv run seo-platform db init
uv run seo-platform db status

# Show resolved configuration (secrets redacted)
uv run seo-platform config show

# Probe the Agent Bridge (mock mode by default)
uv run seo-platform agent ping --task schema_discovery

# End-to-end foundation smoke test
uv run python scripts/verify_foundation.py

# Tests
uv run pytest
```

## Configuration

Settings load from environment variables prefixed with `DSF_` and an optional
`.env` file. Copy `.env.example` to `.env` to customise. Key toggles:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DSF_EXECUTION_MODE` | `standalone` | `agent` if an orchestrating runtime is attached |
| `DSF_IS_PRODUCTION` | `false` | When false, the Agent Bridge always uses mocks |
| `DSF_AGENT_TRANSPORT` | `mock` | `mcp`, `stdio`, or `mock` |
| `DSF_MCP_SERVER_URL` | _unset_ | JSON-RPC/MCP endpoint (when transport is `mcp`) |

## License

Proprietary — all rights reserved.
