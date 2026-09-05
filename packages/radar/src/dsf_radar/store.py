"""SQLite-backed observable ledger for large Radar scans."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from dsf_core.config import Settings, get_settings

from .models import RadarDecision, ScanStatus, ScanSummary, ScoredCandidate


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RadarStore:
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
                CREATE TABLE IF NOT EXISTS radar_scan_runs (
                    run_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_expected INTEGER,
                    processed_count INTEGER NOT NULL DEFAULT 0,
                    promoted_count INTEGER NOT NULL DEFAULT 0,
                    review_count INTEGER NOT NULL DEFAULT 0,
                    rejected_count INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    spend_usd REAL NOT NULL DEFAULT 0,
                    checkpoint TEXT,
                    config_json TEXT NOT NULL DEFAULT '{}',
                    source_snapshot TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS radar_keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES radar_scan_runs(run_id) ON DELETE CASCADE,
                    keyword TEXT NOT NULL,
                    source TEXT NOT NULL,
                    volume INTEGER NOT NULL DEFAULT 0,
                    cpc REAL NOT NULL DEFAULT 0,
                    kd REAL NOT NULL DEFAULT 100,
                    intent TEXT NOT NULL DEFAULT 'unknown',
                    buyer TEXT,
                    decision_value REAL,
                    monetization_ease REAL,
                    defensibility REAL,
                    complexity REAL,
                    data_leverage REAL,
                    evidence_quality REAL,
                    scan_score REAL NOT NULL,
                    business_score REAL,
                    opportunity_score REAL,
                    decision TEXT NOT NULL,
                    reasons_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    scored_at TEXT NOT NULL,
                    UNIQUE(run_id, keyword)
                );

                CREATE INDEX IF NOT EXISTS idx_radar_keywords_run_decision
                    ON radar_keywords(run_id, decision);
                CREATE INDEX IF NOT EXISTS idx_radar_keywords_run_opportunity
                    ON radar_keywords(run_id, opportunity_score DESC);
                CREATE INDEX IF NOT EXISTS idx_radar_keywords_run_scan
                    ON radar_keywords(run_id, scan_score DESC);
                """
            )

    def create_run(
        self,
        run_id: str,
        name: str,
        *,
        total_expected: int | None = None,
        config: dict | None = None,
        source_snapshot: str | None = None,
    ) -> None:
        self.init_schema()
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO radar_scan_runs
                    (run_id, name, status, total_expected, config_json, source_snapshot,
                     started_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    name,
                    ScanStatus.PENDING.value,
                    total_expected,
                    json.dumps(config or {}, sort_keys=True),
                    source_snapshot,
                    now,
                    now,
                ),
            )

    def mark_status(self, run_id: str, status: ScanStatus) -> None:
        completed_at = _now() if status in {ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.CANCELLED} else None
        with self._connect() as conn:
            conn.execute(
                """UPDATE radar_scan_runs
                   SET status = ?, completed_at = COALESCE(?, completed_at), updated_at = ?
                   WHERE run_id = ?""",
                (status.value, completed_at, _now(), run_id),
            )

    def has_keyword(self, run_id: str, keyword: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM radar_keywords WHERE run_id = ? AND keyword = ? LIMIT 1",
                (run_id, keyword),
            ).fetchone()
        return row is not None

    def save_batch(
        self,
        run_id: str,
        results: Iterable[ScoredCandidate],
        *,
        checkpoint: str | None = None,
        spend_delta_usd: float = 0.0,
    ) -> int:
        rows = list(results)
        if not rows:
            return 0

        inserted = 0
        promoted = review = rejected = 0
        with self._connect() as conn:
            for result in rows:
                c = result.candidate
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO radar_keywords (
                        run_id, keyword, source, volume, cpc, kd, intent, buyer,
                        decision_value, monetization_ease, defensibility, complexity,
                        data_leverage, evidence_quality, scan_score, business_score,
                        opportunity_score, decision, reasons_json, payload_json, scored_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        c.keyword,
                        c.source,
                        c.volume,
                        c.cpc,
                        c.kd,
                        c.intent,
                        c.buyer,
                        c.decision_value,
                        c.monetization_ease,
                        c.defensibility,
                        c.complexity,
                        c.data_leverage,
                        c.evidence_quality,
                        result.scan_score,
                        result.business_score,
                        result.opportunity_score,
                        result.decision.value,
                        json.dumps(result.reasons),
                        c.model_dump_json(),
                        result.scored_at.isoformat(),
                    ),
                )
                if cursor.rowcount != 1:
                    continue
                inserted += 1
                if result.decision == RadarDecision.PROMOTE:
                    promoted += 1
                elif result.decision == RadarDecision.REVIEW:
                    review += 1
                else:
                    rejected += 1

            conn.execute(
                """
                UPDATE radar_scan_runs SET
                    processed_count = processed_count + ?,
                    promoted_count = promoted_count + ?,
                    review_count = review_count + ?,
                    rejected_count = rejected_count + ?,
                    spend_usd = spend_usd + ?,
                    checkpoint = COALESCE(?, checkpoint),
                    updated_at = ?
                WHERE run_id = ?
                """,
                (
                    inserted,
                    promoted,
                    review,
                    rejected,
                    spend_delta_usd,
                    checkpoint,
                    _now(),
                    run_id,
                ),
            )
        return inserted

    def record_error(self, run_id: str, checkpoint: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE radar_scan_runs
                   SET error_count = error_count + 1,
                       checkpoint = COALESCE(?, checkpoint), updated_at = ?
                   WHERE run_id = ?""",
                (checkpoint, _now(), run_id),
            )

    def get_summary(self, run_id: str | None = None) -> ScanSummary | None:
        self.init_schema()
        with self._connect() as conn:
            if run_id:
                row = conn.execute(
                    "SELECT * FROM radar_scan_runs WHERE run_id = ?", (run_id,)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM radar_scan_runs ORDER BY started_at DESC LIMIT 1"
                ).fetchone()
        if row is None:
            return None
        return ScanSummary(
            run_id=row["run_id"],
            name=row["name"],
            status=ScanStatus(row["status"]),
            total_expected=row["total_expected"],
            processed_count=row["processed_count"],
            promoted_count=row["promoted_count"],
            review_count=row["review_count"],
            rejected_count=row["rejected_count"],
            error_count=row["error_count"],
            spend_usd=row["spend_usd"],
            checkpoint=row["checkpoint"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )

    def top_candidates(self, run_id: str, limit: int = 20) -> list[dict]:
        self.init_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT keyword, source, volume, cpc, kd, intent, buyer,
                       scan_score, business_score, opportunity_score, decision
                FROM radar_keywords
                WHERE run_id = ? AND decision IN ('PROMOTE', 'REVIEW')
                ORDER BY CASE WHEN decision = 'PROMOTE' THEN 0 ELSE 1 END,
                         COALESCE(opportunity_score, scan_score) DESC
                LIMIT ?
                """,
                (run_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]
