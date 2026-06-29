"""The Phase 4 compilation lifecycle engine.

``SiteCompiler.compile`` turns one ``APPROVED`` :class:`Evaluation` into a hydrated
Astro site: it copies the chosen fixed-invariant template, overwrites only the
``src/data/*.json`` hydration layer, and records a ``SiteGeneration`` row in the
ledger.  Every failure mode is caught and returned as a structured
``CompileReport`` (``AGENT_ACTION_REQUIRED`` / ``REJECTED``) — the compiler never
raises into caller code, satisfying the defensive-failure-isolation mandate.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import traceback
from pathlib import Path
from typing import Any

from dsf_core.config import Settings, get_settings
from dsf_core.telemetry import get_logger, log_event
from dsf_engine.duckdb_engine import DuckDBBroker, DuckDBError
from dsf_engine.models import (
    ArbitrageOpportunity,
    Evaluation,
    EvaluationVerdict,
    JobStatus,
    SiteGeneration,
    TemplateType,
    utcnow,
)
from dsf_engine.sqlite_engine import init_db, session_scope
from pydantic import BaseModel, Field

from .hydration import (
    build_meta_payload,
    build_routes_payload,
    build_rows_payload,
    title_from,
)

_log = get_logger("compiler.builder")

# Directories that must never be copied from a template into a build.
_COPY_IGNORE = shutil.ignore_patterns("node_modules", "dist", ".astro", ".git")


class CompileReport(BaseModel):
    """The structured outcome of a compilation (MCP-tool friendly)."""

    status: str  # COMPLETED / REJECTED / AGENT_ACTION_REQUIRED
    evaluation_id: int
    site_generation_id: int | None = None
    niche_id: str | None = None
    template_type: str | None = None
    build_path: str | None = None
    row_count: int = 0
    route_count: int = 0
    built: bool = False
    error_type: str | None = None
    message: str | None = None


class SiteCompiler:
    """Compiles approved evaluations into hydrated Astro site builds."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        templates_dir: Path | None = None,
        row_limit: int = 500,
        route_limit: int = 500,
    ) -> None:
        self.settings = settings or get_settings()
        self.route_limit = route_limit
        # Templates ship as package data next to this module, so they resolve
        # correctly from an installed wheel as well as the source workspace —
        # never depending on the current working directory.
        self.templates_dir = templates_dir or (Path(__file__).resolve().parent / "templates")
        self.row_limit = row_limit

    def compile(
        self,
        evaluation_id: int,
        dataset_path: str | Path,
        *,
        run_build: bool = False,
    ) -> CompileReport:
        """Hydrate a site for ``evaluation_id`` from ``dataset_path``."""
        init_db(self.settings)
        loaded = self._load_evaluation(evaluation_id)
        if loaded is None:
            return CompileReport(
                status="AGENT_ACTION_REQUIRED",
                evaluation_id=evaluation_id,
                error_type="EvaluationNotFound",
                message=f"evaluation {evaluation_id} not found",
            )
        evaluation, opportunity = loaded

        if evaluation.verdict != EvaluationVerdict.APPROVED:
            log_event(
                _log,
                "compiler.skip.not_approved",
                level=30,
                evaluation_id=evaluation_id,
                verdict=evaluation.verdict.value,
            )
            return CompileReport(
                status="REJECTED",
                evaluation_id=evaluation_id,
                niche_id=getattr(opportunity, "niche_id", None),
                template_type=evaluation.template_type.value,
                message=f"evaluation verdict is {evaluation.verdict.value}, not approved",
            )

        niche_id = getattr(opportunity, "niche_id", None) or f"evaluation-{evaluation_id}"
        site_id = self._create_site_generation(evaluation)
        # The site-generation id makes every build dir unique, so re-compiling the
        # same evaluation (a retry, or a fixed dataset) never overwrites a prior
        # generation's artifacts that an earlier row / deployment still points at.
        build_name = f"{_slugify(niche_id)}-e{evaluation_id}-s{site_id}"

        try:
            row_count, route_count, build_path = self._hydrate(
                evaluation, opportunity, dataset_path, build_name
            )
            built = self._maybe_build(build_path) if run_build else False
            if run_build and not built:
                # A requested build that produced no dist/ must not look COMPLETED:
                # downstream deploy would pick up a generation with no artifacts.
                message = "requested build failed: npm install/build produced no dist/"
                self._mark_site(
                    site_id,
                    JobStatus.FAILED,
                    build_path=str(build_path),
                    log_trace=message,
                )
                log_event(
                    _log,
                    "compiler.build.unsuccessful",
                    level=40,
                    evaluation_id=evaluation_id,
                    site_generation_id=site_id,
                    build_path=str(build_path),
                )
                return CompileReport(
                    status="AGENT_ACTION_REQUIRED",
                    evaluation_id=evaluation_id,
                    site_generation_id=site_id,
                    niche_id=niche_id,
                    template_type=evaluation.template_type.value,
                    build_path=str(build_path),
                    row_count=row_count,
                    built=False,
                    error_type="BuildFailed",
                    message=message,
                )
            self._mark_site(site_id, JobStatus.COMPLETED, build_path=str(build_path))
            log_event(
                _log,
                "compiler.completed",
                evaluation_id=evaluation_id,
                site_generation_id=site_id,
                rows=row_count,
                build_path=str(build_path),
                built=built,
            )
            return CompileReport(
                status="COMPLETED",
                evaluation_id=evaluation_id,
                site_generation_id=site_id,
                niche_id=niche_id,
                template_type=evaluation.template_type.value,
                build_path=str(build_path),
                row_count=row_count,
                route_count=route_count,
                built=built,
            )
        except Exception as exc:  # noqa: BLE001 — convert to a reflection payload
            trace = traceback.format_exc()
            self._mark_site(site_id, JobStatus.FAILED, log_trace=trace)
            log_event(
                _log,
                "compiler.failed",
                level=40,
                evaluation_id=evaluation_id,
                site_generation_id=site_id,
                error=str(exc),
            )
            return CompileReport(
                status="AGENT_ACTION_REQUIRED",
                evaluation_id=evaluation_id,
                site_generation_id=site_id,
                niche_id=niche_id,
                template_type=evaluation.template_type.value,
                error_type=type(exc).__name__,
                message=str(exc),
            )

    # -- pipeline stages ---------------------------------------------------

    def _hydrate(
        self,
        evaluation: Evaluation,
        opportunity: ArbitrageOpportunity | None,
        dataset_path: str | Path,
        build_name: str,
    ) -> tuple[int, int, Path]:
        """Copy the template, write the hydration layer; return (rows, routes, path)."""
        dataset = Path(dataset_path).expanduser()
        if not dataset.is_file():
            raise FileNotFoundError(f"dataset not found: {dataset}")

        broker = DuckDBBroker(self.settings)
        try:
            profile = broker.profile_dataset(dataset, limit=self.row_limit)
        except DuckDBError as exc:
            raise RuntimeError(f"failed to read dataset: {exc}") from exc
        finally:
            broker.close()

        columns = profile["columns"]
        rows_payload = build_rows_payload(profile["sample_rows"], limit=self.row_limit)

        niche_id = getattr(opportunity, "niche_id", None)
        canonical_base = f"https://{_slugify(niche_id)}.pages.dev" if niche_id else ""
        # Programmatic per-route fan-out only applies to the directory theme;
        # the calculator is a single parametric page.
        route_columns = (
            json.loads(evaluation.seo_high_volume_columns or "[]")
            if evaluation.template_type == TemplateType.DIRECTORY
            else []
        )
        routes_payload = build_routes_payload(
            rows_payload,
            columns,
            route_columns=route_columns,
            niche_title=title_from(niche_id),
            max_routes=self.route_limit,
        )
        meta_payload = build_meta_payload(
            evaluation,
            opportunity,
            columns,
            canonical_base=canonical_base,
            route_count=len(routes_payload),
        )

        template_dir = self.templates_dir / evaluation.template_type.value
        if not template_dir.is_dir():
            raise FileNotFoundError(f"template not found: {template_dir}")

        build_root = self.settings.data_dir / "builds"  # type: ignore[operator]
        build_dir = build_root / build_name
        if build_dir.exists():
            shutil.rmtree(build_dir)
        build_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(template_dir, build_dir, ignore=_COPY_IGNORE)

        data_dir = build_dir / "src" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        # allow_nan=False guarantees we never emit invalid JSON (NaN/Infinity);
        # _sanitise already nulls non-finite floats, this is the belt-and-suspenders.
        (data_dir / "rows.json").write_text(
            json.dumps(rows_payload, indent=2, allow_nan=False), encoding="utf-8"
        )
        (data_dir / "meta.json").write_text(
            json.dumps(meta_payload, indent=2, allow_nan=False), encoding="utf-8"
        )
        (data_dir / "routes.json").write_text(
            json.dumps(routes_payload, indent=2, allow_nan=False), encoding="utf-8"
        )
        return len(rows_payload), len(routes_payload), build_dir

    def _maybe_build(self, build_dir: Path) -> bool:
        """Optionally run the real Astro build; never raise on failure."""
        try:
            subprocess.run(
                ["npm", "install", "--no-audit", "--no-fund"],
                cwd=build_dir,
                check=True,
                capture_output=True,
                text=True,
                timeout=600,
            )
            subprocess.run(
                ["npm", "run", "build"],
                cwd=build_dir,
                check=True,
                capture_output=True,
                text=True,
                timeout=600,
            )
            return (build_dir / "dist").is_dir()
        except (OSError, subprocess.SubprocessError) as exc:
            log_event(_log, "compiler.build.failed", level=40, error=str(exc))
            return False

    # -- ledger helpers ----------------------------------------------------

    def _load_evaluation(
        self, evaluation_id: int
    ) -> tuple[Evaluation, ArbitrageOpportunity | None] | None:
        with session_scope(self.settings) as session:
            evaluation = session.get(Evaluation, evaluation_id)
            if evaluation is None:
                return None
            opportunity: ArbitrageOpportunity | None = None
            if evaluation.opportunity_id is not None:
                opportunity = session.get(ArbitrageOpportunity, evaluation.opportunity_id)
            return evaluation, opportunity

    def _create_site_generation(self, evaluation: Evaluation) -> int:
        with session_scope(self.settings) as session:
            site = SiteGeneration(
                evaluation_id=evaluation.id,
                template_type=evaluation.template_type,
                status=JobStatus.RUNNING,
                build_path=None,
            )
            session.add(site)
            session.flush()
            site_id = site.id
        if site_id is None:
            raise RuntimeError("failed to allocate a SiteGeneration id")
        return site_id

    def _mark_site(
        self,
        site_id: int,
        status: JobStatus,
        *,
        build_path: str | None = None,
        log_trace: str | None = None,
    ) -> None:
        with session_scope(self.settings) as session:
            site = session.get(SiteGeneration, site_id)
            if site is None:
                return
            site.status = status
            if build_path is not None:
                site.build_path = build_path
            if log_trace is not None:
                site.log_trace = log_trace
            site.updated_at = utcnow()
            session.add(site)


def _slugify(value: str) -> str:
    """Produce a filesystem/URL-safe slug from a niche id."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "site"
