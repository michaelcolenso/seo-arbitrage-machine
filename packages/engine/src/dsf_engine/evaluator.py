"""Phase 3 — the Monetisation & Opportunity Evaluator.

The Evaluator drains ``PENDING`` :class:`~dsf_engine.models.ArbitrageOpportunity`
rows from the ledger and, for each, runs a strict financial-evaluation loop
through the Agent Bridge.  The agent returns a verified structure describing:

1. **Monetisation pattern** — local lead-gen, contextual affiliation, or premium CPC.
2. **Architectural layout** — the ``directory`` or ``calculator`` Astro template.
3. **SEO keyword layout** — a static routing pattern over high-volume columns.

Each opportunity advances ``PENDING -> RUNNING -> COMPLETED`` (or ``FAILED`` on a
bridge/parse error).  The verdict (``APPROVED`` / ``REJECTED``) lives on the
persisted :class:`~dsf_engine.models.Evaluation` row, which Phase 4 consumes.
Failures are isolated per opportunity so one bad evaluation never aborts the batch.
"""

from __future__ import annotations

import json
import traceback
from typing import Any

from dsf_core.agent_bridge import AgentBridge
from dsf_core.config import Settings, get_settings
from dsf_core.telemetry import get_logger, log_event
from pydantic import BaseModel, Field, ValidationError
from sqlmodel import select

from .models import (
    ArbitrageOpportunity,
    Evaluation,
    EvaluationVerdict,
    JobStatus,
    MonetizationPattern,
    TemplateType,
    utcnow,
)
from .sqlite_engine import init_db, session_scope

_log = get_logger("engine.evaluator")


class SeoKeywordLayout(BaseModel):
    """Static routing layout derived from high-volume categorical/geographic columns."""

    route_pattern: str | None = None
    high_volume_columns: list[str] = Field(default_factory=list)
    sample_routes: list[str] = Field(default_factory=list)


class EvaluationResult(BaseModel):
    """The verified structure returned by the evaluating agent."""

    monetization_pattern: MonetizationPattern
    architectural_layout: TemplateType
    seo_keyword_layout: SeoKeywordLayout = Field(default_factory=SeoKeywordLayout)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str | None = None


class OpportunityOutcome(BaseModel):
    """Per-opportunity outcome surfaced for agent reflection / reporting."""

    opportunity_id: int
    niche_id: str
    status: str  # APPROVED / REJECTED / FAILED
    evaluation_id: int | None = None
    monetization_pattern: str | None = None
    template_type: str | None = None
    confidence: float | None = None
    error: str | None = None


class EvaluationReport(BaseModel):
    """Summary of an evaluation batch (MCP-tool friendly)."""

    status: str = "COMPLETED"
    evaluated: int = 0
    approved: int = 0
    rejected: int = 0
    failed: int = 0
    outcomes: list[OpportunityOutcome] = Field(default_factory=list)


