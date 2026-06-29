# datasiteforge-mcp

Exposes DataSiteForge as a **Model Context Protocol** server, so an orchestrating
agent (Claude Code, an MCP-driven runner, a local auto-loop) can drive the whole
revenue engine declaratively — the "agent's hands" from the architecture.

## Tools

| Tool | Maps to |
| --- | --- |
| `dsf_scout_niche(niche, live)` | `ScoutAgent.run` |
| `dsf_evaluate_opportunities(min_confidence, limit)` | `Evaluator.run` |
| `dsf_compile_site(evaluation_id, dataset)` | `SiteCompiler.compile` |
| `dsf_deploy_site(site_generation_id, dry_run)` | `CloudflareDeployer.deploy` |
| `dsf_optimize(deployment_id, reinforce, redeploy)` | `Optimizer.run` |
| `dsf_fleet_status()` | ledger state summary |

## Resources

| URI | Contents |
| --- | --- |
| `dsf://fleet/status` | counts across every lifecycle stage |
| `dsf://analytics/revenue` | revenue + traffic scorecard |
| `dsf://opportunities` | top arbitrage opportunities |
| `dsf://deployments` | recent deployments + live URLs |
| `dsf://logs/latest-errors` | recent FAILED rows across the ledger (for reflection) |

The tool functions in `dsf_mcp.tools` are pure (return JSON-safe dicts) and reuse
the same orchestrators as the CLI/API, so behaviour is identical across surfaces.

## Run

```
seo-platform mcp            # stdio MCP server
```
