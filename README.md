# DataSiteForge (DSF)

An agent-native engine that transforms public datasets into hyper-optimized,
zero-hosting-cost, programmatic web applications (searchable B2B directories and
interactive calculators) and deploys them to Cloudflare Pages.

> **Status:** The full pipeline is built and **proven end-to-end** — a real run
> (`scout → evaluate → compile → deploy`) has published a live, multi-page
> Cloudflare Pages site. See [`HANDOFF.md`](HANDOFF.md) for what's production-real
> vs. mock, the roadmap, and known gaps.

## Architecture

DataSiteForge never hard-codes an LLM provider. Cognitive work (schema discovery,
monetisation evaluation, content reinforcement) is routed through an **Agent
Bridge** that speaks MCP / JSON-RPC over HTTP, exchanges newline-delimited frames
over stdio with an orchestrating agent (e.g. Claude Code), or falls back to
deterministic file-driven mocks when no runtime is attached.

Every stage records its state in a SQLite ledger (the "deterministic state
ledger"), and every orchestrator returns a structured, MCP-friendly report so the
same logic drives the CLI, the REST API, and the MCP server identically.

## The pipeline

```
scout → evaluate → compile → deploy → optimize
```

| Stage | Package | What it does | CLI |
| --- | --- | --- | --- |
| Scout | `packages/scout` | Discover + score arbitrage niches (manifest + live CKAN) | `scout run/list/sources` |
| Evaluate | `packages/engine` | Monetisation pattern + template + SEO routing verdict | `evaluate run/list` |
| Compile | `packages/compiler` | DuckDB rows → routed Astro build (sitemap, robots, JSON-LD) | `compile run/list` |
| Deploy | `packages/deployer` | Cloudflare Pages (dry-run, or live via wrangler) | `deploy run/list` |
| Optimize | `packages/optimizer` | Telemetry → flag weak pages → Agent-Bridge rewrite → redeploy | `optimize run/list` |

## Monorepo layout

```
pyproject.toml          # root uv workspace
packages/
  core/                 # settings, telemetry, Agent Bridge, the seo-platform CLI
  engine/               # SQLModel state ledger + thread-safe DuckDB broker + evaluator
  scout/                # arbitrage miner + multi-source candidate discovery
  compiler/             # Astro hydration compiler; ships directory/calculator themes
                        #   as package data under src/dsf_compiler/templates/
  deployer/             # zero-cost Cloudflare Pages deployment (REST + wrangler)
  optimizer/            # traffic telemetry ingestion + reinforcement loops
  mcp/                  # MCP server: dsf_* tools + dsf:// resources for agent runners
apps/
  api/                  # FastAPI control plane + operator console (seo-platform serve)
data/                   # generated state stores + agent mock fixtures + seed manifest
tests/                  # pytest suite (unit + gated live integration tests)
```

## Requirements

- Python ≥ 3.11 and [`uv`](https://docs.astral.sh/uv/)
- Node ≥ 18 (only for `--build` / live deploys — Astro + wrangler)

## Quickstart

```bash
uv sync                                   # install the whole workspace
uv run seo-platform --help                # discover commands
uv run seo-platform db init               # create the SQLite + DuckDB stores

# Run the pipeline (mock-safe: no external services, no credentials)
uv run seo-platform scout run --niche compliance
uv run seo-platform evaluate run
uv run seo-platform compile run --evaluation-id 1 --dataset data/sample/compliance_sample.csv
uv run seo-platform deploy run --site-generation-id 1        # dry-run without creds

# Control plane + operator console  →  http://127.0.0.1:8000
uv run seo-platform serve

# MCP server (stdio) for an orchestrating agent
uv run seo-platform mcp
```

## Tests

```bash
uv run pytest                     # default suite (offline, hermetic)
uv run pytest -m live --run-live  # live integration tests (real CKAN portals)
```

CI (`.github/workflows/ci.yml`) runs `uv sync --frozen` + `uv run pytest` on every PR.

## Live deploy (real Cloudflare Pages)

Provide a Cloudflare API token with **Account → Cloudflare Pages → Edit**. Both
the standard wrangler names and the `DSF_`-prefixed names are accepted:

```bash
export CLOUDFLARE_API_TOKEN=...      # or DSF_CLOUDFLARE_API_TOKEN
export CLOUDFLARE_ACCOUNT_ID=...     # or DSF_CLOUDFLARE_ACCOUNT_ID
uv run seo-platform deploy run --site-generation-id 1 --build --live
```

With credentials present the deployer builds `dist/` and pushes it via `wrangler`,
returning the live `*.pages.dev` URL (recorded in the ledger). Without them it
runs in dry-run mode.

## Configuration

Settings load from `DSF_`-prefixed environment variables and an optional `.env`
(see `.env.example`). Key toggles:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DSF_EXECUTION_MODE` | `standalone` | `agent` if an orchestrating runtime is attached |
| `DSF_IS_PRODUCTION` | `false` | When false, the Agent Bridge always uses mocks |
| `DSF_AGENT_TRANSPORT` | `mock` | `mcp`, `stdio`, or `mock` |
| `DSF_MCP_SERVER_URL` | _unset_ | JSON-RPC/MCP endpoint (when transport is `mcp`) |
| `DSF_API_TOKEN` | _unset_ | When set, the control-plane API requires this token |
| `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` | _unset_ | Live Cloudflare Pages deploy |

## License

Proprietary — all rights reserved.
