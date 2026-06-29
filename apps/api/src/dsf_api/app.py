"""The DataSiteForge FastAPI control plane (Phase 8).

``create_app`` builds the gateway: lifecycle POST endpoints submit orchestrator
runs to a background :class:`JobManager` and return a ``job_id``; GET endpoints
read aggregate state straight from the SQLite ledger; ``/`` serves a self-contained
operator console.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dsf_core import __version__ as core_version
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
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from sqlmodel import select

from .jobs import JobManager
from .schemas import (
    CompileRunRequest,
    DeployRunRequest,
    EvaluateRunRequest,
    JobAccepted,
    OptimizeRunRequest,
    ScoutRunRequest,
)

_STATIC_DIR = Path(__file__).parent / "static"

# Endpoints reachable without a token: the public console and the liveness probe.
_PUBLIC_PATHS = frozenset({"/", "/healthz"})


def _dump(report: Any) -> dict[str, Any]:
    """Serialise a pydantic report to a JSON-safe dict."""
    return report.model_dump(mode="json")


def require_token(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> None:
    """Enforce the API token on protected routes when one is configured.

    Applied as a global dependency.  When ``DSF_API_TOKEN`` is unset the API is
    open (development); when set, every route except the console and health probe
    requires a matching ``Authorization: Bearer <token>`` or ``X-API-Key`` header.
    """
    if request.url.path in _PUBLIC_PATHS:
        return
    expected = get_settings().api_token
    if not expected:
        return
    provided: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    elif x_api_key:
        provided = x_api_key.strip()
    if not provided or provided != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# -- job handlers (kind -> Callable[[params], result]) ---------------------
# Handlers take JSON-serialisable params so jobs are durable and recoverable
# across a restart (a Python closure could not be persisted).


def _scout_job(params: dict[str, Any]) -> dict[str, Any]:
    from dsf_scout.agent import ScoutAgent
    from dsf_scout.sources import ManifestSource, OpenDataSource

    req = ScoutRunRequest(**params)
    s = get_settings()
    assert s.data_dir is not None
    sources: list[Any] = [ManifestSource(s.data_dir / "manifest.json")]
    if req.live:
        sources.append(OpenDataSource(req.portal, rows=req.rows))
    return _dump(ScoutAgent(sources, settings=s).run(req.niche))


def _evaluate_job(params: dict[str, Any]) -> dict[str, Any]:
    from dsf_engine.evaluator import Evaluator

    req = EvaluateRunRequest(**params)
    return _dump(Evaluator(min_confidence=req.min_confidence).run(limit=req.limit))


def _compile_job(params: dict[str, Any]) -> dict[str, Any]:
    from dsf_compiler.builder import SiteCompiler

    req = CompileRunRequest(**params)
    return _dump(SiteCompiler().compile(req.evaluation_id, req.dataset, run_build=req.build))


def _deploy_job(params: dict[str, Any]) -> dict[str, Any]:
    from dsf_deployer.cloudflare import CloudflareDeployer

    req = DeployRunRequest(**params)
    return _dump(
        CloudflareDeployer().deploy(req.site_generation_id, run_build=req.build, dry_run=req.dry_run)
    )


def _optimize_job(params: dict[str, Any]) -> dict[str, Any]:
    from dsf_optimizer.optimizer import Optimizer

    req = OptimizeRunRequest(**params)
    return _dump(
        Optimizer(min_impressions=req.min_impressions, max_ctr=req.max_ctr).run(
            req.deployment_id, reinforce=req.reinforce, redeploy=req.redeploy
        )
    )


_JOB_HANDLERS = {
    "scout": _scout_job,
    "evaluate": _evaluate_job,
    "compile": _compile_job,
    "deploy": _deploy_job,
    "optimize": _optimize_job,
}


def create_app(*, inline_jobs: bool = False) -> FastAPI:
    jobs = JobManager(_JOB_HANDLERS, inline=inline_jobs)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        init_db(get_settings())  # ensure the ledger exists + is migrated
        jobs.recover()  # reconcile orphaned jobs left by a prior process
        yield
        jobs.shutdown()

    app = FastAPI(
        title="DataSiteForge Control Plane",
        version=core_version,
        lifespan=lifespan,
        dependencies=[Depends(require_token)],
    )

    # Self-hosted console assets (CSS/JS). Mounted sub-apps bypass the global
    # auth dependency, so these stay publicly fetchable — they hold no secrets.
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    # -- health & console -------------------------------------------------

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": core_version}

    @app.get("/", response_class=HTMLResponse)
    def console() -> str:
        index = _STATIC_DIR / "index.html"
        if not index.is_file():
            return "<h1>DataSiteForge</h1><p>Console not bundled.</p>"
        return index.read_text(encoding="utf-8")

    # -- lifecycle actions (background jobs) ------------------------------

    @app.post("/scout/run", response_model=JobAccepted)
    def scout_run(req: ScoutRunRequest) -> JobAccepted:
        return _accept(jobs.submit("scout", req.model_dump()))

    @app.post("/evaluate/run", response_model=JobAccepted)
    def evaluate_run(req: EvaluateRunRequest) -> JobAccepted:
        return _accept(jobs.submit("evaluate", req.model_dump()))

    @app.post("/compile/run", response_model=JobAccepted)
    def compile_run(req: CompileRunRequest) -> JobAccepted:
        return _accept(jobs.submit("compile", req.model_dump()))

    @app.post("/deploy/run", response_model=JobAccepted)
    def deploy_run(req: DeployRunRequest) -> JobAccepted:
        return _accept(jobs.submit("deploy", req.model_dump()))

    @app.post("/optimize/run", response_model=JobAccepted)
    def optimize_run(req: OptimizeRunRequest) -> JobAccepted:
        return _accept(jobs.submit("optimize", req.model_dump()))

    # -- job polling ------------------------------------------------------

    @app.get("/jobs")
    def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
        return [j.model_dump(mode="json") for j in jobs.list(limit)]

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        record = jobs.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="job not found")
        return record.model_dump(mode="json")

    # -- fleet state & analytics ------------------------------------------

    @app.get("/fleet/status")
    def fleet_status() -> dict[str, Any]:
        with session_scope(get_settings()) as session:
            counts = {
                "scout_jobs": _count(session, ScoutJob),
                "opportunities": _count(session, ArbitrageOpportunity),
                "evaluations": _count(session, Evaluation),
                "site_generations": _count(session, SiteGeneration),
                "deployments": _count(session, Deployment),
                "optimizations": _count(session, Optimization),
            }
            deployments_by_status = _group_status(session, Deployment)
            live_sites = [
                {
                    "deployment_id": d.id,
                    "project_slug": d.project_slug,
                    "live_url": d.live_url,
                    "status": d.status.value,
                }
                for d in session.exec(
                    select(Deployment).where(Deployment.live_url.is_not(None))  # type: ignore[union-attr]
                )
            ]
        return {
            "counts": counts,
            "deployments_by_status": deployments_by_status,
            "live_sites": live_sites,
        }

    @app.get("/analytics/revenue")
    def analytics_revenue() -> dict[str, Any]:
        with session_scope(get_settings()) as session:
            impressions = _sum(session, AnalyticsLog.impressions)
            clicks = _sum(session, AnalyticsLog.clicks)
            revenue_cents = _sum(session, AnalyticsLog.revenue_cents)
            live = _count_where(session, Deployment, Deployment.status == JobStatus.COMPLETED)
            opportunities = _count(session, ArbitrageOpportunity)
        ctr = (clicks / impressions) if impressions else 0.0
        return {
            "revenue_usd": round(revenue_cents / 100.0, 2),
            "impressions": impressions,
            "clicks": clicks,
            "ctr": round(ctr, 4),
            "live_deployments": live,
            "opportunities": opportunities,
        }

    @app.get("/opportunities")
    def opportunities(limit: int = 50) -> list[dict[str, Any]]:
        return _list(ArbitrageOpportunity, ArbitrageOpportunity.arbitrage_score, limit, desc=True)

    @app.get("/evaluations")
    def evaluations(limit: int = 50) -> list[dict[str, Any]]:
        return _list(Evaluation, Evaluation.created_at, limit, desc=True)

    @app.get("/deployments")
    def deployments(limit: int = 50) -> list[dict[str, Any]]:
        return _list(Deployment, Deployment.created_at, limit, desc=True)

    @app.get("/optimizations")
    def optimizations(limit: int = 50) -> list[dict[str, Any]]:
        return _list(Optimization, Optimization.created_at, limit, desc=True)

    return app


# -- helpers ---------------------------------------------------------------


def _accept(record: Any) -> JobAccepted:
    return JobAccepted(job_id=record.id, kind=record.kind, status=record.status)


def _count(session: Any, model: Any) -> int:
    return int(session.exec(select(func.count()).select_from(model)).one())


def _count_where(session: Any, model: Any, condition: Any) -> int:
    return int(session.exec(select(func.count()).select_from(model).where(condition)).one())


def _sum(session: Any, column: Any) -> int:
    value = session.exec(select(func.coalesce(func.sum(column), 0))).one()
    return int(value)


def _group_status(session: Any, model: Any) -> dict[str, int]:
    rows = session.exec(select(model.status, func.count()).group_by(model.status)).all()
    return {status.value: int(count) for status, count in rows}


def _list(model: Any, order_column: Any, limit: int, *, desc: bool = False) -> list[dict[str, Any]]:
    order = order_column.desc() if desc else order_column.asc()
    with session_scope(get_settings()) as session:
        records = list(session.exec(select(model).order_by(order).limit(limit)))
    return [r.model_dump(mode="json") for r in records]
