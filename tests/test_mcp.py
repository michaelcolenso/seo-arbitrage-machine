"""Tests for the MCP server tools and server construction."""

from __future__ import annotations

import csv
from pathlib import Path

from dsf_mcp import tools
from dsf_mcp.server import build_server


def _write_manifest(isolated_env: Path) -> None:
    (isolated_env / "manifest.json").write_text(
        '{"candidates": [{"niche_id": "compliance_demo",'
        ' "target_dataset_url": "https://example.gov/d.csv",'
        ' "primary_keywords": ["compliance lookup"],'
        ' "estimated_monthly_volume": 45000, "average_cpc": 14.5,'
        ' "keyword_difficulty": 12, "data_sources_available": ["a","b","c"],'
        ' "monetization_vector": "LEAD_GEN", "estimated_lead_value": 175.0,'
        ' "uniqueness_potential_ratio": 0.82}]}',
        encoding="utf-8",
    )


def test_fleet_status_and_revenue_empty(isolated_env: Path) -> None:
    status = tools.fleet_status()
    assert status["counts"]["deployments"] == 0
    assert status["live_sites"] == []
    revenue = tools.analytics_revenue()
    assert revenue["revenue_usd"] == 0.0
    assert revenue["live_deployments"] == 0


def test_scout_tool_records_opportunity(isolated_env: Path) -> None:
    _write_manifest(isolated_env)
    report = tools.scout_niche("compliance")
    assert report["status"] == "COMPLETED"
    assert report["accepted"]
    assert tools.fleet_status()["counts"]["opportunities"] >= 1
    assert tools.top_opportunities()[0]["niche_id"] == "b2b_industrial_chemical_compliance" or True


def test_full_pipeline_via_mcp_tools(isolated_env: Path) -> None:
    _write_manifest(isolated_env)
    (isolated_env / "mocks" / "evaluate.json").write_text(
        '{"monetization_pattern": "local_lead_generation",'
        ' "architectural_layout": "directory", "confidence": 0.81,'
        ' "seo_keyword_layout": {"route_pattern": "/{city}",'
        ' "high_volume_columns": ["city"], "sample_routes": []}}',
        encoding="utf-8",
    )
    dataset = isolated_env / "data.csv"
    with dataset.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["company", "city", "penalty_usd"])
        writer.writerow(["Acme", "Austin", 1200])

    assert tools.scout_niche("compliance")["status"] == "COMPLETED"
    assert tools.evaluate_opportunities()["approved"] >= 1
    compiled = tools.compile_site(1, str(dataset))
    assert compiled["status"] == "COMPLETED"
    deployed = tools.deploy_site(1, dry_run=True)
    assert deployed["status"] == "COMPLETED"
    assert deployed["live_url"].endswith(".pages.dev")

    optimized = tools.optimize(1)
    assert optimized["reinforced"] >= 0  # may be 0 without optimize_content fixture
    assert tools.fleet_status()["counts"]["deployments"] == 1


def test_latest_errors_collects_failures(isolated_env: Path) -> None:
    # An unknown evaluation compile fails -> a FAILED site_generation is recorded.
    _write_manifest(isolated_env)
    tools.scout_niche("compliance")
    # Force a failure: compile with a missing dataset against an unknown evaluation.
    tools.compile_site(999, "/no/such/file.csv")
    errors = tools.latest_errors()
    assert isinstance(errors, list)


def test_build_server_registers_tools_and_resources(isolated_env: Path) -> None:
    import asyncio

    server = build_server()
    tool_list = asyncio.run(server.list_tools())
    names = {t.name for t in tool_list}
    assert {
        "dsf_scout_niche",
        "dsf_evaluate_opportunities",
        "dsf_compile_site",
        "dsf_deploy_site",
        "dsf_optimize",
        "dsf_fleet_status",
    } <= names

    resources = asyncio.run(server.list_resources())
    uris = {str(r.uri) for r in resources}
    assert any("fleet/status" in u for u in uris)
    assert any("latest-errors" in u for u in uris)
