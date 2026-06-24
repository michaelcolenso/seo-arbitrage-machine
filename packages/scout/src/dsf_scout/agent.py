"""The Scout orchestrator: gather -> enrich -> score -> persist.

``ScoutAgent.run`` drives a single scouting pass and is the unit an MCP tool
(`dsf_run_arbitrage_scan`) would wrap.  It is agent-native by construction:

* Every pass is anchored to a :class:`~dsf_engine.models.ScoutJob` row whose
  ``status`` advances ``PENDING -> RUNNING -> COMPLETED/FAILED`` in the ledger.
* Per-source failures are isolated into structured reflections rather than
  aborting the whole pass.
* A fatal error sets the job to ``FAILED`` with a trace and returns an
  ``AGENT_ACTION_REQUIRED`` payload instead of raising into the caller.
"""

from __future__ import annotations

import json
import traceback
from typing import Any

from dsf_core.agent_bridge import AgentBridge
from dsf_core.config import Settings, get_settings
from dsf_core.telemetry import get_logger, log_event
from dsf_engine.models import ArbitrageOpportunity as OpportunityRecord
from dsf_engine.models import JobStatus, MonetizationVector, ScoutJob
from dsf_engine.models import utcnow
from dsf_engine.sqlite_engine import init_db, session_scope
from pydantic import BaseModel, Field

from .miner import ArbitrageMiner
from .models import ArbitrageOpportunity, MiningResult, RejectedCandidate
from .sources import CandidateSource, SourceError

_log = get_logger("scout.agent")

# Scoring fields that, when all present, mean a candidate needs no enrichment.
_SCORING_FIELDS = (
    "estimated_monthly_volume",
    "average_cpc",
    "keyword_difficulty",
    "estimated_lead_value",
    "uniqueness_potential_ratio",
)


class SourceReflection(BaseModel):
    """A per-source outcome surfaced for agent inspection."""

    source_id: str
    ok: bool
    candidate_count: int = 0
    error: str | None = None


class ScoutRunReport(BaseModel):
    """The structured result of a scouting pass (MCP-tool friendly)."""

    status: str
    scout_job_id: int | None = None
    seed_niche: str
    accepted: list[ArbitrageOpportunity] = Field(default_factory=list)
    rejected: list[RejectedCandidate] = Field(default_factory=list)
    persisted_ids: list[int] = Field(default_factory=list)
    sources: list[SourceReflection] = Field(default_factory=list)
    error_type: str | None = None
    message: str | None = None


