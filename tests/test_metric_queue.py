"""Verify paid metric enrichment advances evidence without bypassing business gates."""

from __future__ import annotations

from pathlib import Path

from dsf_core.config import reload_settings
from dsf_engine.opportunity_graph import OpportunityGraphStore
from dsf_scout.radar.enrichment import OpportunityResolver
from dsf_scout.radar.metric_enrichment import MetricQueueRunner
from dsf_scout.radar.models import KeywordCandidate, RadarDecision
from dsf_scout.radar.scoring import score_candidate
from dsf_scout.radar.store import RadarStore
from dsf_scout.radar.universe import iter_keyword_universe


class _FakeAhrefs:
    def available(self) -> bool:
        return True

    def enrich(self, _candidate):
        return {
            "estimated_monthly_volume": 10000,
            "average_cpc": 5.0,
            "keyword_difficulty": 20,
        }


def test_verified_metric_still_waits_for_business_evidence(isolated_env: Path) -> None:
    settings = reload_settings()
    radar = RadarStore(settings)
    radar.create_run("metric-test", "metric-test", total_expected=1)
    candidate = next(
        c for c in iter_keyword_universe(limit=5000) if score_candidate(c).scan_score >= 55
    )
    initial = score_candidate(candidate)
    assert initial.decision == RadarDecision.REVIEW
    radar.save_batch("metric-test", [initial], checkpoint="1")

    graph = OpportunityGraphStore(settings)
    resolution = OpportunityResolver(radar, graph).resolve_run("metric-test")
    assert resolution.clusters == 1 and resolution.metric_queue == 1

    report = MetricQueueRunner(
        radar_store=radar,
        graph_store=graph,
        ahrefs=_FakeAhrefs(),  # type: ignore[arg-type]
    ).run(limit=1)
    assert report.verified == 1 and report.failed == 0

    with radar._connect() as conn:
        row = conn.execute(
            "SELECT decision, payload_json FROM radar_keywords WHERE run_id = 'metric-test'"
        ).fetchone()
    assert row is not None
    enriched = KeywordCandidate.model_validate_json(row["payload_json"])
    assert enriched.metrics_verified is True
    assert enriched.metrics_source == "ahrefs:v3"
    assert row["decision"] == "REVIEW"  # business evidence is still catalog-prior only

    clusters = graph.top_clusters("metric-test", limit=1)
    assert clusters[0]["readiness"] == "NEEDS_BUSINESS_VERIFICATION"
