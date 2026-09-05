# SEO Arbitrage Platform — Canonical Status

Last updated: 2026-09-04

## Canonical repository

**Repository:** `michaelcolenso/seo-arbitrage-machine`

This repository is the integration target for the SEO Arbitrage Platform. Other
implementations are source material, not parallel production systems.

## Governing product logic

`signal/data → expensive decision → buyer → revenue → product → SEO distribution`

Traffic is a discovery/distribution signal. It is not the business objective.

## Canonical component map

| Concept | Canonical implementation | Status |
|---|---|---|
| Radar / radar-v2 | `packages/scout/src/dsf_scout/radar` | ACTIVE — million-row reference run completed |
| Dataset discovery / crawler | `packages/scout` | ACTIVE foundation; source adapters to expand |
| Opportunity Graph | `packages/engine/src/dsf_engine/opportunity_graph.py` | ACTIVE |
| Opportunity evaluation | `packages/engine` | ACTIVE; money-first contract |
| Factory / site build | `packages/compiler` | ACTIVE; deterministic prebuild gate |
| Deployment | `packages/deployer` | ACTIVE |
| Acquisition/business evidence | `packages/optimizer/src/dsf_optimizer/evidence.py` | ACTIVE — GSC, Cloudflare, first-party events |
| Portfolio learning | `packages/optimizer` | ACTIVE; evidence-safe policy |
| API | `apps/api` | ACTIVE; protected `/telemetry` routes added |
| MCP | `packages/mcp` | ACTIVE |
| 1M-keyword scan | Radar SQLite run ledger | COMPLETED reference run + durable compact snapshot |

## Measured 1M reference run

Canonical run: `public-data-million-v1`

The universe is deterministic and exactly:

- 40 ranked public-data opportunity families
- 50 states
- 5 family-specific buyer roles
- 10 intent patterns
- 10 modifiers

= **1,000,000 keyword-shaped discovery signals**.

Reference workflow run `33946767199` executed the actual branch code against a real
temporary SQLite ledger and completed successfully.

| Metric | Result |
|---|---:|
| Processed | 1,000,000 |
| REVIEW | 612,730 |
| REJECT | 387,270 |
| PROMOTE | 0 |
| Errors | 0 |
| Paid keyword API spend | $0.00 |
| Checkpoint | 1,000,000 |
| Scan + resolve elapsed | 82.418 s |
| Opportunity clusters | 200 |
| Opportunity Graph nodes | 374 |
| Opportunity Graph edges | 800 |
| Initial paid-metric queue | 200 |

The compact immutable repository snapshot is:

`data/run_snapshots/public-data-million-v1.json`

The corresponding GitHub Actions artifact had SHA-256:

`c602379ec29c8c5333033a8245dc49bb54c24029ff50b38b7266d3fe3657848b`

### Evidence interpretation

The million-row universe deliberately uses deterministic ranking priors rather than
pretending they are provider measurements:

- `metrics_source=deterministic-prior:v1`
- `metrics_verified=false`
- `business_evidence_verified=false`

Generated priors can reach `REVIEW`; they cannot reach `PROMOTE`. An independent
reference execution caught and corrected a gate bug where populated catalog priors
were initially being treated as enrichment. Business scoring now requires explicitly
verified business evidence.

## Opportunity Graph / resolver

`REVIEW` keywords are collapsed into family × buyer opportunity clusters rather than
creating one research job per keyword.

The graph currently represents:

- opportunities
- datasets
- buyers
- expensive decisions
- product patterns
- verified keyword-metric evidence

Core relationships:

- `USES_DATASET`
- `SERVES_BUYER`
- `IMPROVES_DECISION`
- `PACKAGED_AS`
- `HAS_VERIFIED_KEYWORD_METRIC`

The full initial funnel creates 200 opportunity clusters and therefore at most 200
first-tranche provider metric checks, rather than hundreds of thousands of paid calls.

## Paid keyword verification

The existing Ahrefs v3 client is now connected to the cluster queue:

```bash
seo-platform radar verify-metrics --limit 25
```

Paid verification is explicit, not automatic. A verified provider metric replaces the
representative row's prior volume/CPC/KD and attaches metric evidence to the graph, but
the opportunity remains in `REVIEW` until its buyer/decision/source/monetization evidence
is separately verified.

## Production evidence / telemetry

The platform now keeps acquisition evidence separate from commercial outcomes.

### Acquisition

- Google Search Console: query/page/date impressions, clicks, CTR and position.
- Cloudflare: current GraphQL `httpRequestsAdaptiveGroups` path-level requests/visits.

### Commercial outcomes

First-party idempotent events are the source of truth:

- `LEAD`
- `CONVERSION`
- `REVENUE`

Revenue is never inferred from traffic analytics.

Protected control-plane routes:

- `POST /telemetry/sites`
- `POST /telemetry/events`
- `POST /telemetry/{site_key}/sync/gsc`
- `POST /telemetry/{site_key}/sync/cloudflare`
- `GET /telemetry/{site_key}/summary`

Live GSC/Cloudflare observations are not yet present in the repository ledger because
runtime credentials/site registrations are deployment-specific. The ingestion path and
first-party event ledger are implemented and tested.

## What survives from each predecessor

### DataSiteForge
- SQLite/DuckDB production plumbing
- Scout + Ahrefs enrichment
- Evaluator / Agent Bridge
- Astro compiler
- Cloudflare deployment
- optimizer
- FastAPI + MCP
- structured telemetry and failure isolation

### Agentic Arbitrage
- evidence completeness
- validation lifecycle
- portfolio promote/hold/cull concepts
- outcome learning

### Codex SEO Machine
- explicit quality contracts
- information-gain / differentiation principles
- anti-thin-content direction

### OpportunityForge / Build What Pays
- buyer/decision/revenue-first scoring philosophy
- kill weak ideas before overbuilding
- Opportunity Graph as the long-term moat

## Next integration gates

1. Verify the first tranche of the 200 cluster representatives with Ahrefs or another
   provider and rerank on measured demand/CPC/difficulty.
2. Build the business-evidence verifier that changes clusters from
   `NEEDS_BUSINESS_VERIFICATION` to promotion-eligible only when buyer, source,
   competition, monetization and expensive-decision claims are supported.
3. Register live products and ingest real GSC/Cloudflare + first-party outcome events.
4. Feed verified revenue/conversion evidence back into opportunity-family priors.
5. Extend factory QA with post-hydration information-gain, claim-support, internal-link
   and route-level thin-content checks.
