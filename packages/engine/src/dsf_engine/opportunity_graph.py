"""Durable generic Opportunity Graph backed by the canonical SQLite ledger."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dsf_core.config import Settings, get_settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OpportunityGraphStore:
    """Store datasets, buyers, decisions, products and opportunities as a graph.

    The graph is deliberately generic: new discovery systems can add node/edge
    types without schema migrations, while canonical keys prevent duplicates.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_directories()
        assert self.settings.sqlite_path is not None
        self.path = Path(self.settings.sqlite_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS opportunity_graph_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_type TEXT NOT NULL,
                    canonical_key TEXT NOT NULL,
                    label TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0,
                    source TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(node_type, canonical_key)
                );
                CREATE INDEX IF NOT EXISTS idx_og_nodes_type
                    ON opportunity_graph_nodes(node_type);

                CREATE TABLE IF NOT EXISTS opportunity_graph_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_node_id INTEGER NOT NULL REFERENCES opportunity_graph_nodes(id) ON DELETE CASCADE,
                    to_node_id INTEGER NOT NULL REFERENCES opportunity_graph_nodes(id) ON DELETE CASCADE,
                    relation TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0,
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(from_node_id, to_node_id, relation)
                );
                CREATE INDEX IF NOT EXISTS idx_og_edges_from ON opportunity_graph_edges(from_node_id);
                CREATE INDEX IF NOT EXISTS idx_og_edges_to ON opportunity_graph_edges(to_node_id);

                CREATE TABLE IF NOT EXISTS radar_opportunity_clusters (
                    run_id TEXT NOT NULL,
                    cluster_key TEXT NOT NULL,
                    opportunity_node_id INTEGER NOT NULL REFERENCES opportunity_graph_nodes(id) ON DELETE CASCADE,
                    keyword_count INTEGER NOT NULL DEFAULT 0,
                    max_scan_score REAL NOT NULL DEFAULT 0,
                    avg_scan_score REAL NOT NULL DEFAULT 0,
                    sample_keywords_json TEXT NOT NULL DEFAULT '[]',
                    readiness TEXT NOT NULL DEFAULT 'NEEDS_METRICS',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(run_id, cluster_key)
                );

                CREATE TABLE IF NOT EXISTS metric_enrichment_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    cluster_key TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'ahrefs',
                    priority REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(run_id, cluster_key, provider)
                );
                CREATE INDEX IF NOT EXISTS idx_metric_queue_status_priority
                    ON metric_enrichment_queue(status, priority DESC);
                """
            )

    def upsert_node(
        self,
        node_type: str,
        canonical_key: str,
        label: str,
        *,
        confidence: float = 0.0,
        source: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int:
        self.init_schema()
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO opportunity_graph_nodes
                    (node_type, canonical_key, label, confidence, source, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_type, canonical_key) DO UPDATE SET
                    label = excluded.label,
                    confidence = MAX(opportunity_graph_nodes.confidence, excluded.confidence),
                    source = COALESCE(excluded.source, opportunity_graph_nodes.source),
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    node_type, canonical_key, label, confidence, source,
                    json.dumps(payload or {}, sort_keys=True), now, now,
                ),
            )
            row = conn.execute(
                "SELECT id FROM opportunity_graph_nodes WHERE node_type = ? AND canonical_key = ?",
                (node_type, canonical_key),
            ).fetchone()
        if row is None:
            raise RuntimeError("failed to upsert opportunity graph node")
        return int(row["id"])

    def upsert_edge(
        self,
        from_node_id: int,
        to_node_id: int,
        relation: str,
        *,
        confidence: float = 0.0,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        self.init_schema()
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO opportunity_graph_edges
                    (from_node_id, to_node_id, relation, confidence, evidence_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(from_node_id, to_node_id, relation) DO UPDATE SET
                    confidence = MAX(opportunity_graph_edges.confidence, excluded.confidence),
                    evidence_json = excluded.evidence_json,
                    updated_at = excluded.updated_at
                """,
                (
                    from_node_id, to_node_id, relation, confidence,
                    json.dumps(evidence or {}, sort_keys=True), now, now,
                ),
            )

    def upsert_cluster(
        self,
        *,
        run_id: str,
        cluster_key: str,
        opportunity_node_id: int,
        keyword_count: int,
        max_scan_score: float,
        avg_scan_score: float,
        sample_keywords: list[str],
        readiness: str,
    ) -> None:
        self.init_schema()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO radar_opportunity_clusters
                    (run_id, cluster_key, opportunity_node_id, keyword_count, max_scan_score,
                     avg_scan_score, sample_keywords_json, readiness, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, cluster_key) DO UPDATE SET
                    opportunity_node_id = excluded.opportunity_node_id,
                    keyword_count = excluded.keyword_count,
                    max_scan_score = excluded.max_scan_score,
                    avg_scan_score = excluded.avg_scan_score,
                    sample_keywords_json = excluded.sample_keywords_json,
                    readiness = excluded.readiness,
                    updated_at = excluded.updated_at
                """,
                (
                    run_id, cluster_key, opportunity_node_id, keyword_count,
                    max_scan_score, avg_scan_score, json.dumps(sample_keywords), readiness, _now(),
                ),
            )

    def enqueue_metric_keyword(
        self,
        *,
        run_id: str,
        cluster_key: str,
        keyword: str,
        priority: float,
        provider: str = "ahrefs",
    ) -> None:
        self.init_schema()
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO metric_enrichment_queue
                    (run_id, cluster_key, keyword, provider, priority, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?)
                ON CONFLICT(run_id, cluster_key, provider) DO UPDATE SET
                    keyword = excluded.keyword,
                    priority = MAX(metric_enrichment_queue.priority, excluded.priority),
                    updated_at = excluded.updated_at
                """,
                (run_id, cluster_key, keyword, provider, priority, now, now),
            )

    def top_clusters(self, run_id: str, limit: int = 50) -> list[dict[str, Any]]:
        self.init_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT c.*, n.label, n.confidence, n.payload_json
                FROM radar_opportunity_clusters c
                JOIN opportunity_graph_nodes n ON n.id = c.opportunity_node_id
                WHERE c.run_id = ?
                ORDER BY c.max_scan_score DESC, c.keyword_count DESC
                LIMIT ?
                """,
                (run_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def graph_counts(self) -> dict[str, int]:
        self.init_schema()
        with self._connect() as conn:
            nodes = conn.execute("SELECT COUNT(*) AS n FROM opportunity_graph_nodes").fetchone()["n"]
            edges = conn.execute("SELECT COUNT(*) AS n FROM opportunity_graph_edges").fetchone()["n"]
            clusters = conn.execute("SELECT COUNT(*) AS n FROM radar_opportunity_clusters").fetchone()["n"]
            queued = conn.execute(
                "SELECT COUNT(*) AS n FROM metric_enrichment_queue WHERE status = 'PENDING'"
            ).fetchone()["n"]
        return {"nodes": int(nodes), "edges": int(edges), "clusters": int(clusters), "metric_queue": int(queued)}
