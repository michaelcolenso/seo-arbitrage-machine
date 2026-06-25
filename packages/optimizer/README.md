# datasiteforge-optimizer

Traffic telemetry and automated reinforcement loops for **DataSiteForge** (Phases 6–7).

This closes the autonomous self-correction loop:

1. **Ingest** edge interaction data (Cloudflare Web Analytics, or a deterministic
   mock source) into the `analytics_logs` ledger.
2. **Analyse** per-page click-through: flag pages with high impressions but weak
   CTR (the structural underperformers).
3. **Reinforce**: send each anomaly through the Agent Bridge (`optimize_content`),
   apply the returned meta rewrite to the site's hydration layer
   (`src/data/meta.json`), record an `Optimization` row, and optionally trigger a
   silent rebuild + redeploy via the Phase 5 deployer.

Mirroring the platform's mock-first ethos, telemetry defaults to a deterministic
mock source unless Cloudflare credentials are configured, and reinforcement runs
through the Agent Bridge's mock fallback — so the whole loop runs end-to-end with
no external services. Every failure is isolated into a structured report.

## CLI

```
seo-platform optimize run [--deployment-id <id>] [--reinforce/--no-reinforce] \
    [--redeploy] [--min-impressions N] [--max-ctr 0.02]
seo-platform optimize list
```
