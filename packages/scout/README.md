# datasiteforge-scout

Autonomous intelligence scout for **DataSiteForge** (Phase 2).

Provides:

- `dsf_scout.models` — the `ArbitrageOpportunity` scoring model and candidate schema.
- `dsf_scout.miner` — the `ArbitrageMiner`: economic leverage scoring + reflective filtering.
- `dsf_scout.sources` — pluggable candidate sources (`ManifestSource`, `OpenDataSource`).
- `dsf_scout.agent` — the `ScoutAgent` orchestrator: gather → enrich → score → persist.
- `dsf_scout.cli` — the `scout` command group (mounted under `seo-platform scout`).

## Candidate sources (run in parallel)

1. **Manifest** — a deterministic `data/manifest.json` of curated target datasets.
2. **Open-data discovery** — live CKAN-style portal search (e.g. data.gov), gated by
   configuration so tests and standalone runs stay offline by default.

All candidates flow into one pool, are enriched via the Agent Bridge (keyword
metrics / monetisation hints), scored by the miner, and the survivors are written
to the SQLite ledger as `arbitrage_opportunities` rows linked to a `ScoutJob`.

## Reflective filtering

Rejected candidates are never silently dropped: each rejection produces a
structured reason (`schema_invalid`, `keyword_difficulty_too_high`,
`uniqueness_below_threshold`) so an orchestrating agent can inspect and correct.