class Evaluator:
    """Runs the Agent-Bridge financial-evaluation loop over pending opportunities."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        bridge: AgentBridge | None = None,
        min_confidence: float = 0.5,
    ) -> None:
        self.settings = settings or get_settings()
        self.bridge = bridge or AgentBridge(self.settings)
        self.min_confidence = min_confidence

    def run(self, limit: int | None = None) -> EvaluationReport:
        """Evaluate all ``PENDING`` opportunities; return a batch report."""
        init_db(self.settings)
        pending_ids = self._pending_opportunity_ids(limit)
        report = EvaluationReport()

        for opportunity_id in pending_ids:
            outcome = self._evaluate_one(opportunity_id)
            report.outcomes.append(outcome)
            report.evaluated += 1
            if outcome.status == "APPROVED":
                report.approved += 1
            elif outcome.status == "REJECTED":
                report.rejected += 1
            else:
                report.failed += 1

        log_event(
            _log,
            "evaluator.run.completed",
            evaluated=report.evaluated,
            approved=report.approved,
            rejected=report.rejected,
            failed=report.failed,
        )
        return report

    # -- single-opportunity pipeline --------------------------------------

    def _evaluate_one(self, opportunity_id: int) -> OpportunityOutcome:
        niche_id = self._mark_opportunity(opportunity_id, JobStatus.RUNNING)
        try:
            payload = self._build_payload(opportunity_id)
            response = self.bridge.request("evaluate", payload)
            if not response.ok:
                raise RuntimeError(f"agent evaluation failed: {response.error}")
            result = EvaluationResult(**response.result)
        except (ValidationError, RuntimeError, KeyError) as exc:
            trace = traceback.format_exc()
            self._mark_opportunity(opportunity_id, JobStatus.FAILED, log_trace=trace)
            log_event(
                _log,
                "evaluator.opportunity.failed",
                level=40,
                opportunity_id=opportunity_id,
                error=str(exc),
            )
            return OpportunityOutcome(
                opportunity_id=opportunity_id,
                niche_id=niche_id,
                status="FAILED",
                error=str(exc),
            )

        verdict = (
            EvaluationVerdict.APPROVED
            if result.confidence >= self.min_confidence
            else EvaluationVerdict.REJECTED
        )
        evaluation_id = self._persist_evaluation(opportunity_id, result, verdict)
        self._mark_opportunity(opportunity_id, JobStatus.COMPLETED)
        log_event(
            _log,
            "evaluator.opportunity.evaluated",
            opportunity_id=opportunity_id,
            verdict=verdict.value,
            confidence=result.confidence,
        )
        return OpportunityOutcome(
            opportunity_id=opportunity_id,
            niche_id=niche_id,
            status=verdict.value.upper(),
            evaluation_id=evaluation_id,
            monetization_pattern=result.monetization_pattern.value,
            template_type=result.architectural_layout.value,
            confidence=result.confidence,
        )

    # -- ledger access -----------------------------------------------------

    def _pending_opportunity_ids(self, limit: int | None) -> list[int]:
        with session_scope(self.settings) as session:
            statement = select(ArbitrageOpportunity.id).where(
                ArbitrageOpportunity.status == JobStatus.PENDING
            )
            if limit is not None:
                statement = statement.limit(limit)
            return [row for row in session.exec(statement) if row is not None]

    def _build_payload(self, opportunity_id: int) -> dict[str, Any]:
        with session_scope(self.settings) as session:
            record = session.get(ArbitrageOpportunity, opportunity_id)
            if record is None:
                raise KeyError(f"opportunity {opportunity_id} not found")
            return {
                "niche_id": record.niche_id,
                "target_dataset_url": record.target_dataset_url,
                "primary_keywords": json.loads(record.primary_keywords or "[]"),
                "data_sources_available": json.loads(record.data_sources_available or "[]"),
                "monetization_vector": record.monetization_vector.value,
                "estimated_monthly_volume": record.estimated_monthly_volume,
                "average_cpc": record.average_cpc,
                "estimated_lead_value": record.estimated_lead_value,
                "keyword_difficulty": record.keyword_difficulty,
            }

    def _persist_evaluation(
        self, opportunity_id: int, result: EvaluationResult, verdict: EvaluationVerdict
    ) -> int:
        with session_scope(self.settings) as session:
            evaluation = Evaluation(
                opportunity_id=opportunity_id,
                monetization_pattern=result.monetization_pattern,
                template_type=result.architectural_layout,
                seo_route_pattern=result.seo_keyword_layout.route_pattern,
                seo_high_volume_columns=json.dumps(
                    result.seo_keyword_layout.high_volume_columns
                ),
                seo_sample_routes=json.dumps(result.seo_keyword_layout.sample_routes),
                confidence=result.confidence,
                verdict=verdict,
                rationale=result.rationale,
            )
            session.add(evaluation)
            session.flush()
            evaluation_id = evaluation.id
        if evaluation_id is None:
            raise RuntimeError("failed to allocate an Evaluation id")
        return evaluation_id

    def _mark_opportunity(
        self, opportunity_id: int, status: JobStatus, *, log_trace: str | None = None
    ) -> str:
        """Set an opportunity's status; return its niche_id for reporting."""
        with session_scope(self.settings) as session:
            record = session.get(ArbitrageOpportunity, opportunity_id)
            if record is None:
                return "<unknown>"
            record.status = status
            record.updated_at = utcnow()
            session.add(record)
            return record.niche_id
