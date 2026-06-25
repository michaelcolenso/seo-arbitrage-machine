"""Phases 6–7 — traffic telemetry processing and automated reinforcement.

``Optimizer.run`` ingests per-page interaction metrics for deployed sites, flags
structural underperformers (high impressions, weak click-through), and — for each
anomaly — asks the Agent Bridge to rewrite the page's meta, applies the rewrite to
the hydration layer, records an ``Optimization`` row, and optionally triggers a
silent rebuild + redeploy.

Every deployment and every page is processed in isolation: one failure becomes a
structured outcome rather than aborting the loop, and the run returns an
MCP-friendly :class:`OptimizationReport`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dsf_core.agent_bridge import AgentBridge
from dsf_core.config import Settings, get_settings
from dsf_core.telemetry import get_logger, log_event
from dsf_deployer.cloudflare import CloudflareDeployer
from dsf_engine.models import (
    AnalyticsLog,
    Deployment,
    JobStatus,
    Optimization,
    SiteGeneration,
)
from dsf_engine.sqlite_engine import init_db, session_scope
from pydantic import BaseModel, Field
from sqlmodel import select

from .telemetry import (
    CloudflareWebAnalyticsSource,
    MockTelemetrySource,
    PageMetric,
    TelemetrySource,
)

_log = get_logger("optimizer")


class OptimizationOutcome(BaseModel):
    """Per-page reinforcement outcome."""

    deployment_id: int
    page_path: str
    ctr: float
    impressions: int
    action: str
    new_title: str | None = None
    redeployed: bool = False
    status: str = "COMPLETED"  # COMPLETED / FAILED
    error: str | None = None


class OptimizationReport(BaseModel):
    """Summary of an optimization pass (MCP-tool friendly)."""

    status: str = "COMPLETED"
    deployments_processed: int = 0
    pages_ingested: int = 0
    flagged: int = 0
    reinforced: int = 0
    redeployed: int = 0
    outcomes: list[OptimizationOutcome] = Field(default_factory=list)


class Optimizer:
    """Ingests telemetry and runs the Agent-Bridge reinforcement loop."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        telemetry_source: TelemetrySource | None = None,
        bridge: AgentBridge | None = None,
        deployer: CloudflareDeployer | None = None,
        min_impressions: int = 300,
        max_ctr: float = 0.02,
    ) -> None:
        self.settings = settings or get_settings()
        self.telemetry_source = telemetry_source or self._default_source()
        self.bridge = bridge or AgentBridge(self.settings)
        self.deployer = deployer or CloudflareDeployer(settings=self.settings)
        self.min_impressions = min_impressions
        self.max_ctr = max_ctr

    def _default_source(self) -> TelemetrySource:
        if self.settings.cloudflare_api_token and self.settings.cloudflare_account_id:
            return CloudflareWebAnalyticsSource(self.settings)
        return MockTelemetrySource()

    # -- public API --------------------------------------------------------

    def run(
        self,
        deployment_id: int | None = None,
        *,
        reinforce: bool = True,
        redeploy: bool = False,
        run_build: bool = False,
        dry_run: bool | None = None,
        max_pages: int = 10,
    ) -> OptimizationReport:
        """Run an optimization pass over one or all completed deployments."""
        init_db(self.settings)
        deployments = self._load_deployments(deployment_id)
        report = OptimizationReport()

        for deployment in deployments:
            report.deployments_processed += 1
            try:
                metrics = self.telemetry_source.fetch(deployment)
            except Exception as exc:  # noqa: BLE001 — isolate per deployment
                log_event(
                    _log, "optimizer.ingest.failed", level=40,
                    deployment_id=deployment.id, error=str(exc),
                )
                continue

            self._persist_metrics(deployment, metrics)
            report.pages_ingested += len(metrics)

            flagged = [
                m for m in metrics
                if m.impressions >= self.min_impressions and m.ctr < self.max_ctr
            ]
            report.flagged += len(flagged)
            if not reinforce:
                continue

            for metric in flagged[:max_pages]:
                outcome = self._reinforce(
                    deployment, metric, redeploy=redeploy, run_build=run_build, dry_run=dry_run
                )
                report.outcomes.append(outcome)
                if outcome.status == "COMPLETED":
                    report.reinforced += 1
                if outcome.redeployed:
                    report.redeployed += 1

        log_event(
            _log, "optimizer.run.completed",
            deployments=report.deployments_processed,
            flagged=report.flagged, reinforced=report.reinforced,
        )
        return report

    # -- reinforcement -----------------------------------------------------

    def _reinforce(
        self,
        deployment: Deployment,
        metric: PageMetric,
        *,
        redeploy: bool,
        run_build: bool,
        dry_run: bool | None,
    ) -> OptimizationOutcome:
        optimization_id = self._create_optimization(deployment, metric)
        try:
            build_path, site_generation_id = self._site_build_path(deployment)
            current = self._read_meta(build_path)
            response = self.bridge.request(
                "optimize_content",
                {
                    "page_path": metric.page_path,
                    "impressions": metric.impressions,
                    "clicks": metric.clicks,
                    "ctr": round(metric.ctr, 4),
                    "current_title": current.get("title"),
                    "current_description": current.get("description"),
                },
            )
            if not response.ok:
                raise RuntimeError(f"agent optimize_content failed: {response.error}")

            new_title = response.result.get("title")
            new_description = response.result.get("description")
            keywords = response.result.get("keywords")

            if build_path is not None and current:
                action = "meta_rewrite"
                self._apply_meta(build_path, new_title, new_description, keywords)
            else:
                action = "meta_unavailable"  # suggestion stored, no build to apply to

            redeployed = False
            if redeploy and build_path is not None and site_generation_id is not None:
                deploy_report = self.deployer.deploy(
                    site_generation_id, run_build=run_build, dry_run=dry_run
                )
                redeployed = deploy_report.status == "COMPLETED"

            detail = f"title={new_title!r}" if new_title else "no title returned"
            self._mark_optimization(
                optimization_id, JobStatus.COMPLETED, action=action,
                detail=detail, redeployed=redeployed,
            )
            log_event(
                _log, "optimizer.reinforced",
                deployment_id=deployment.id, page=metric.page_path,
                action=action, redeployed=redeployed,
            )
            return OptimizationOutcome(
                deployment_id=deployment.id or 0,
                page_path=metric.page_path,
                ctr=round(metric.ctr, 4),
                impressions=metric.impressions,
                action=action,
                new_title=new_title,
                redeployed=redeployed,
            )
        except Exception as exc:  # noqa: BLE001 — isolate per page
            self._mark_optimization(
                optimization_id, JobStatus.FAILED, action="failed", detail=str(exc),
            )
            log_event(
                _log, "optimizer.reinforce.failed", level=40,
                deployment_id=deployment.id, page=metric.page_path, error=str(exc),
            )
            return OptimizationOutcome(
                deployment_id=deployment.id or 0,
                page_path=metric.page_path,
                ctr=round(metric.ctr, 4),
                impressions=metric.impressions,
                action="failed",
                status="FAILED",
                error=str(exc),
            )

    # -- hydration-layer helpers ------------------------------------------

    def _site_build_path(self, deployment: Deployment) -> tuple[Path | None, int | None]:
        if deployment.site_generation_id is None:
            return None, None
        with session_scope(self.settings) as session:
            site = session.get(SiteGeneration, deployment.site_generation_id)
            if site is None or not site.build_path:
                return None, deployment.site_generation_id
            return Path(site.build_path), site.id

    @staticmethod
    def _meta_path(build_path: Path) -> Path:
        return build_path / "src" / "data" / "meta.json"

    def _read_meta(self, build_path: Path | None) -> dict[str, Any]:
        if build_path is None:
            return {}
        meta_file = self._meta_path(build_path)
        if not meta_file.is_file():
            return {}
        try:
            return json.loads(meta_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _apply_meta(
        self,
        build_path: Path,
        new_title: str | None,
        new_description: str | None,
        keywords: Any,
    ) -> None:
        meta_file = self._meta_path(build_path)
        meta = self._read_meta(build_path)
        if new_title:
            meta["title"] = new_title
        if new_description:
            meta["description"] = new_description
        if isinstance(keywords, list) and keywords:
            meta["optimized_keywords"] = [str(k) for k in keywords]
        meta["optimized"] = True
        meta_file.parent.mkdir(parents=True, exist_ok=True)
        meta_file.write_text(json.dumps(meta, indent=2, allow_nan=False), encoding="utf-8")

    # -- ledger helpers ----------------------------------------------------

    def _load_deployments(self, deployment_id: int | None) -> list[Deployment]:
        with session_scope(self.settings) as session:
            if deployment_id is not None:
                deployment = session.get(Deployment, deployment_id)
                return [deployment] if deployment is not None else []
            statement = select(Deployment).where(Deployment.status == JobStatus.COMPLETED)
            return list(session.exec(statement))

    def _persist_metrics(self, deployment: Deployment, metrics: list[PageMetric]) -> None:
        with session_scope(self.settings) as session:
            for metric in metrics:
                session.add(
                    AnalyticsLog(
                        deployment_id=deployment.id,
                        page_path=metric.page_path,
                        impressions=metric.impressions,
                        clicks=metric.clicks,
                        revenue_cents=metric.revenue_cents,
                    )
                )

    def _create_optimization(self, deployment: Deployment, metric: PageMetric) -> int:
        with session_scope(self.settings) as session:
            optimization = Optimization(
                deployment_id=deployment.id,
                page_path=metric.page_path,
                impressions=metric.impressions,
                clicks=metric.clicks,
                ctr=round(metric.ctr, 4),
                status=JobStatus.RUNNING,
            )
            session.add(optimization)
            session.flush()
            optimization_id = optimization.id
        if optimization_id is None:
            raise RuntimeError("failed to allocate an Optimization id")
        return optimization_id

    def _mark_optimization(
        self,
        optimization_id: int,
        status: JobStatus,
        *,
        action: str,
        detail: str | None,
        redeployed: bool = False,
    ) -> None:
        with session_scope(self.settings) as session:
            optimization = session.get(Optimization, optimization_id)
            if optimization is None:
                return
            optimization.status = status
            optimization.action = action
            optimization.detail = detail
            optimization.redeployed = redeployed
            session.add(optimization)
