"""Regression tests for the million-row universe and Opportunity Graph resolver."""

from __future__ import annotations

from pathlib import Path

from dsf_core.config import reload_settings
from dsf_engine.opportunity_graph import OpportunityGraphStore
from dsf_scout.radar.enrichment import OpportunityResolver
from dsf_scout.radar.models import RadarDecision
from dsf_scout.radar.runner import RadarRunner
from dsf_scout.radar.scoring import score_candidate
from dsf_scout.radar.store import RadarStore
from dsf_scout.radar.universe import UNIVERSE_SIZE, iter_keyword_universe


def test_universe_is_exactly_one_million_by_construction() -> None:
    assert UNIVERSE_SIZE == 1_000_000


def test_generated_universe_has_explicit_unverified_provenance() -> None:
    candidate = next(iter_keyword_universe(limit=1))
    assert candidate.metrics_source == "deterministic-prior:v1"
    assert candidate.metrics_verified is False
    assert candidate.business_evidence_verified is False
    assert candidate.family_id
    assert candidate.buyer


def test_generated_candidate_never_promotes_before_verification() -> None:
    candidates = list(iter_keyword_universe(limit=1000))
    strongest = max(candidates, key=lambda c: score_candidate(c).scan_score)
    scored = score_candidate(strongest)
    assert scored.scan_score >= 55
    assert scored.decision == RadarDecision.REVIEW
    assert any("unverified" in reason for reason in scored.reasons)


def test_resolver_collapses_5000_signals_into_five_buyer_clusters(isolated_env: Path) -> None:
    settings = reload_settings()
    store = RadarStore(settings)
    run_id = RadarRunner(store).scan_universe(
        name="small-universe",
        run_id="small-universe",
        max_rows=5000,
        batch_size=1000,
    )
    report = OpportunityResolver(store, OpportunityGraphStore(settings)).resolve_run(run_id)

    # The first 5,000 generated rows all belong to contractor-license, spanning
    # ten states and five buyer roles.  They should become five research jobs,
    # not thousands of provider/LLM calls.
    assert report.reviewed_keywords > 4000
    assert report.clusters == 5
    assert report.metric_queue == 5
    counts = OpportunityGraphStore(settings).graph_counts()
    assert counts["clusters"] == 5
    assert counts["metric_queue"] == 5
