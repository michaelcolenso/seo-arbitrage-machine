# Opportunity Graph, Million Scan, and Evidence Loop

## The invariant

The platform has four evidence levels. Never collapse them.

1. **Generated discovery prior** — cheap ranking signal for a huge universe.
2. **Verified keyword metric** — provider-measured demand/CPC/difficulty.
3. **Verified business evidence** — buyer, expensive decision, source feasibility, monetization and competition evidence.
4. **Observed outcome** — production Search Console/Cloudflare behavior plus first-party leads, conversions and revenue.

Only levels 2 + 3 can create a `PROMOTE` candidate. Level 4 changes portfolio policy after launch.

## First million-row pass

```bash
seo-platform radar million --name public-data-million-v1
```

The canonical universe is exactly:

- 40 public-data opportunity families
- 50 states
- 5 family-specific buyer roles
- 10 intent patterns
- 10 modifiers

= **1,000,000 keyword-shaped discovery signals**.

The generated `volume`, `cpc` and `kd` values are deterministic priors for ordering work. They are tagged:

```text
metrics_source=deterministic-prior:v1
metrics_verified=false
business_evidence_verified=false
```

They can reach `REVIEW`; they cannot reach `PROMOTE`.

## Resolver

The default million command resolves a completed run automatically. It groups keyword evidence into:

```text
opportunity family × buyer
```

rather than creating one research job per keyword.

The Opportunity Graph stores:

```text
Opportunity --USES_DATASET--> Dataset
Opportunity --SERVES_BUYER--> Buyer
Opportunity --IMPROVES_DECISION--> Decision
Opportunity --PACKAGED_AS--> Product Pattern
Opportunity --HAS_VERIFIED_KEYWORD_METRIC--> Provider Metric
```

Inspect:

```bash
seo-platform radar clusters public-data-million-v1 --limit 25
```

## Paid metric escalation

Resolver queues one representative term per opportunity cluster. Ahrefs calls are deliberately **not** automatic during the million-row pass.

```bash
DSF_AHREFS_API_TOKEN=... seo-platform radar verify-metrics --limit 25
```

A verified Ahrefs result:

- replaces the representative row's prior volume/CPC/KD
- sets `metrics_source=ahrefs:v3`
- sets `metrics_verified=true`
- rescoring still leaves the opportunity in REVIEW while business evidence is unverified
- adds a metric-evidence node/edge to the Opportunity Graph

This creates an explicit cost control: increase `--limit` only when the next tranche deserves paid validation.

## Production evidence

Register each live product once:

```http
POST /telemetry/sites
{
  "site_key": "buildingseattle",
  "domain": "buildingseattle.com",
  "gsc_property": "sc-domain:buildingseattle.com",
  "cloudflare_zone_id": "...",
  "opportunity_node_id": 123
}
```

### Search Console

Runtime secret:

```text
DSF_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN
```

Sync:

```http
POST /telemetry/buildingseattle/sync/gsc
{"start_date":"2026-08-01","end_date":"2026-08-31"}
```

The access token is never written to SQLite. Stored observations contain date, page, query, clicks, impressions and returned CTR/position metadata.

### Cloudflare

Runtime secret:

```text
DSF_CLOUDFLARE_API_TOKEN
```

Sync:

```http
POST /telemetry/buildingseattle/sync/cloudflare
{"start_date":"2026-08-01","end_date":"2026-08-31"}
```

Path-level HTTP evidence is queried from Cloudflare GraphQL `httpRequestsAdaptiveGroups`. The ledger stores requests, visits and sample metadata.

## First-party business events

Traffic tools are not the revenue ledger. The product/backend sends server-to-server events to the protected control plane:

```http
POST /telemetry/events
{
  "event_id":"stripe-pi_123-revenue",
  "site_key":"buildingseattle",
  "event_type":"REVENUE",
  "occurred_at":"2026-09-04T18:00:00Z",
  "lead_key":"lead-abc",
  "value_cents":9900,
  "currency":"USD"
}
```

Allowed types:

- `LEAD`
- `CONVERSION`
- `REVENUE`

`event_id` is globally unique and ingestion is idempotent, making webhook retries safe.

## Learning hierarchy

Portfolio decisions should prioritize evidence in this order:

1. verified revenue
2. verified conversions
3. qualified leads
4. Search Console organic clicks and query growth
5. Cloudflare visits/requests
6. impressions
7. pre-launch scores

A high-traffic product with no commercial outcome should not outrank a lower-traffic B2B product producing real revenue.

## Reference-run reproducibility

PR changes to Radar execute `.github/workflows/million-scan-reference.yml`.

The job:

1. installs the frozen uv workspace
2. executes all 1,000,000 rows against a temporary real SQLite ledger
3. resolves REVIEW signals into Opportunity Graph clusters
4. writes `public-data-million-v1.json`
5. uploads only that compact snapshot, not the large transient database

This gives each material Radar change an auditable million-row behavior snapshot without bloating the repository.
