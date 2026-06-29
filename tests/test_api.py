"""Tests for the Phase 8 FastAPI control plane."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from dsf_api.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture()
def client(isolated_env: Path):
    # Inline jobs make background submissions deterministic (run synchronously).
    app = create_app(inline_jobs=True)
    with TestClient(app) as test_client:
        yield test_client


def _write_manifest(isolated_env: Path) -> None:
    manifest = isolated_env / "manifest.json"
    manifest.write_text(
        '{"candidates": [{"niche_id": "compliance_demo",'
        ' "target_dataset_url": "https://example.gov/d.csv",'
        ' "primary_keywords": ["compliance lookup"],'
        ' "estimated_monthly_volume": 45000, "average_cpc": 14.5,'
        ' "keyword_difficulty": 12, "data_sources_available": ["a","b","c"],'
        ' "monetization_vector": "LEAD_GEN", "estimated_lead_value": 175.0,'
        ' "uniqueness_potential_ratio": 0.82}]}',
        encoding="utf-8",
    )


def test_healthz(client) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_fleet_status_empty(client) -> None:
    resp = client.get("/fleet/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["counts"]["deployments"] == 0
    assert body["live_sites"] == []


def test_scout_run_job_succeeds_and_updates_fleet(client, isolated_env: Path) -> None:
    _write_manifest(isolated_env)

    resp = client.post("/scout/run", json={"niche": "compliance"})
    assert resp.status_code == 200
    job = resp.json()
    assert job["kind"] == "scout"

    # Inline jobs are terminal immediately.
    job_resp = client.get(f"/jobs/{job['job_id']}")
    assert job_resp.status_code == 200
    job_record = job_resp.json()
    assert job_record["status"] == "succeeded"
    assert job_record["result"]["status"] == "COMPLETED"
    assert job_record["result"]["accepted"]  # at least one opportunity accepted

    # Fleet now reflects the persisted opportunity.
    fleet = client.get("/fleet/status").json()
    assert fleet["counts"]["opportunities"] >= 1
    assert fleet["counts"]["scout_jobs"] >= 1


def test_full_pipeline_via_api(client, isolated_env: Path) -> None:
    _write_manifest(isolated_env)
    # The evaluator's Agent-Bridge "evaluate" task resolves this mock fixture.
    (isolated_env / "mocks" / "evaluate.json").write_text(
        '{"monetization_pattern": "local_lead_generation",'
        ' "architectural_layout": "directory", "confidence": 0.81,'
        ' "seo_keyword_layout": {"route_pattern": "/{city}",'
        ' "high_volume_columns": ["city"], "sample_routes": []}}',
        encoding="utf-8",
    )
    # dataset for compilation
    dataset = isolated_env / "data.csv"
    with dataset.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["company", "city", "penalty_usd"])
        writer.writerow(["Acme", "Austin", 1200])

    # scout -> evaluate -> compile -> deploy, all as (inline) jobs.
    client.post("/scout/run", json={"niche": "compliance"})
    ev = client.post("/evaluate/run", json={}).json()
    assert client.get(f"/jobs/{ev['job_id']}").json()["result"]["approved"] >= 1

    comp = client.post(
        "/compile/run", json={"evaluation_id": 1, "dataset": str(dataset)}
    ).json()
    comp_result = client.get(f"/jobs/{comp['job_id']}").json()["result"]
    assert comp_result["status"] == "COMPLETED"

    dep = client.post("/deploy/run", json={"site_generation_id": 1, "dry_run": True}).json()
    dep_result = client.get(f"/jobs/{dep['job_id']}").json()["result"]
    assert dep_result["status"] == "COMPLETED"
    assert dep_result["live_url"].endswith(".pages.dev")

    # Fleet + revenue endpoints reflect the deployed site.
    fleet = client.get("/fleet/status").json()
    assert len(fleet["live_sites"]) == 1
    revenue = client.get("/analytics/revenue").json()
    assert revenue["live_deployments"] >= 1


def test_unknown_job_404(client) -> None:
    assert client.get("/jobs/does-not-exist").status_code == 404


def test_api_token_enforced_when_set(isolated_env: Path, monkeypatch) -> None:
    from dsf_core.config import reload_settings

    monkeypatch.setenv("DSF_API_TOKEN", "s3cret")
    reload_settings()
    app = create_app(inline_jobs=True)
    with TestClient(app) as c:
        # Public surfaces stay open.
        assert c.get("/healthz").status_code == 200
        assert c.get("/").status_code == 200
        # Protected routes require the token.
        assert c.get("/fleet/status").status_code == 401
        assert c.post("/scout/run", json={"niche": "x"}).status_code == 401
        # Accepted via either header scheme.
        assert c.get("/fleet/status", headers={"Authorization": "Bearer s3cret"}).status_code == 200
        assert c.get("/fleet/status", headers={"X-API-Key": "s3cret"}).status_code == 200
        # Wrong token is rejected.
        assert c.get("/fleet/status", headers={"X-API-Key": "nope"}).status_code == 401


def test_api_open_when_token_unset(client) -> None:
    # The default fixture sets no DSF_API_TOKEN, so protected routes are open.
    assert client.get("/fleet/status").status_code == 200


def test_console_served_at_root(client) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "DataSiteForge" in resp.text
    assert "dsfConsole" in resp.text


def test_console_uses_only_self_hosted_assets(client) -> None:
    # The console handles the API token, so it must not load third-party scripts.
    html = client.get("/").text
    assert "cdn.tailwindcss.com" not in html
    assert "unpkg.com" not in html
    assert "/static/alpine.min.js" in html
    assert "/static/console.css" in html


def test_static_assets_public_even_under_auth(isolated_env: Path, monkeypatch) -> None:
    from dsf_core.config import reload_settings

    monkeypatch.setenv("DSF_API_TOKEN", "s3cret")
    reload_settings()
    app = create_app(inline_jobs=True)
    with TestClient(app) as c:
        assert c.get("/static/console.css").status_code == 200
        asset = c.get("/static/alpine.min.js")
        assert asset.status_code == 200
        assert len(asset.content) > 1000