class ScoutAgent:
    """Coordinates candidate sources, the Agent Bridge, and the miner."""

    def __init__(
        self,
        sources: list[CandidateSource],
        *,
        settings: Settings | None = None,
        miner: ArbitrageMiner | None = None,
        bridge: AgentBridge | None = None,
    ) -> None:
        if not sources:
            raise ValueError("ScoutAgent requires at least one candidate source")
        self.sources = sources
        self.settings = settings or get_settings()
        self.miner = miner or ArbitrageMiner()
        self.bridge = bridge or AgentBridge(self.settings)

    def run(self, seed_niche: str) -> ScoutRunReport:
        """Execute one full scouting pass for ``seed_niche``."""
        init_db(self.settings)
        job_id = self._create_job(seed_niche)

        try:
            candidates, reflections = self._gather(seed_niche)
            enriched = [self._enrich(c) for c in candidates]
            result: MiningResult = self.miner.evaluate_candidates(enriched)
            persisted_ids = self._persist(job_id, result)
            self._mark_job(job_id, JobStatus.COMPLETED, log_trace=None)
            log_event(
                _log,
                "scout.run.completed",
                job_id=job_id,
                accepted=result.accepted_count,
                rejected=result.rejected_count,
            )
            return ScoutRunReport(
                status="COMPLETED",
                scout_job_id=job_id,
                seed_niche=seed_niche,
                accepted=result.accepted,
                rejected=result.rejected,
                persisted_ids=persisted_ids,
                sources=reflections,
            )
        except Exception as exc:  # noqa: BLE001 — convert to a reflection payload
            trace = traceback.format_exc()
            self._mark_job(job_id, JobStatus.FAILED, log_trace=trace)
            log_event(
                _log, "scout.run.failed", level=40, job_id=job_id, error=str(exc)
            )
            return ScoutRunReport(
                status="AGENT_ACTION_REQUIRED",
                scout_job_id=job_id,
                seed_niche=seed_niche,
                error_type=type(exc).__name__,
                message=str(exc),
            )

    # -- pipeline stages ---------------------------------------------------

    def _gather(
        self, seed_niche: str
    ) -> tuple[list[dict[str, Any]], list[SourceReflection]]:
        """Collect candidates from every source, isolating per-source failures."""
        pool: list[dict[str, Any]] = []
        reflections: list[SourceReflection] = []
        for source in self.sources:
            try:
                found = source.discover(seed_niche)
            except SourceError as exc:
                reflections.append(
                    SourceReflection(source_id=source.source_id, ok=False, error=str(exc))
                )
                log_event(
                    _log,
                    "scout.source.failed",
                    level=30,
                    source=source.source_id,
                    error=str(exc),
                )
                continue
            pool.extend(found)
            reflections.append(
                SourceReflection(
                    source_id=source.source_id, ok=True, candidate_count=len(found)
                )
            )
        return pool, reflections

    def _enrich(self, candidate: dict[str, Any]) -> dict[str, Any]:
        """Fill missing scoring fields via the Agent Bridge (mock-aware)."""
        if all(field in candidate for field in _SCORING_FIELDS):
            return candidate
        response = self.bridge.request("keyword_metrics", {"candidate": candidate})
        if not response.ok:
            log_event(
                _log,
                "scout.enrich.skipped",
                level=30,
                niche_id=candidate.get("niche_id"),
                error=response.error,
            )
            return candidate
        merged = dict(candidate)
        for key, value in response.result.items():
            merged.setdefault(key, value)
        return merged

    def _persist(self, job_id: int, result: MiningResult) -> list[int]:
        """Write accepted opportunities to the ledger; return their row ids."""
        persisted: list[int] = []
        with session_scope(self.settings) as session:
            for opp in result.accepted:
                record = OpportunityRecord(
                    scout_job_id=job_id,
                    niche_id=opp.niche_id,
                    target_dataset_url=opp.target_dataset_url,
                    primary_keywords=json.dumps(opp.primary_keywords),
                    estimated_monthly_volume=opp.estimated_monthly_volume,
                    average_cpc=opp.average_cpc,
                    keyword_difficulty=opp.keyword_difficulty,
                    data_sources_available=json.dumps(opp.data_sources_available),
                    monetization_vector=MonetizationVector(opp.monetization_vector.value),
                    estimated_lead_value=opp.estimated_lead_value,
                    uniqueness_potential_ratio=opp.uniqueness_potential_ratio,
                    arbitrage_score=opp.arbitrage_score,
                    source=opp.source,
                    status=JobStatus.PENDING,
                )
                session.add(record)
                session.flush()
                if record.id is not None:
                    persisted.append(record.id)
        return persisted

    # -- ledger helpers ----------------------------------------------------

    def _create_job(self, seed_niche: str) -> int:
        with session_scope(self.settings) as session:
            job = ScoutJob(seed_niche=seed_niche, status=JobStatus.RUNNING)
            session.add(job)
            session.flush()
            job_id = job.id
        if job_id is None:
            raise RuntimeError("failed to allocate a ScoutJob id")
        return job_id

    def _mark_job(self, job_id: int, status: JobStatus, *, log_trace: str | None) -> None:
        with session_scope(self.settings) as session:
            job = session.get(ScoutJob, job_id)
            if job is None:
                return
            job.status = status
            job.log_trace = log_trace
            job.updated_at = utcnow()
            session.add(job)
