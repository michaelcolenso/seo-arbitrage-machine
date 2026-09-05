"""Validate the highest-priority Radar clusters with real Ahrefs metrics when available.

This script is intentionally safe for CI:
- it rebuilds the deterministic 1M universe in an isolated temporary ledger;
- it resolves REVIEW rows into opportunity clusters;
- it spends at most ``--limit`` Ahrefs representative-keyword calls;
- it never prints or persists the Ahrefs token;
- without a token it writes a BLOCKED artifact and exits successfully.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from dsf_core.config import Settings
from dsf_engine.opportunity_graph import OpportunityGraphStore
from dsf_scout.ahrefs import AhrefsEnricher
from dsf_scout.radar.enrichment import OpportunityResolver
from dsf_scout.radar.metric_enrichment import MetricQueueRunner
from dsf_scout.radar.runner import RadarRunner
from dsf_scout.radar.store import RadarStore


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    token = os.environ.get("AHREFS_API_TOKEN") or os.environ.get("DSF_AHREFS_API_TOKEN")
    if not token:
        _write(
            args.output,
            {
                "schema_version": 1,
                "status": "BLOCKED",
                "reason": "AHREFS_API_TOKEN repository secret is not configured",
                "requested_cluster_limit": args.limit,
                "verified_keyword_metrics": False,
            },
        )
        print("Ahrefs validation blocked: token not configured")
        return 0

    work = Path(tempfile.mkdtemp(prefix="dsf-top25-"))
    try:
        settings = Settings(data_dir=work, ahrefs_api_token=token)
        radar = RadarStore(settings)
        graph = OpportunityGraphStore(settings)
        run_id = "public-data-million-v1-top25-validation"

        started = time.perf_counter()
        RadarRunner(radar).scan_universe(
            name="public-data-million-v1-top25-validation",
            run_id=run_id,
            batch_size=5000,
            review_threshold=55.0,
        )
        resolution = OpportunityResolver(radar, graph).resolve_run(run_id, min_scan_score=55.0)
        report = MetricQueueRunner(
            radar_store=radar,
            graph_store=graph,
            ahrefs=AhrefsEnricher(settings),
        ).run(limit=args.limit)

        with graph._connect() as conn:  # repository-internal shared SQLite ledger
            rows = conn.execute(
                """
                SELECT q.id, q.cluster_key, q.keyword AS representative_keyword,
                       q.status AS metric_status, q.result_json,
                       c.keyword_count, c.max_scan_score, c.avg_scan_score,
                       c.readiness, n.label
                FROM metric_enrichment_queue q
                JOIN radar_opportunity_clusters c
                  ON c.run_id = q.run_id AND c.cluster_key = q.cluster_key
                JOIN opportunity_nodes n ON n.id = c.opportunity_node_id
                WHERE q.run_id = ?
                ORDER BY q.priority DESC, q.id ASC
                LIMIT ?
                """,
                (run_id, args.limit),
            ).fetchall()

        candidates: list[dict[str, Any]] = []
        with radar._connect() as conn:
            for row in rows:
                metric = json.loads(row["result_json"] or "{}")
                scored = conn.execute(
                    """
                    SELECT volume, cpc, kd, scan_score, business_score,
                           opportunity_score, decision, metrics_source
                    FROM radar_keywords
                    WHERE run_id = ? AND keyword = ?
                    """,
                    (run_id, row["representative_keyword"]),
                ).fetchone()
                candidates.append(
                    {
                        "cluster_key": row["cluster_key"],
                        "label": row["label"],
                        "representative_keyword": row["representative_keyword"],
                        "keyword_count": row["keyword_count"],
                        "prior_max_scan_score": row["max_scan_score"],
                        "prior_avg_scan_score": row["avg_scan_score"],
                        "readiness": row["readiness"],
                        "metric_status": row["metric_status"],
                        "verified_metrics": metric,
                        "rescored": None
                        if scored is None
                        else {
                            "volume": scored["volume"],
                            "cpc_usd": scored["cpc"],
                            "keyword_difficulty": scored["kd"],
                            "scan_score": scored["scan_score"],
                            "business_score": scored["business_score"],
                            "opportunity_score": scored["opportunity_score"],
                            "decision": scored["decision"],
                            "metrics_source": scored["metrics_source"],
                        },
                    }
                )

        _write(
            args.output,
            {
                "schema_version": 1,
                "status": "COMPLETED",
                "verified_keyword_metrics": report.verified > 0,
                "provider": "ahrefs:v3",
                "requested_cluster_limit": args.limit,
                "api_calls_attempted": report.attempted,
                "verified": report.verified,
                "empty": report.empty,
                "failed": report.failed,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "resolution": {
                    "reviewed_keywords": resolution.reviewed_keywords,
                    "clusters": resolution.clusters,
                    "metric_queue": resolution.metric_queue,
                },
                "candidates": candidates,
            },
        )
        print(
            json.dumps(
                {
                    "attempted": report.attempted,
                    "verified": report.verified,
                    "empty": report.empty,
                    "failed": report.failed,
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
