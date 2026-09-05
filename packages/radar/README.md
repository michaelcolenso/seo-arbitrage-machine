# DataSiteForge Radar

Radar is the high-volume discovery front end for the unified SEO Arbitrage Platform.
It is designed to scan 1,000,000+ keywords without turning keyword popularity into
a build decision.

## Two-stage funnel

1. **SCAN** — cheap deterministic scoring from volume, CPC, keyword difficulty and intent.
   Strong rows become `REVIEW`; weak rows are rejected before expensive enrichment.
2. **PROMOTE** — a candidate can become `PROMOTE` only after business evidence exists:
   a named buyer, decision value, monetization ease, defensibility, complexity,
   data leverage and evidence quality.

The final opportunity score deliberately weights business value above SEO metrics.
A high-volume keyword with no buyer stays in `REVIEW` and cannot reach the factory.

## 1M scan

Radar streams CSV input in batches and stores every scored row plus run counters in
SQLite. Runs are resumable: `(run_id, keyword)` is unique, so rerunning the same
input skips already-recorded keywords. Checkpoints, errors, spend and funnel counts
remain queryable while a scan is running.

Expected CSV columns:

- `keyword` (required)
- `volume` or `monthly_volume`
- `cpc`
- `kd` or `difficulty`
- `intent`
- optional enrichment: `buyer`, `decision_value`, `monetization_ease`,
  `defensibility`, `complexity`, `data_leverage`, `evidence_quality`, `source`

```bash
uv run seo-platform radar init
uv run seo-platform radar scan keywords.csv --name million-keyword-2026 --total 1000000
uv run seo-platform radar status
uv run seo-platform radar top --limit 25
```

## Decision contract

`PROMOTE` is a downstream privilege, not a keyword score. Promotion requires all
business dimensions plus a named buyer and minimum evidence gates. Website creation
happens only after a promoted opportunity passes deeper market validation.
