"""Pure tool functions backing the MCP server.

Each function reuses the same orchestrators as the CLI and API and returns a
JSON-safe ``dict`` — keeping them free of MCP runtime types makes them directly
unit-testable and guarantees identical behaviour across every surface.
"""

from __future__ import annotations

from typing import Any

from dsf_core.config import get_settings
from dsf_engine.models import (
    AnalyticsLog,
    ArbitrageOpportunity,
    Deployment,
    Evaluation,
    JobStatus,
    Optimization,
    ScoutJob,
    SiteGeneration,
)
from dsf_engine.sqlite_engine import init_db, session_scope
from sqlalchemy import func
from sqlmodel import select


def _dump(report: Any) -> dict[str, Any]:
    return report.model_dump(mode="json")


# -- lifecycle tools -------------------------------------------------------


def scout_niche(niche: str, live: bool = False) -> dict[str, Any]:
    """Run a scouting pass for ``niche`` (manifest + optional live open-data)."""
    from dsf_scout.agent import ScoutAgent
    from dsf_scout.sources import ManifestSource, OpenDataSource

    settings = get_settings()
    assert settings.data_dir is not None
    sources: list[Any] = [ManifestSource(settings.data_dir / "manifest.json")]
    if live:
        sources.append(OpenDataSource())
    return _dump(ScoutAgent(sources, settings=settings).run(niche))


def evaluate_opportunities(min_confidence: float = 0.5, limit: int | None = None) -> dict[str, Any]:
    """Evaluate pending opportunities into APPROVED/REJECTED verdicts."""
    from dsf_engine.evaluator import Evaluator

    return _dump(Evaluator(min_confidence=min_confidence).run(limit=limit))


def compile_site(evaluation_id: int, dataset: str, build: bool = False) -> dict[str, Any]:
    """Hydrate an approved evaluation into an Astro build."""
    from dsf_compiler.builder import SiteCompiler

    return _dump(SiteCompiler().compile(evaluation_id, dataset, run_build=build))


def deploy_site(
    site_generation_id: int, dry_run: bool | None = None, build: bool = False
) -> dict[str, Any]:
    """Deploy a completed site generation to Cloudflare Pages."""
    from dsf_deployer.cloudflare import CloudflareDeployer

    return _dump(
        CloudflareDeployer().deploy(site_generation_id, run_build=build, dry_run=dry_run)
    )


def optimize(
    deployment_id: int | None = None, reinforce: bool = True, redeploy: bool = False
) -> dict[str, Any]:
    """Ingest telemetry and run the reinforcement loop."""
    from dsf_optimizer.optimizer import Optimizer

    return _dump(Optimizer().run(deployment_id, reinforce=reinforce, redeploy=redeploy))


# -- state / resource tools ------------------------------------------------


def fleet_status() -> dict[str, Any]:
    """Return ledger state counts across every lifecycle stage."""
    settings = get_settings()
    init_db(settings)
    with session_scope(settings) as session:
        counts = {
            "scout_jobs": _count(session, ScoutJob),
            "opportunities": _count(session, ArbitrageOpportunity),
            "evaluations": _count(session, Evaluation),
            "site_generations": _count(session, SiteGeneration),
            "deployments": _count(session, Deployment),
            "optimizations": _count(session, Optimization),
        }
        live = [
            {"project_slug": d.project_slug, "live_url": d.live_url}
            for d in session.exec(
                select(Deployment).where(Deployment.live_url.is_not(None))  # type: ignore[union-attr]
            )
        ]
    return {"counts": counts, "live_sites": live}


def analytics_revenue() -> dict[str, Any]:
    """Return a revenue + traffic scorecard."""
    settings = get_settings()
    init_db(settings)
    with session_scope(settings) as session:
        impressions = _sum(session, AnalyticsLog.impressions)
        clicks = _sum(session, AnalyticsLog.clicks)
        revenue_cents = _sum(session, AnalyticsLog.revenue_cents)
        live = int(
            session.exec(
                select(func.count()).select_from(Deployment).where(
                    Deployment.status == JobStatus.COMPLETED
                )
            ).one()
        )
    return {
        "revenue_usd": round(revenue_cents / 100.0, 2),
        "impressions": impressions,
        "clicks": clicks,
        "ctr": round((clicks / impressions) if impressions else 0.0, 4),
        "live_deployments": live,
    }


def top_opportunities(limit: int = 20) -> list[dict[str, Any]]:
    settings = get_settings()
    init_db(settings)
    with session_scope(settings) as session:
        records = list(
            session.exec(
                select(ArbitrageOpportunity)
                .order_by(ArbitrageOpportunity.arbitrage_score.desc())  # type: ignore[attr-defined]
                .limit(limit)
            )
        )
    return [r.model_dump(mode="json") for r in records]


def recent_deployments(limit: int = 20) -> list[dict[str, Any]]:
    settings = get_settings()
    init_db(settings)
    with session_scope(settings) as session:
        records = list(
            session.exec(
                select(Deployment)
                .order_by(Deployment.created_at.desc())  # type: ignore[attr-defined]
                .limit(limit)
            )
        )
    return [r.model_dump(mode="json") for r in records]


def latest_errors(limit: int = 20) -> list[dict[str, Any]]:
    """Return recent FAILED rows across the ledger for agent reflection."""
    settings = get_settings()
    init_db(settings)
    errors: list[dict[str, Any]] = []
    with session_scope(settings) as session:
        for model, kind, trace_attr in (
            (ScoutJob, "scout_job", "log_trace"),
            (SiteGeneration, "site_generation", "log_trace"),
            (Deployment, "deployment", "log_trace"),
            (Optimization, "optimization", "detail"),
        ):
            rows = session.exec(
                select(model).where(model.status == JobStatus.FAILED).limit(limit)
            )
            for row in rows:
                errors.append(
                    {
                        "kind": kind,
                        "id": row.id,
                        "trace": getattr(row, trace_attr, None),
                    }
                )
    return errors[:limit]


# -- query helpers ---------------------------------------------------------


def _count(session: Any, model: Any) -> int:
    return int(session.exec(select(func.count()).select_from(model)).one())


def _sum(session: Any, column: Any) -> int:
    return int(session.exec(select(func.coalesce(func.sum(column), 0))).one())
