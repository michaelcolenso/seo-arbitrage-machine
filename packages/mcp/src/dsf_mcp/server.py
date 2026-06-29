"""The DataSiteForge MCP server.

Registers the lifecycle as MCP **tools** (actions the agent invokes) and exposes
ledger state as MCP **resources** (URIs the agent reads).  All logic lives in
:mod:`dsf_mcp.tools`; this module is the thin protocol surface.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import tools


def build_server() -> FastMCP:
    """Construct and return the configured FastMCP server."""
    server = FastMCP("datasiteforge")

    # -- tools ------------------------------------------------------------

    @server.tool()
    def dsf_scout_niche(niche: str, live: bool = False) -> dict[str, Any]:
        """Discover and score arbitrage opportunities for a seed niche."""
        return tools.scout_niche(niche, live=live)

    @server.tool()
    def dsf_evaluate_opportunities(
        min_confidence: float = 0.5, limit: int | None = None
    ) -> dict[str, Any]:
        """Evaluate pending opportunities into APPROVED/REJECTED verdicts."""
        return tools.evaluate_opportunities(min_confidence=min_confidence, limit=limit)

    @server.tool()
    def dsf_compile_site(evaluation_id: int, dataset: str, build: bool = False) -> dict[str, Any]:
        """Hydrate an approved evaluation into an Astro site build."""
        return tools.compile_site(evaluation_id, dataset, build=build)

    @server.tool()
    def dsf_deploy_site(
        site_generation_id: int, dry_run: bool | None = None, build: bool = False
    ) -> dict[str, Any]:
        """Deploy a completed site generation to Cloudflare Pages."""
        return tools.deploy_site(site_generation_id, dry_run=dry_run, build=build)

    @server.tool()
    def dsf_optimize(
        deployment_id: int | None = None, reinforce: bool = True, redeploy: bool = False
    ) -> dict[str, Any]:
        """Ingest telemetry and run the reinforcement loop over deployed sites."""
        return tools.optimize(deployment_id, reinforce=reinforce, redeploy=redeploy)

    @server.tool()
    def dsf_fleet_status() -> dict[str, Any]:
        """Summarise ledger state across every lifecycle stage."""
        return tools.fleet_status()

    # -- resources --------------------------------------------------------

    @server.resource("dsf://fleet/status")
    def fleet_status_resource() -> str:
        return json.dumps(tools.fleet_status(), indent=2)

    @server.resource("dsf://analytics/revenue")
    def revenue_resource() -> str:
        return json.dumps(tools.analytics_revenue(), indent=2)

    @server.resource("dsf://opportunities")
    def opportunities_resource() -> str:
        return json.dumps(tools.top_opportunities(), indent=2)

    @server.resource("dsf://deployments")
    def deployments_resource() -> str:
        return json.dumps(tools.recent_deployments(), indent=2)

    @server.resource("dsf://logs/latest-errors")
    def latest_errors_resource() -> str:
        return json.dumps(tools.latest_errors(), indent=2)

    return server


def main() -> None:  # pragma: no cover - process entry point
    """Run the MCP server over stdio."""
    build_server().run()


if __name__ == "__main__":  # pragma: no cover
    main()
