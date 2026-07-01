# DataSiteForge — Handoff

A candid map of what exists, what's real vs. mock, how to run it, and what's left
to turn it into a business. Read this before picking the project back up.

## 1. What it is

DataSiteForge discovers public/structured datasets, decides how to monetise them,
compiles them into routed static **Astro** sites (searchable directories or
parametric calculators), and deploys them to **Cloudflare Pages** at zero hosting
cost. Cognitive steps go through an **Agent Bridge** (MCP / stdio / mock). All
state lives in a SQLite ledger; every orchestrator returns a structured report,
so the CLI, REST API, and MCP server share identical logic.

## 2. Pipeline & entry points

```
scout → evaluate → compile → deploy → optimize
```

- **CLI:** `seo-platform <scout|evaluate|compile|deploy|optimize|db|config|agent|serve|mcp>`
- **REST API + console:** `seo-platform serve` (FastAPI, `apps/api`)
- **MCP server (stdio):** `seo-platform mcp` — tools `dsf_scout_niche`,
  `dsf_evaluate_opportunities`, `dsf_compile_site`, `dsf_deploy_site`,
  `dsf_optimize`, `dsf_fleet_status`; resources under `dsf://…`.

## 3. What's REAL vs. MOCK (read this carefully)

| Capability | Status | Notes |
| --- | --- | --- |
| Cloudflare Pages deploy | ✅ **Real, proven** | A live 13-URL routed site was deployed end-to-end and verified (200s, sitemap, canonical, JSON-LD), then torn down. Uses `wrangler` + REST. |
| Compiler / per-route SEO fleet | ✅ **Real** | Real `astro build`; flat-file routing (no trailing-slash redirects), sitemap.xml, robots.txt, JSON-LD, canonical. |
| Scout live open-data (CKAN) | ✅ **Real** | Works against real CKAN portals (`data.gov.uk` etc.). ⚠️ `catalog.data.gov`'s action API returns 404 to bots — pass a working `--portal`. |
| SQLite ledger + DuckDB | ✅ **Real** | Additive migrations; thread-safe DuckDB broker over CSV/JSON/Parquet. |
| API auth, durable jobs, CI | ✅ **Real** | Token-gated API; jobs persisted + restart-recoverable; CI runs the suite on every PR. |
| Agent Bridge cognitive tasks | 🟡 **Mock by default** | `evaluate`, `schema_discovery`, `optimize_content` read file fixtures unless a real MCP/stdio agent runtime is attached. The *evaluation logic itself has never run against a real model.* |
| Telemetry / analytics | 🟡 **Mock by default** | `MockTelemetrySource` returns synthetic metrics. A `CloudflareWebAnalyticsSource` (GraphQL RUM) exists; an **Ahrefs/GSC MCP** is also available to feed real numbers, but a fresh `.pages.dev` has no search data until indexed. |
| Revenue / lead capture | ❌ **Not built** | The lead-gen form posts to a webhook with **no backend**. `revenue_cents` is only ever written by the mock telemetry source. There is no money path yet. |
| Autonomous supervisor + cost guardrails | ❌ **Not built** | No perpetual `while True` driver, no `check_cloud_budgets()`. Each stage is invoked manually / via API. |

## 4. Credentials & config

`DSF_`-prefixed env vars or `.env` (see `.env.example`). For a live deploy set a
Cloudflare API token (**Account → Cloudflare Pages → Edit**) as
`CLOUDFLARE_API_TOKEN` (or `DSF_CLOUDFLARE_API_TOKEN`); `CLOUDFLARE_ACCOUNT_ID` is
also read. Never commit secrets.

## 5. How to run

```bash
uv sync
uv run pytest                          # 97 passing, 2 live-skipped
uv run pytest -m live --run-live       # real CKAN integration
uv run seo-platform db init
# scout → evaluate → compile → deploy (dry-run without creds; --build --live with them)
```

A real deploy round-trip (verified): compile a dataset with geo + category
columns → `deploy run --site-generation-id N --build --live` → live
`https://<slug>.pages.dev` with one page per `/{col1}/{col2}` combination.

## 6. Roadmap status

- **Milestone A — hardening:** ✅ CI · ✅ API auth · ✅ durable jobs · ✅ live integration tests
- **Milestone B — first real deploy:** ✅ done (deploy proven; analytics half still mock until a site has traffic)
- **Milestone C — revenue:** ❌ lead capture/store/forward backend + real `revenue_cents`
- **Milestone D — autonomy & safety:** ❌ supervisor loop, cost guardrails, resume-from-ledger boot
- **Milestone E — content quality & scale:** ❌ enforce anti-thin-content/uniqueness at compile, internal linking, dataset-refresh cadence, pagination

## 7. Known gaps / risks

- **No revenue path** — the business model (sell leads) is unimplemented.
- **Agent Bridge unproven in production** — all cognitive output is mock fixtures.
- **Thin-content risk** — the ≥60% uniqueness rule is scored by the miner but not
  enforced at compile; low-row routes can still generate (Milestone E).
- **Legal/ToS** — dataset licensing, CAN-SPAM (sold leads), and search-engine
  guidelines all need review before operating for real.
- **`catalog.data.gov`** action API 404s for automated clients; use another CKAN host.

## 8. Repo conventions

- `uv` workspace; each phase is its own package. Python 3.11, ruff, pytest.
- Tests are hermetic (`isolated_env` clears ambient credentials). Live tests are
  gated behind `-m live --run-live`.
- Templates in `packages/compiler/.../templates/` are **fixed invariants** — the
  compiler only ever writes the JSON hydration layer (`src/data/*.json`).
