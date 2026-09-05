"""Escalate representative opportunity-cluster keywords to verified provider metrics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from dsf_engine.opportunity_graph import OpportunityGraphStore
from dsf_scout.ahrefs import AhrefsEnricher, AhrefsError

from .models import KeywordCandidate
from .scoring import score_candidate
from .store import RadarStore, _now


@dataclass(frozen=True)
class MetricEnrichmentReport:
    attempted: int
    verified: int
    empty: int
    failed: int


class MetricQueueRunner:
    """Process cluster representatives with a paid/verified keyword provider."""

    def __init__(
        self,
        *,
        radar_store: RadarStore | None = None,
        graph_store: OpportunityGraphStore | None = None,
        ahrefs: AhrefsEnricher | None = None,
    ) -> None:
        self.radar = radar_store or RadarStore()
        self.graph = graph_store or OpportunityGraphStore(self.radar.settings)
        self.ahrefs = ahrefs or AhrefsEnricher(self.radar.settings)

    def run(self, *, limit: int = 200) -> MetricEnrichmentReport:
        self.graph.init_schema()
        if not self.ahrefs.available():
            raise AhrefsError("AHREFS_API_TOKEN is not configured")

        with self.graph._connect() as conn:
            pending = conn.execute(
                """
                SELECT id, run_id, cluster_key, keyword, provider
                FROM metric_enrichment_queue
                WHERE status = 'PENDING' AND provider = 'ahrefs'
                ORDER BY priority DESC, id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        attempted = verified = empty = failed = 0
        for row in pending:
            attempted += 1
            queue_id = int(row["id"])
            keyword = str(row["keyword"])
            cluster_key = str(row["cluster_key"])
            run_id = str(row["run_id"])
            self._mark_queue(queue_id, "RUNNING")
            try:
                metrics = self.ahrefs.enrich(
                    {"niche_id": cluster_key, "primary_keywords": [keyword]}
                )
                if not metrics:
                    empty += 1
                    self._mark_queue(queue_id, "EMPTY", result={})
                    continue
                self._apply_metrics(run_id, keyword, metrics)
                self._attach_metric_evidence(run_id, cluster_key, keyword, metrics)
                self._mark_queue(queue_id, "VERIFIED", result=metrics)
                verified += 1
            except (AhrefsError, ValueError, KeyError) as exc:
                failed += 1
                self._mark_queue(queue_id, "FAILED", result={"error": str(exc)})

        return MetricEnrichmentReport(
            attempted=attempted, verified=verified, empty=empty, failed=failed
        )

    def _apply_metrics(self, run_id: str, keyword: str, metrics: dict[str, Any]) -> None:
        with self.radar._connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM radar_keywords WHERE run_id = ? AND keyword = ?",
                (run_id, keyword),
            ).fetchone()
            if row is None:
                raise KeyError(f"Radar keyword not found: {keyword}")
            candidate = KeywordCandidate.model_validate_json(row["payload_json"])
            candidate.volume = int(metrics["estimated_monthly_volume"])
            candidate.cpc = float(metrics["average_cpc"])
            candidate.kd = float(metrics["keyword_difficulty"])
            candidate.metrics_source = "ahrefs:v3"
            candidate.metrics_verified = True
            rescored = score_candidate(candidate)
            conn.execute(
                """
                UPDATE radar_keywords SET
                    volume = ?, cpc = ?, kd = ?, scan_score = ?, business_score = ?,
                    opportunity_score = ?, decision = ?, reasons_json = ?, payload_json = ?, scored_at = ?
                WHERE run_id = ? AND keyword = ?
                """,
                (
                    candidate.volume,
                    candidate.cpc,
                    candidate.kd,
                    rescored.scan_score,
                    rescored.business_score,
                    rescored.opportunity_score,
                    rescored.decision.value,
                    json.dumps(rescored.reasons),
                    candidate.model_dump_json(),
                    rescored.scored_at.isoformat(),
                    run_id,
                    keyword,
                ),
            )

    def _attach_metric_evidence(
        self,
        run_id: str,
        cluster_key: str,
        keyword: str,
        metrics: dict[str, Any],
    ) -> None:
        metric_id = self.graph.upsert_node(
            "keyword_metric",
            f"ahrefs|{keyword.lower()}",
            keyword,
            confidence=1.0,
            source="ahrefs:v3",
            payload=metrics,
        )
        with self.graph._connect() as conn:
            cluster = conn.execute(
                """
                SELECT opportunity_node_id FROM radar_opportunity_clusters
                WHERE run_id = ? AND cluster_key = ?
                """,
                (run_id, cluster_key),
            ).fetchone()
            if cluster is None:
                raise KeyError(f"opportunity cluster not found: {cluster_key}")
            opportunity_id = int(cluster["opportunity_node_id"])
            conn.execute(
                """
                UPDATE radar_opportunity_clusters
                SET readiness = 'NEEDS_BUSINESS_VERIFICATION', updated_at = ?
                WHERE run_id = ? AND cluster_key = ?
                """,
                (_now(), run_id, cluster_key),
            )
        self.graph.upsert_edge(
            opportunity_id,
            metric_id,
            "HAS_VERIFIED_KEYWORD_METRIC",
            confidence=1.0,
            evidence={"run_id": run_id, "keyword": keyword},
        )

    def _mark_queue(
        self,
        queue_id: int,
        status: str,
        *,
        result: dict[str, Any] | None = None,
    ) -> None:
        with self.graph._connect() as conn:
            conn.execute(
                """
                UPDATE metric_enrichment_queue
                SET status = ?, attempts = attempts + ?, result_json = COALESCE(?, result_json),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    1 if status == "RUNNING" else 0,
                    None if result is None else json.dumps(result, sort_keys=True),
                    _now(),
                    queue_id,
                ),
            )
