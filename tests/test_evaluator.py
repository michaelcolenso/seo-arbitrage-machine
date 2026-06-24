"""Tests for the Phase 3 Evaluator."""

from __future__ import annotations

from pathlib import Path

from dsf_core.config import reload_settings
from dsf_engine.evaluator import Evaluator
from dsf_engine.models import (
    ArbitrageOpportunity,
    Evaluation,
    EvaluationVerdict,
    JobStatus,
    MonetizationVector,
    TemplateType,
)
from dsf_engine.sqlite_engine import init_db, session_scope
from sqlmodel import select


def _insert_opportunity(settings, niche_id: str = "compliance_demo", status=JobStatus.PENDING) -> int:
    init_db(settings)
    with session_scope(settings) as session:
        opp = ArbitrageOpportunity(
            niche_id=niche_id,
            target_dataset_url="https://example.gov/dataset.csv",
            monetization_vector=MonetizationVector.LEAD_GEN,
            status=status,
        )
        session.add(opp)
        session.flush()
        opp_id = opp.id
    assert opp_id is not None
    return opp_id


_APPROVE_FIXTURE = {
    "monetization_pattern": "local_lead_generation",
    "architectural_layout": "directory",
    "confidence": 0.81,
    "seo_keyword_layout": {
        "route_pattern": "/{city}/{category}",
        "high_volume_columns": ["city", "category"],
        "sample_routes": ["/austin/solar-installers"],
    },
    "rationale": "geo + categorical columns support local directory routing",
}


def test_evaluator_approves_high_confidence(isolated_env: Path, write_mock) -> None:
    write_mock("evaluate", _APPROVE_FIXTURE)
    settings = reload_settings()
    opp_id = _insert_opportunity(settings)

    report = Evaluator(settings=settings).run()

    assert report.evaluated == 1
    assert report.approved == 1 and report.rejected == 0 and report.failed == 0

    with session_scope(settings) as session:
        evaluation = session.exec(select(Evaluation)).one()
        opp = session.get(ArbitrageOpportunity, opp_id)
    assert evaluation.verdict == EvaluationVerdict.APPROVED
    assert evaluation.template_type == TemplateType.DIRECTORY
    assert evaluation.seo_route_pattern == "/{city}/{category}"
    assert opp is not None and opp.status == JobStatus.COMPLETED


def test_evaluator_rejects_low_confidence(isolated_env: Path, write_mock) -> None:
    write_mock("evaluate", {**_APPROVE_FIXTURE, "confidence": 0.2})
    settings = reload_settings()
    _insert_opportunity(settings)

    report = Evaluator(settings=settings, min_confidence=0.5).run()

    assert report.rejected == 1 and report.approved == 0
    with session_scope(settings) as session:
        evaluation = session.exec(select(Evaluation)).one()
    assert evaluation.verdict == EvaluationVerdict.REJECTED


def test_evaluator_isolates_agent_failure(isolated_env: Path) -> None:
    # No "evaluate" mock fixture -> bridge returns ok=False -> opportunity FAILED.
    settings = reload_settings()
    opp_id = _insert_opportunity(settings)

    report = Evaluator(settings=settings).run()

    assert report.failed == 1 and report.approved == 0
    assert report.outcomes[0].status == "FAILED"
    assert report.outcomes[0].error is not None
    with session_scope(settings) as session:
        opp = session.get(ArbitrageOpportunity, opp_id)
        evaluations = list(session.exec(select(Evaluation)))
    assert opp is not None and opp.status == JobStatus.FAILED
    assert evaluations == []


def test_evaluator_only_processes_pending(isolated_env: Path, write_mock) -> None:
    write_mock("evaluate", _APPROVE_FIXTURE)
    settings = reload_settings()
    _insert_opportunity(settings, niche_id="already_done", status=JobStatus.COMPLETED)
    pending_id = _insert_opportunity(settings, niche_id="to_do", status=JobStatus.PENDING)

    report = Evaluator(settings=settings).run()

    assert report.evaluated == 1
    assert report.outcomes[0].opportunity_id == pending_id
    assert report.outcomes[0].niche_id == "to_do"


def test_evaluator_respects_limit(isolated_env: Path, write_mock) -> None:
    write_mock("evaluate", _APPROVE_FIXTURE)
    settings = reload_settings()
    _insert_opportunity(settings, niche_id="one")
    _insert_opportunity(settings, niche_id="two")

    report = Evaluator(settings=settings).run(limit=1)

    assert report.evaluated == 1
