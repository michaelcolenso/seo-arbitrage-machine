"""Tests for the Ahrefs keyword-metrics enricher."""

from __future__ import annotations

from pathlib import Path

import httpx
from dsf_core.config import Settings
from dsf_scout.agent import ScoutAgent
from dsf_scout.ahrefs import AhrefsEnricher, _extract_rows
from dsf_scout.sources import ManifestSource


def _settings(isolated_env: Path, token: str | None) -> Settings:
    return Settings(
        ahrefs_api_token=token,
        data_dir=isolated_env,
        mock_dir=isolated_env / "mocks",
    )


def test_available_reflects_token(isolated_env: Path) -> None:
    assert AhrefsEnricher(_settings(isolated_env, None)).available() is False
    assert AhrefsEnricher(_settings(isolated_env, "tok")).available() is True


def test_extract_rows_shape_tolerant() -> None:
    row = {"keyword": "x", "volume": 10}
    assert _extract_rows({"keywords": [row]}) == [row]
    assert _extract_rows({"metrics": [row]}) == [row]
    assert _extract_rows([row]) == [row]
    assert _extract_rows({"nope": 1}) == []


def test_enrich_parses_overview(isolated_env: Path) -> None:
    payload = {
        "keywords": [
            {"keyword": "chemical data sheet lookup", "volume": 45000, "cpc": 1450, "difficulty": 12},
            {"keyword": "reach compliance", "volume": 8000, "cpc": 900, "difficulty": 30},
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3/keywords-explorer/overview"
        assert request.headers["authorization"] == "Bearer tok"
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    enricher = AhrefsEnricher(_settings(isolated_env, "tok"), client=client)
    out = enricher.enrich({"niche_id": "x", "primary_keywords": ["a", "b"]})
    client.close()

    # Highest-volume keyword is representative; cpc converted from cents.
    assert out["estimated_monthly_volume"] == 45000
    assert out["average_cpc"] == 14.5
    assert out["keyword_difficulty"] == 12


def test_enrich_no_keywords_returns_empty(isolated_env: Path) -> None:
    enricher = AhrefsEnricher(_settings(isolated_env, "tok"))
    assert enricher.enrich({"niche_id": "x", "primary_keywords": []}) == {}


def test_scout_agent_prefers_real_ahrefs_metrics(isolated_env: Path) -> None:
    # A manifest candidate has *estimated* metrics; real Ahrefs must override them.
    manifest = isolated_env / "manifest.json"
    manifest.write_text(
        '{"candidates": [{"niche_id": "demo",'
        ' "target_dataset_url": "https://example.gov/d.csv",'
        ' "primary_keywords": ["chemical data sheet lookup"],'
        ' "estimated_monthly_volume": 100, "average_cpc": 1.0,'
        ' "keyword_difficulty": 99, "data_sources_available": ["a","b","c"],'
        ' "monetization_vector": "LEAD_GEN", "estimated_lead_value": 175.0,'
        ' "uniqueness_potential_ratio": 0.82}]}',
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"keywords": [{"keyword": "chemical data sheet lookup",
                                "volume": 45000, "cpc": 1450, "difficulty": 12}]},
        )

    settings = _settings(isolated_env, "tok")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    enricher = AhrefsEnricher(settings, client=client)
    agent = ScoutAgent([ManifestSource(manifest)], settings=settings, enricher=enricher)

    report = agent.run("demo")
    client.close()

    assert report.status == "COMPLETED"
    opp = report.accepted[0]
    # Real Ahrefs values replaced the manifest's placeholder estimates.
    assert opp.estimated_monthly_volume == 45000
    assert opp.average_cpc == 14.5
    assert opp.keyword_difficulty == 12
