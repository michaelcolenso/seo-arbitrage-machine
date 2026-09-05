# SEO Arbitrage Platform — Canonical Status

Last updated: 2026-09-04

## Canonical repository

**Repository:** `michaelcolenso/seo-arbitrage-machine`

This repository is now the integration target for the SEO Arbitrage Platform.
Other implementations are treated as source material, not parallel production systems.

## What survives from each predecessor

### DataSiteForge / seo-arbitrage-machine — production foundation
Keep and extend:
- SQLite orchestration ledger and additive migrations
- DuckDB dataset profiling/analytics
- Scout and Ahrefs keyword enrichment
- Evaluator + Agent Bridge
- Astro compiler/hydration
- Cloudflare deployment
- analytics optimizer
- FastAPI control plane
- MCP interface
- structured telemetry and failure isolation

### agentic-arbitrage — lifecycle intelligence
Port the useful concepts, not the duplicate stack:
- pain-signal discovery (Red Queen)
- explicit validation experiments (Midwife)
- evidence completeness / ready-to-fund gates
- portfolio promote/hold/cull decisions (Mortician)
- archive outcomes and learn from failures

Do not port:
- fabricated production metrics
- fixed thresholds disguised as universal truth
- duplicate storage/orchestration layers

### codex-seo-machine — editorial contracts
Port as deterministic factory gates:
- explicit search intent
- differentiation angle
- conversion path
- information gain
- claim/evidence support
- internal-link opportunities
- anti-repetition / anti-thin-content checks

Do not port:
- Phase-0 command stubs where working DataSiteForge components already exist

### OpportunityForge / Build What Pays — decision philosophy
This is the governing product logic:

`signal/data → expensive decision → buyer → revenue → product → SEO distribution`

The platform must reject traffic-only opportunities even when keyword economics look attractive.

## Canonical component map

| Concept | Canonical implementation | Status |
|---|---|---|
| Radar / radar-v2 | `packages/radar` | ACTIVE — new unified implementation |
| Dataset discovery / crawler | `packages/scout` + future source adapters | ACTIVE foundation; adapters to expand |
| Opportunity evaluation | `packages/engine` | ACTIVE; money-first contract to deepen |
| Factory / site build | `packages/compiler` | ACTIVE |
| Deployment | `packages/deployer` | ACTIVE |
| Portfolio learning | `packages/optimizer` | ACTIVE foundation; portfolio policy to deepen |
| API | `apps/api` | ACTIVE |
| MCP | `packages/mcp` | ACTIVE |
| 1M-keyword scan | `packages/radar` SQLite run ledger | IMPLEMENTED foundation; production run not yet executed |

## 1M-keyword scan contract

Every production scan must have a durable `run_id` and report:
- total expected
- processed
- promoted
- review
- rejected
- errors
- spend
- checkpoint
- started/completed timestamps
- top candidates

A keyword may reach `REVIEW` from SEO metrics alone. It may reach `PROMOTE` only after
buyer and business evidence are populated. `PROMOTE` means "advance to deep validation",
not "generate a site".

## Current branch

`codex/unified-seo-arbitrage-platform`

This branch establishes the canonical architecture and first-class Radar package.

## Next integration gates

1. Feed Radar `REVIEW` rows into an enrichment/resolution job that attaches buyer,
   decision, public-data sources and evidence.
2. Persist a unified Opportunity Graph across keyword signals, pain signals, datasets,
   buyers, decisions, monetization patterns and outcomes.
3. Enforce editorial/information-gain quality before compiler output can be deployed.
4. Connect verified Search Console/Cloudflare/conversion/revenue metrics to portfolio policy.
5. Run the production 1M-keyword scan and preserve the immutable run snapshot.
