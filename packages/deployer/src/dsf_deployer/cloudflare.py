"""Phase 5 — zero-cost Cloudflare Pages deployment.

``CloudflareDeployer.deploy`` takes one ``COMPLETED`` :class:`SiteGeneration`,
ensures its production assets exist, pushes them to Cloudflare Pages, and records
a :class:`Deployment` row (with the live ``*.pages.dev`` URL) in the ledger.

Two modes, mirroring the platform's mock-first ethos:

* **dry-run** (default without Cloudflare credentials) — simulates the upload and
  synthesises the canonical ``https://<slug>.pages.dev`` URL, so the whole
  pipeline runs end-to-end with no real account.
* **live** — ensures the Pages project exists via the Cloudflare REST API
  (``httpx``) and performs a direct-upload deployment of ``dist/`` via
  ``wrangler``.

Every failure is caught and returned as a structured ``DeployReport``
(``AGENT_ACTION_REQUIRED`` / ``REJECTED``); the deployer never raises into caller
code, and the ``Deployment`` row is moved to ``FAILED`` with a trace.
"""

from __future__ import annotations

import re
import subprocess
import traceback
import uuid
from pathlib import Path
from typing import Any

import httpx
from dsf_core.config import Settings, get_settings
from dsf_core.telemetry import get_logger, log_event
from dsf_engine.models import (
    ArbitrageOpportunity,
    Deployment,
    Evaluation,
    JobStatus,
    SiteGeneration,
    utcnow,
)
from dsf_engine.sqlite_engine import init_db, session_scope
from pydantic import BaseModel, Field

_log = get_logger("deployer.cloudflare")

_CF_API_BASE = "https://api.cloudflare.com/client/v4"
_PAGES_DEV = re.compile(r"https://[a-z0-9.\-]+\.pages\.dev")
# Cloudflare Pages project names: lowercase alnum + hyphens, <= 58 chars.
_MAX_SLUG_LEN = 58


class CloudflareError(RuntimeError):
    """Raised by transport/build helpers; converted to a reflection by deploy()."""


class DeployReport(BaseModel):
    """The structured outcome of a deployment (MCP-tool friendly)."""

    status: str  # COMPLETED / REJECTED / AGENT_ACTION_REQUIRED
    site_generation_id: int
    deployment_id: int | None = None
    project_slug: str | None = None
    live_url: str | None = None
    mode: str | None = None  # dry_run / live
    error_type: str | None = None
    message: str | None = None


class _Target(BaseModel):
    """Resolved deployment target derived from a SiteGeneration."""

    site_generation_id: int
    status: JobStatus
    build_path: str | None
    slug: str


