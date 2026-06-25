# datasiteforge-deployer

Zero-cost **Cloudflare Pages** deployment for **DataSiteForge** (Phase 5).

Consumes a `COMPLETED` `SiteGeneration`, ensures its production assets are built,
pushes them to Cloudflare Pages, and records a `Deployment` row (with the live
`*.pages.dev` URL) in the ledger.

## Modes

The deployer mirrors the platform's mock-first ethos:

- **Dry-run** (default when not in production or with no Cloudflare credentials):
  simulates the deployment, synthesises the canonical `https://<slug>.pages.dev`
  URL, and records a `Deployment` — so the full pipeline runs end-to-end without
  real credentials.
- **Live**: ensures the Pages project exists via the Cloudflare REST API (httpx),
  then performs a direct-upload deployment of `dist/` via `wrangler`. Returns the
  live URL to the state ledger.

Every failure is caught and returned as a structured `DeployReport`
(`AGENT_ACTION_REQUIRED`) with the `Deployment` row marked `FAILED` — the
deployer never raises into caller code.

## CLI

```
seo-platform deploy run --site-generation-id <id> [--build] [--dry-run/--no-dry-run]
seo-platform deploy list
```
