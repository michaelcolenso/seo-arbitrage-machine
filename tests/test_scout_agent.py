"""End-to-end tests for the ScoutAgent orchestrator against the ledger."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dsf_core.config import reload_settings
from dsf_engine.models import ArbitrageOpportunity as OpportunityRecord
from dsf_engine.models import JobStatus, ScoutJob
from dsf_engine.sqlite_engine import session_scope
from dsf_scout.agent import ScoutAgent
from dsf_scout.sources import ManifestSource, SourceError
from sqlmodel import select


def _full_candidate(niche_id: str = "compliance_demo") -> dict[str, Any]:
    return {
        "niche_id": niche_id,
        "target_dataset_url": "https://example.gov/dataset.csv",
        "primary_keywords": ["compliance lookup"],
        "estimated_monthly_volume": 45000,
        "average_cpc": 14.50,
        "keyword_difficulty": 12,
        "data_sources_available": ["a", "b", "c"],
        "monetization_vector": "LEAD_GEN",
        "estimated_lead_value": 175.00,
        "uniqueness_potential_ratio": 0.82,
    }


def _write_manifest(data_dir: Path, candidates: list[dict[str, Any]]) -> Path:
    path = data_dir / "manifest.json"
    path.write_text(json.dumps({"candidates": candidates}), encoding="utf-8")
    return path


class _PartialSource:
    """A stub source returning a candidate that needs Agent Bridge enrichment."""

    source_id = "partial"

    def discover(self, seed_niche: str) -> list[dict[str, Any]]:
        return [
            {
                "niche_id": "partial_candidate",
                "target_dataset_url": "https://example.gov/partial.csv",
                "data_sources_available": ["x", "y", "z"],
                "source": self.source_id,
            }
        ]


class _ExpectedFailureSource:
    """A source that fails in the expected (isolated) way."""

    source_id = "flaky"

    def discover(self, seed_niche: str) -> list[dict[str, Any]]:
        raise SourceError("portal timed out")


class _FatalSource:
    """A source raising an unexpected error (drives the fatal reflection path)."""

    source_id = "fatal"

    def discover(self, seed_niche: str) -> list[dict[str, Any]]:
        raise RuntimeError("unexpected boom")


def test_run_persists_accepted_opportunities(isolated_env: Path) -> None:
    settings = reload_settings()
    manifest = _write_manifest(isolated_env, [_full_candidate("a"), _full_candidate("b")])
    agent = ScoutAgent([ManifestSource(manifest)], settings=settings)

    report = agent.run("compliance")

    assert report.status == "COMPLETED"
    assert len(report.accepted) == 2
    assert len(report.persisted_ids) == 2

    with session_scope(settings) as session:
        records = list(session.exec(select(OpportunityRecord)))
        job = session.get(ScoutJob, report.scout_job_id)
    assert len(records) == 2
    assert job is not None and job.status == JobStatus.COMPLETED
    assert all(r.scout_job_id == report.scout_job_id for r in records)


def test_run_enriches_partial_candidate_via_bridge(isolated_env: Path, write_mock) -> None:
    # The mock bridge returns these enrichment values for partial candidates.
    write_mock(
        "keyword_metrics",
        {
            "estimated_monthly_volume": 8200,
            "average_cpc": 7.40,
            "keyword_difficulty": 22,
            "monetization_vector": "LEAD_GEN",
            "estimated_lead_value": 95.00,
            "uniqueness_potential_ratio": 0.68,
        },
    )
    settings = reload_settings()
    agent = ScoutAgent([_PartialSource()], settings=settings)

    report = agent.run("compliance")

    assert report.status == "COMPLETED"
    assert len(report.accepted) == 1
    opp = report.accepted[0]
    assert opp.estimated_monthly_volume == 8200
    assert opp.uniqueness_potential_ratio == 0.68


def test_expected_source_failure_is_isolated(isolated_env: Path) -> None:
    settings = reload_settings()
    manifest = _write_manifest(isolated_env, [_full_candidate("a")])
    agent = ScoutAgent(
        [ManifestSource(manifest), _ExpectedFailureSource()], settings=settings
    )

    report = agent.run("compliance")

    assert report.status == "COMPLETED"  # the working source still produced results
    assert len(report.accepted) == 1
    reflections = {r.source_id: r for r in report.sources}
    assert reflections["flaky"].ok is False
    assert "timed out" in (reflections["flaky"].error or "")
    assert reflections["manifest"].ok is True


def test_fatal_error_returns_reflection_and_fails_job(isolated_env: Path) -> None:
    settings = reload_settings()
    agent = ScoutAgent([_FatalSource()], settings=settings)

    report = agent.run("compliance")

    assert report.status == "AGENT_ACTION_REQUIRED"
    assert report.error_type == "RuntimeError"
    assert "boom" in (report.message or "")

    with session_scope(settings) as session:
        job = session.get(ScoutJob, report.scout_job_id)
    assert job is not None
    assert job.status == JobStatus.FAILED
    assert job.log_trace is not None