class CloudflareDeployer:
    """Deploys compiled sites to Cloudflare Pages (live or dry-run)."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
        wrangler_runner: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        # Injectable so the live path is unit-testable without a real account.
        self._wrangler_runner = wrangler_runner or self._run_wrangler

    # -- public API --------------------------------------------------------

    def has_credentials(self) -> bool:
        return bool(self.settings.cloudflare_api_token and self.settings.cloudflare_account_id)

    def deploy(
        self,
        site_generation_id: int,
        *,
        run_build: bool = False,
        dry_run: bool | None = None,
    ) -> DeployReport:
        """Deploy one compiled site generation to Cloudflare Pages."""
        init_db(self.settings)
        target = self._load_target(site_generation_id)
        if target is None:
            return DeployReport(
                status="AGENT_ACTION_REQUIRED",
                site_generation_id=site_generation_id,
                error_type="SiteGenerationNotFound",
                message=f"site generation {site_generation_id} not found",
            )
        if target.status != JobStatus.COMPLETED:
            return DeployReport(
                status="REJECTED",
                site_generation_id=site_generation_id,
                project_slug=target.slug,
                message=f"site generation status is {target.status.value}, not completed",
            )

        effective_dry_run = (not self.has_credentials()) if dry_run is None else dry_run
        mode = "dry_run" if effective_dry_run else "live"
        deployment_id = self._create_deployment(site_generation_id, target.slug)

        try:
            dist = self._ensure_dist(target.build_path, run_build, effective_dry_run)
            if effective_dry_run:
                project_id = None
                cf_deployment_id = f"dryrun-{uuid.uuid4().hex[:12]}"
                live_url = f"https://{target.slug}.pages.dev"
            else:
                project_id, subdomain = self._ensure_project(target.slug)
                cf_deployment_id, live_url = self._deploy_dist(dist, target.slug, subdomain)

            self._mark_deployment(
                deployment_id,
                JobStatus.COMPLETED,
                live_url=live_url,
                cloudflare_project_id=project_id,
                cloudflare_deployment_id=cf_deployment_id,
            )
            log_event(
                _log,
                "deploy.completed",
                site_generation_id=site_generation_id,
                deployment_id=deployment_id,
                mode=mode,
                live_url=live_url,
            )
            return DeployReport(
                status="COMPLETED",
                site_generation_id=site_generation_id,
                deployment_id=deployment_id,
                project_slug=target.slug,
                live_url=live_url,
                mode=mode,
            )
        except Exception as exc:  # noqa: BLE001 — convert to a reflection payload
            trace = traceback.format_exc()
            self._mark_deployment(deployment_id, JobStatus.FAILED, log_trace=trace)
            log_event(
                _log,
                "deploy.failed",
                level=40,
                site_generation_id=site_generation_id,
                deployment_id=deployment_id,
                mode=mode,
                error=str(exc),
            )
            return DeployReport(
                status="AGENT_ACTION_REQUIRED",
                site_generation_id=site_generation_id,
                deployment_id=deployment_id,
                project_slug=target.slug,
                mode=mode,
                error_type=type(exc).__name__,
                message=str(exc),
            )

    # -- asset resolution --------------------------------------------------

    def _ensure_dist(self, build_path: str | None, run_build: bool, dry_run: bool) -> Path | None:
        if not build_path:
            raise CloudflareError("site generation has no build_path")
        build_dir = Path(build_path)
        if not build_dir.is_dir():
            raise CloudflareError(f"build path not found: {build_dir}")
        dist = build_dir / "dist"
        if dist.is_dir():
            return dist
        if run_build:
            self._build_assets(build_dir)
            if dist.is_dir():
                return dist
            raise CloudflareError("astro build did not produce dist/")
        if dry_run:
            # Dry-run can simulate without built assets.
            return None
        raise CloudflareError(
            "no dist/ to deploy; run the build first or pass run_build=True"
        )

    def _build_assets(self, build_dir: Path) -> None:
        """Run `npm install && npm run build`; raise on failure."""
        try:
            subprocess.run(
                ["npm", "install", "--no-audit", "--no-fund"],
                cwd=build_dir, check=True, capture_output=True, text=True, timeout=600,
            )
            subprocess.run(
                ["npm", "run", "build"],
                cwd=build_dir, check=True, capture_output=True, text=True, timeout=600,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise CloudflareError(f"asset build failed: {exc}") from exc

    # -- Cloudflare REST API (project management) --------------------------

    def _ensure_project(self, slug: str) -> tuple[str, str]:
        """Ensure the Pages project exists; return (project_id, subdomain)."""
        account = self.settings.cloudflare_account_id
        base = f"{_CF_API_BASE}/accounts/{account}/pages/projects"

        existing = self._api_request("GET", f"{base}/{slug}", expect=(200, 404))
        if existing.status_code == 200:
            result = existing.json().get("result", {})
            return str(result.get("id", slug)), str(result.get("subdomain", f"{slug}.pages.dev"))

        created = self._api_request(
            "POST", base, json={"name": slug, "production_branch": "main"}, expect=(200, 201)
        )
        result = created.json().get("result", {})
        log_event(_log, "deploy.project.created", slug=slug)
        return str(result.get("id", slug)), str(result.get("subdomain", f"{slug}.pages.dev"))

    def _api_request(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        expect: tuple[int, ...] = (200,),
    ) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.settings.cloudflare_api_token}",
            "Content-Type": "application/json",
        }
        try:
            if self._client is not None:
                response = self._client.request(method, url, headers=headers, json=json)
            else:
                with httpx.Client(timeout=60.0) as client:
                    response = client.request(method, url, headers=headers, json=json)
        except httpx.HTTPError as exc:
            raise CloudflareError(f"Cloudflare API request failed: {exc}") from exc
        if response.status_code not in expect:
            raise CloudflareError(
                f"Cloudflare API {method} {url} returned {response.status_code}: {response.text[:300]}"
            )
        return response

    # -- direct upload via wrangler ---------------------------------------

    def _deploy_dist(self, dist: Path | None, slug: str, subdomain: str) -> tuple[str, str]:
        if dist is None:
            raise CloudflareError("live deployment requires built dist/ assets")
        deployment_id, parsed_url = self._wrangler_runner(dist, slug)
        # The canonical production URL is the project subdomain; prefer it for live_url.
        live_url = f"https://{subdomain}" if subdomain else (parsed_url or f"https://{slug}.pages.dev")
        return deployment_id, live_url

    def _run_wrangler(self, dist: Path, slug: str) -> tuple[str, str]:
        """Run `wrangler pages deploy`; return (deployment_id, parsed_url)."""
        env = {
            "CLOUDFLARE_API_TOKEN": self.settings.cloudflare_api_token or "",
            "CLOUDFLARE_ACCOUNT_ID": self.settings.cloudflare_account_id or "",
        }
        try:
            import os

            full_env = {**os.environ, **env}
            completed = subprocess.run(
                [
                    "npx", "--yes", "wrangler@3", "pages", "deploy", str(dist),
                    "--project-name", slug, "--branch", "main", "--commit-dirty=true",
                ],
                check=True, capture_output=True, text=True, timeout=900, env=full_env,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            stderr = getattr(exc, "stderr", "") or ""
            raise CloudflareError(f"wrangler deploy failed: {exc} {stderr}".strip()) from exc
        output = f"{completed.stdout}\n{completed.stderr}"
        match = _PAGES_DEV.search(output)
        parsed_url = match.group(0) if match else ""
        return uuid.uuid4().hex[:12], parsed_url

    # -- ledger helpers ----------------------------------------------------

    def _load_target(self, site_generation_id: int) -> _Target | None:
        with session_scope(self.settings) as session:
            site = session.get(SiteGeneration, site_generation_id)
            if site is None:
                return None
            niche_id: str | None = None
            if site.evaluation_id is not None:
                evaluation = session.get(Evaluation, site.evaluation_id)
                if evaluation is not None and evaluation.opportunity_id is not None:
                    opp = session.get(ArbitrageOpportunity, evaluation.opportunity_id)
                    niche_id = getattr(opp, "niche_id", None)
            slug = self._project_slug(niche_id, site)
            return _Target(
                site_generation_id=site_generation_id,
                status=site.status,
                build_path=site.build_path,
                slug=slug,
            )

    def _project_slug(self, niche_id: str | None, site: SiteGeneration) -> str:
        if niche_id:
            return _slugify(niche_id)
        if site.build_path:
            # Strip the -e<eval>-s<site> build suffix to keep the project stable.
            base = Path(site.build_path).name
            base = re.sub(r"-e\d+-s\d+$", "", base)
            if base:
                return _slugify(base)
        return f"dsf-site-{site.id}"

    def _create_deployment(self, site_generation_id: int, slug: str) -> int:
        with session_scope(self.settings) as session:
            deployment = Deployment(
                site_generation_id=site_generation_id,
                project_slug=slug,
                status=JobStatus.RUNNING,
            )
            session.add(deployment)
            session.flush()
            deployment_id = deployment.id
        if deployment_id is None:
            raise RuntimeError("failed to allocate a Deployment id")
        return deployment_id

    def _mark_deployment(
        self,
        deployment_id: int,
        status: JobStatus,
        *,
        live_url: str | None = None,
        cloudflare_project_id: str | None = None,
        cloudflare_deployment_id: str | None = None,
        log_trace: str | None = None,
    ) -> None:
        with session_scope(self.settings) as session:
            deployment = session.get(Deployment, deployment_id)
            if deployment is None:
                return
            deployment.status = status
            if live_url is not None:
                deployment.live_url = live_url
            if cloudflare_project_id is not None:
                deployment.cloudflare_project_id = cloudflare_project_id
            if cloudflare_deployment_id is not None:
                deployment.cloudflare_deployment_id = cloudflare_deployment_id
            if log_trace is not None:
                deployment.log_trace = log_trace
            deployment.updated_at = utcnow()
            session.add(deployment)


def _slugify(value: str) -> str:
    """Produce a Cloudflare-Pages-safe project slug (lowercase alnum + hyphens)."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    slug = slug[:_MAX_SLUG_LEN].strip("-")
    return slug or "dsf-site"
