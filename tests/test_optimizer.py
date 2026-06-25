"""Tests for the Phase 6-7 telemetry optimizer."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from dsf_core.config import reload_settings
from dsf_engine.models import (
    AnalyticsLog,
    Deployment,
    JobStatus,
    Optimization,
    SiteGeneration,
    TemplateType,
)
from dsf_engine.sqlite_engine import init_db, session_scope
from dsf_optimizer.optimizer import Optimizer
from dsf_optimizer.telemetry import (
    CloudflareWebAnalyticsSource,
    MockTelemetrySource,
    PageMetric,
)
from sqlmodel import select


def _seed_deployment(settings, build_dir: Path | None = None) -> int:
    """Insert a SiteGeneration (+ meta.json) and a COMPLETED Deployment."""
    init_db(settings)
    with session_scope(settings) as session:
        site = SiteGeneration(
            template_type=TemplateType.DIRECTORY,
            status=JobStatus.COMPLETED,
            build_path=str(build_dir) if build_dir else None,
        )
        session.add(site)
        session.flush()
        deployment = Deployment(
            site_generation_id=site.id,
            project_slug="demo-site",
            status=JobStatus.COMPLETED,
            live_url="https://demo-site.pages.dev",
        )
        session.add(deployment)
        session.flush()
        deployment_id = deployment.id
    assert deployment_id is not None
    return deployment_id


def _make_build(root: Path, *, title: str = "Original Title") -> Path:
    build_dir = root / "build"
    data_dir = build_dir / "src" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "meta.json").write_text(
        json.dumps({"title": title, "description": "old", "template_type": "directory"}),
        encoding="utf-8",
    )
    return build_dir


def test_page_metric_ctr() -> None:
    assert PageMetric(page_path="/", impressions=1000, clicks=5).ctr == 0.005
    assert PageMetric(page_path="/", impressions=0, clicks=0).ctr == 0.0


def test_mock_source_flags_underperformer(isolated_env: Path) -> None:
    settings = reload_settings()
    build = _make_build(isolated_env)
    deployment_id = _seed_deployment(settings, build)
    write_mock = None  # mock fixture comes from data/mocks committed; ensure present here
    (settings.mock_dir / "optimize_content.json").write_text(  # type: ignore[union-attr]
        json.dumps({"title": "New Better Title", "description": "fresh", "keywords": ["a", "b"]}),
        encoding="utf-8",
    )

    report = Optimizer(settings=settings).run(deployment_id)

    assert report.deployments_processed == 1
    assert report.pages_ingested == 2
    assert report.flagged == 1  # "/" only
    assert report.reinforced == 1
    outcome = report.outcomes[0]
    assert outcome.page_path == "/"
    assert outcome.action == "meta_rewrite"
    assert outcome.new_title == "New Better Title"

    # The hydration layer was rewritten in place.
    meta = json.loads((build / "src" / "data" / "meta.json").read_text())
    assert meta["title"] == "New Better Title"
    assert meta["optimized"] is True
    assert meta["optimized_keywords"] == ["a", "b"]

    # Telemetry + optimization rows were recorded.
    with session_scope(settings) as session:
        assert len(list(session.exec(select(AnalyticsLog)))) == 2
        opt = session.exec(select(Optimization)).one()
    assert opt.status == JobStatus.COMPLETED
    assert opt.page_path == "/"


def test_no_reinforce_only_ingests_and_flags(isolated_env: Path) -> None:
    settings = reload_settings()
    deployment_id = _seed_deployment(settings)

    report = Optimizer(settings=settings).run(deployment_id, reinforce=False)

    assert report.flagged == 1
    assert report.reinforced == 0
    assert report.outcomes == []
    with session_scope(settings) as session:
        assert list(session.exec(select(Optimization))) == []
        assert len(list(session.exec(select(AnalyticsLog)))) == 2


def test_reinforce_without_build_path_records_unavailable(isolated_env: Path) -> None:
    settings = reload_settings()
    deployment_id = _seed_deployment(settings, build_dir=None)
    (settings.mock_dir / "optimize_content.json").write_text(  # type: ignore[union-attr]
        json.dumps({"title": "T", "description": "D"}), encoding="utf-8"
    )

    report = Optimizer(settings=settings).run(deployment_id)

    assert report.reinforced == 1
    assert report.outcomes[0].action == "meta_unavailable"


def test_reinforce_agent_failure_is_isolated(isolated_env: Path) -> None:
    settings = reload_settings()
    build = _make_build(isolated_env)
    deployment_id = _seed_deployment(settings, build)
    # No optimize_content mock fixture -> bridge returns ok=False -> outcome FAILED.

    report = Optimizer(settings=settings).run(deployment_id)

    assert report.reinforced == 0
    assert report.outcomes[0].status == "FAILED"
    with session_scope(settings) as session:
        opt = session.exec(select(Optimization)).one()
    assert opt.status == JobStatus.FAILED


def test_min_impressions_threshold_excludes_low_traffic(isolated_env: Path) -> None:
    settings = reload_settings()
    deployment_id = _seed_deployment(settings)
    # Raise the floor above the mock landing page's impressions -> nothing flagged.
    report = Optimizer(settings=settings, min_impressions=100000).run(
        deployment_id, reinforce=False
    )
    assert report.flagged == 0


def test_cloudflare_source_parses_rum_groups() -> None:
    payload = {
        "data": {
            "viewer": {
                "accounts": [
                    {
                        "rumPageloadEventsAdaptiveGroups": [
                            {"count": 900, "sum": {"visits": 6}, "dimensions": {"requestPath": "/"}},
                            {"count": 120, "sum": {"visits": 30}, "dimensions": {"requestPath": "/x"}},
                        ]
                    }
                ]
            }
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.cloudflare.com"
        return httpx.Response(200, json=payload)

    from dsf_core.config import Settings

    settings = Settings(cloudflare_api_token="t", cloudflare_account_id="a")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    source = CloudflareWebAnalyticsSource(settings, client=client)
    metrics = source.fetch(Deployment(project_slug="x", id=1))
    client.close()

    assert [m.page_path for m in metrics] == ["/", "/x"]
    assert metrics[0].impressions == 900 and metrics[0].clicks == 6


def test_default_source_is_mock_without_credentials(isolated_env: Path) -> None:
    settings = reload_settings()
    optimizer = Optimizer(settings=settings)
    assert isinstance(optimizer.telemetry_source, MockTelemetrySource)
