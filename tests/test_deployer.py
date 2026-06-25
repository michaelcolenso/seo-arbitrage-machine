"""Tests for the Phase 5 Cloudflare deployer."""

from __future__ import annotations

from pathlib import Path

import httpx
from dsf_core.config import Settings, reload_settings
from dsf_deployer.cloudflare import CloudflareDeployer, _slugify
from dsf_engine.models import (
    ArbitrageOpportunity,
    Deployment,
    Evaluation,
    EvaluationVerdict,
    JobStatus,
    MonetizationPattern,
    SiteGeneration,
    TemplateType,
)
from dsf_engine.sqlite_engine import init_db, session_scope
from sqlmodel import select


def _seed_site(settings, *, status: JobStatus = JobStatus.COMPLETED, build_path: str | None = "/x") -> int:
    """Insert opportunity -> evaluation -> site_generation; return the site id."""
    init_db(settings)
    with session_scope(settings) as session:
        opp = ArbitrageOpportunity(
            niche_id="b2b_industrial_chemical_compliance",
            target_dataset_url="https://example.gov/data.csv",
        )
        session.add(opp)
        session.flush()
        evaluation = Evaluation(
            opportunity_id=opp.id,
            monetization_pattern=MonetizationPattern.LOCAL_LEAD_GENERATION,
            template_type=TemplateType.DIRECTORY,
            verdict=EvaluationVerdict.APPROVED,
        )
        session.add(evaluation)
        session.flush()
        site = SiteGeneration(
            evaluation_id=evaluation.id,
            template_type=TemplateType.DIRECTORY,
            status=status,
            build_path=build_path,
        )
        session.add(site)
        session.flush()
        site_id = site.id
    assert site_id is not None
    return site_id


def test_slugify_is_cloudflare_safe() -> None:
    assert _slugify("B2B Industrial: Chemical Compliance!") == "b2b-industrial-chemical-compliance"
    assert _slugify("---") == "dsf-site"
    assert len(_slugify("x" * 100)) <= 58


def test_dry_run_deploy_records_synthetic_url(isolated_env: Path) -> None:
    settings = reload_settings()
    # build_path must exist for the dry-run (dist may be absent).
    build_dir = isolated_env / "site"
    build_dir.mkdir()
    site_id = _seed_site(settings, build_path=str(build_dir))

    report = CloudflareDeployer(settings=settings).deploy(site_id, dry_run=True)

    assert report.status == "COMPLETED"
    assert report.mode == "dry_run"
    assert report.live_url == "https://b2b-industrial-chemical-compliance.pages.dev"
    with session_scope(settings) as session:
        dep = session.exec(select(Deployment)).one()
    assert dep.status == JobStatus.COMPLETED
    assert dep.site_generation_id == site_id
    assert dep.live_url == report.live_url


def test_deploy_rejects_uncompiled_site(isolated_env: Path) -> None:
    settings = reload_settings()
    site_id = _seed_site(settings, status=JobStatus.RUNNING)

    report = CloudflareDeployer(settings=settings).deploy(site_id, dry_run=True)

    assert report.status == "REJECTED"
    assert report.deployment_id is None
    with session_scope(settings) as session:
        assert list(session.exec(select(Deployment))) == []


def test_deploy_unknown_site(isolated_env: Path) -> None:
    settings = reload_settings()
    init_db(settings)
    report = CloudflareDeployer(settings=settings).deploy(999, dry_run=True)
    assert report.status == "AGENT_ACTION_REQUIRED"
    assert report.error_type == "SiteGenerationNotFound"


def test_missing_build_path_reflects_and_fails(isolated_env: Path) -> None:
    settings = reload_settings()
    site_id = _seed_site(settings, build_path=str(isolated_env / "does-not-exist"))

    report = CloudflareDeployer(settings=settings).deploy(site_id, dry_run=True)

    assert report.status == "AGENT_ACTION_REQUIRED"
    assert report.error_type == "CloudflareError"
    with session_scope(settings) as session:
        dep = session.exec(select(Deployment)).one()
    assert dep.status == JobStatus.FAILED
    assert dep.log_trace is not None


def _live_settings(isolated_env: Path) -> Settings:
    return Settings(
        cloudflare_api_token="tok",
        cloudflare_account_id="acct",
        data_dir=isolated_env,
        mock_dir=isolated_env / "mocks",
    )


def test_live_deploy_creates_project_and_uploads(isolated_env: Path) -> None:
    settings = _live_settings(isolated_env)
    site_id = _seed_site(settings, build_path=str(_make_built_site(isolated_env)))

    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(404, json={"success": False, "result": None})
        # POST create project
        return httpx.Response(
            200,
            json={"success": True, "result": {"id": "proj_123", "subdomain": "my-site.pages.dev"}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    # Stub wrangler so no real upload happens.
    deployer = CloudflareDeployer(
        settings=settings,
        client=client,
        wrangler_runner=lambda dist, slug: ("dep_abc", "https://preview.my-site.pages.dev"),
    )
    report = deployer.deploy(site_id, dry_run=False)
    client.close()

    assert report.status == "COMPLETED"
    assert report.mode == "live"
    assert report.live_url == "https://my-site.pages.dev"  # canonical project subdomain
    # GET (probe) then POST (create) were issued.
    assert ("GET", "/client/v4/accounts/acct/pages/projects/b2b-industrial-chemical-compliance") in requests
    assert any(m == "POST" for m, _ in requests)
    with session_scope(settings) as session:
        dep = session.exec(select(Deployment)).one()
    assert dep.cloudflare_project_id == "proj_123"
    assert dep.status == JobStatus.COMPLETED


def test_live_deploy_requires_dist(isolated_env: Path) -> None:
    settings = _live_settings(isolated_env)
    # build dir exists but has no dist/ and run_build is False -> failure.
    build_dir = isolated_env / "nodist"
    build_dir.mkdir()
    site_id = _seed_site(settings, build_path=str(build_dir))

    report = CloudflareDeployer(settings=settings).deploy(site_id, dry_run=False)

    assert report.status == "AGENT_ACTION_REQUIRED"
    assert report.error_type == "CloudflareError"
    assert "dist/" in (report.message or "")


def _make_built_site(root: Path) -> Path:
    build_dir = root / "built-site"
    (build_dir / "dist").mkdir(parents=True)
    (build_dir / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
    return build_dir
