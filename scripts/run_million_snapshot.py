"""Execute the canonical 1M Radar universe and emit a compact reproducibility snapshot."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from pathlib import Path

from dsf_core.config import Settings
from dsf_engine.opportunity_graph import OpportunityGraphStore
from dsf_scout.radar.enrichment import OpportunityResolver
from dsf_scout.radar.runner import RadarRunner
from dsf_scout.radar.store import RadarStore
from dsf_scout.radar.universe import FAMILIES, UNIVERSE_SIZE


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    work = Path(tempfile.mkdtemp(prefix="dsf-million-"))
    try:
        settings = Settings(data_dir=work)
        radar = RadarStore(settings)
        graph = OpportunityGraphStore(settings)
        runner = RadarRunner(radar)
        run_id = "public-data-million-v1"
        started = time.perf_counter()
        runner.scan_universe(
            name="public-data-million-v1",
            run_id=run_id,
            batch_size=5000,
            review_threshold=55.0,
        )
        resolver = OpportunityResolver(radar, graph)
        resolution = resolver.resolve_run(run_id, min_scan_score=55.0)
        elapsed = time.perf_counter() - started
        summary = radar.get_summary(run_id)
        if summary is None:
            raise RuntimeError("million scan did not produce a summary")

        snapshot = {
            "schema_version": 1,
            "run_id": run_id,
            "universe": {
                "generator": "generated-public-data-universe:v1",
                "expected_rows": UNIVERSE_SIZE,
                "family_count": len(FAMILIES),
                "metrics_source": "deterministic-prior:v1",
                "metrics_verified": False,
                "business_evidence_verified": False,
            },
            "result": {
                "status": summary.status.value,
                "processed": summary.processed_count,
                "review": summary.review_count,
                "promoted": summary.promoted_count,
                "rejected": summary.rejected_count,
                "errors": summary.error_count,
                "spend_usd": summary.spend_usd,
                "checkpoint": summary.checkpoint,
                "elapsed_seconds": round(elapsed, 3),
            },
            "resolution": {
                "reviewed_keywords": resolution.reviewed_keywords,
                "clusters": resolution.clusters,
                "metric_queue": resolution.metric_queue,
                "skipped": resolution.skipped,
                "graph_counts": graph.graph_counts(),
                "top_clusters": graph.top_clusters(run_id, limit=20),
            },
            "invariants": {
                "generated_priors_may_promote": False,
                "provider_metric_checks_are_cluster_level": True,
                "paid_metric_calls_per_initial_pass": resolution.metric_queue,
            },
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(snapshot["result"], sort_keys=True))
        print(json.dumps(snapshot["resolution"]["graph_counts"], sort_keys=True))
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
