"""Collapse Radar REVIEW signals into business-shaped Opportunity Graph clusters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dsf_engine.opportunity_graph import OpportunityGraphStore
from pydantic import ValidationError

from .models import KeywordCandidate
from .store import RadarStore
from .universe import FAMILIES, OpportunityFamily, family_by_id


@dataclass
class _Cluster:
    family: OpportunityFamily
    buyer: str
    keyword_count: int = 0
    scan_sum: float = 0.0
    max_scan_score: float = 0.0
    top_keyword: str = ""
    samples: list[str] = field(default_factory=list)
    geographies: set[str] = field(default_factory=set)

    def add(self, keyword: str, scan_score: float, geography: str | None) -> None:
        self.keyword_count += 1
        self.scan_sum += scan_score
        if scan_score > self.max_scan_score:
            self.max_scan_score = scan_score
            self.top_keyword = keyword
        if len(self.samples) < 8:
            self.samples.append(keyword)
        if geography:
            self.geographies.add(geography)

    @property
    def avg_scan_score(self) -> float:
        return self.scan_sum / self.keyword_count if self.keyword_count else 0.0


@dataclass(frozen=True)
class ResolverReport:
    run_id: str
    reviewed_keywords: int
    clusters: int
    metric_queue: int
    skipped: int


class OpportunityResolver:
    """Turn a large REVIEW set into a small number of researchable business wedges."""

    def __init__(
        self,
        radar_store: RadarStore | None = None,
        graph_store: OpportunityGraphStore | None = None,
    ) -> None:
        self.radar = radar_store or RadarStore()
        self.graph = graph_store or OpportunityGraphStore(self.radar.settings)

    def resolve_run(
        self,
        run_id: str,
        *,
        min_scan_score: float = 55.0,
        max_keywords: int | None = None,
        metric_provider: str = "ahrefs",
    ) -> ResolverReport:
        """Cluster REVIEW rows by family + buyer and populate the Opportunity Graph.

        This is intentionally many-to-one: hundreds of thousands of keyword-shaped
        signals normally collapse into a few hundred buyer/product opportunities.
        """
        self.radar.init_schema()
        self.graph.init_schema()
        clusters: dict[str, _Cluster] = {}
        reviewed = skipped = 0

        with self.radar._connect() as conn:  # package-internal shared ledger access
            statement = """
                SELECT keyword, scan_score, payload_json
                FROM radar_keywords
                WHERE run_id = ? AND decision = 'REVIEW' AND scan_score >= ?
                ORDER BY scan_score DESC
            """
            params: list[Any] = [run_id, min_scan_score]
            if max_keywords is not None:
                statement += " LIMIT ?"
                params.append(max_keywords)
            rows = conn.execute(statement, tuple(params))
            for row in rows:
                reviewed += 1
                try:
                    candidate = KeywordCandidate.model_validate_json(row["payload_json"])
                except ValidationError:
                    skipped += 1
                    continue
                family = family_by_id(candidate.family_id) or _infer_family(candidate.keyword)
                if family is None:
                    skipped += 1
                    continue
                buyer = candidate.buyer or "unknown buyer"
                cluster_key = f"{family.id}|{_key(buyer)}"
                cluster = clusters.setdefault(cluster_key, _Cluster(family=family, buyer=buyer))
                cluster.add(candidate.keyword, float(row["scan_score"]), candidate.geography)

        for cluster_key, cluster in clusters.items():
            self._persist_cluster(
                run_id,
                cluster_key,
                cluster,
                metric_provider=metric_provider,
            )

        counts = self.graph.graph_counts()
        return ResolverReport(
            run_id=run_id,
            reviewed_keywords=reviewed,
            clusters=len(clusters),
            metric_queue=counts["metric_queue"],
            skipped=skipped,
        )

    def _persist_cluster(
        self,
        run_id: str,
        cluster_key: str,
        cluster: _Cluster,
        *,
        metric_provider: str,
    ) -> None:
        family = cluster.family
        confidence = min(0.90, 0.45 + family.score * 0.04)
        readiness = "NEEDS_METRICS" if family.data_source_name else "NEEDS_SOURCE_VALIDATION"
        payload = {
            "family_id": family.id,
            "research_prior_score": family.score,
            "buyer": cluster.buyer,
            "decision": family.decision,
            "product_pattern": family.product_pattern,
            "data_source_name": family.data_source_name,
            "data_source_url": family.data_source_url,
            "keyword_count": cluster.keyword_count,
            "max_scan_score": round(cluster.max_scan_score, 2),
            "avg_scan_score": round(cluster.avg_scan_score, 2),
            "geography_count": len(cluster.geographies),
            "sample_keywords": cluster.samples,
            "top_keyword": cluster.top_keyword,
            "evidence_state": "catalog-prior; keyword metrics still require provider verification",
        }
        opportunity_id = self.graph.upsert_node(
            "opportunity",
            cluster_key,
            f"{family.topic} for {cluster.buyer}",
            confidence=confidence,
            source="radar-resolver:v1",
            payload=payload,
        )
        dataset_id = self.graph.upsert_node(
            "dataset",
            family.id,
            family.data_source_name,
            confidence=confidence,
            source=family.data_source_url,
            payload={"url": family.data_source_url, "family_id": family.id},
        )
        buyer_id = self.graph.upsert_node(
            "buyer", _key(cluster.buyer), cluster.buyer, confidence=confidence, source="radar-resolver:v1"
        )
        decision_id = self.graph.upsert_node(
            "decision", family.id, family.decision, confidence=confidence, source="radar-resolver:v1"
        )
        product_id = self.graph.upsert_node(
            "product_pattern", family.id, family.product_pattern, confidence=confidence, source="radar-resolver:v1"
        )
        evidence = {
            "run_id": run_id,
            "keyword_count": cluster.keyword_count,
            "max_scan_score": round(cluster.max_scan_score, 2),
        }
        self.graph.upsert_edge(opportunity_id, dataset_id, "USES_DATASET", confidence=confidence, evidence=evidence)
        self.graph.upsert_edge(opportunity_id, buyer_id, "SERVES_BUYER", confidence=confidence, evidence=evidence)
        self.graph.upsert_edge(opportunity_id, decision_id, "IMPROVES_DECISION", confidence=confidence, evidence=evidence)
        self.graph.upsert_edge(opportunity_id, product_id, "PACKAGED_AS", confidence=confidence, evidence=evidence)
        self.graph.upsert_cluster(
            run_id=run_id,
            cluster_key=cluster_key,
            opportunity_node_id=opportunity_id,
            keyword_count=cluster.keyword_count,
            max_scan_score=cluster.max_scan_score,
            avg_scan_score=cluster.avg_scan_score,
            sample_keywords=cluster.samples,
            readiness=readiness,
        )
        self.graph.enqueue_metric_keyword(
            run_id=run_id,
            cluster_key=cluster_key,
            keyword=cluster.top_keyword,
            priority=cluster.max_scan_score + family.score,
            provider=metric_provider,
        )


def _infer_family(keyword: str) -> OpportunityFamily | None:
    lower = keyword.lower()
    return next((family for family in FAMILIES if family.topic.lower() in lower), None)


def _key(value: str) -> str:
    return "-".join(value.lower().strip().split())
