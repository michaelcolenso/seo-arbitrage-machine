"""Streaming execution engine for large keyword scans."""

from __future__ import annotations

import csv
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from .models import KeywordCandidate, ScanStatus
from .scoring import score_candidate
from .store import RadarStore


def _number(row: dict[str, str], *names: str, default: float = 0.0) -> float:
    for name in names:
        raw = row.get(name)
        if raw not in (None, ""):
            try:
                return float(str(raw).replace(",", "").strip())
            except ValueError:
                return default
    return default


def _optional_number(row: dict[str, str], name: str) -> float | None:
    raw = row.get(name)
    if raw in (None, ""):
        return None
    try:
        return float(str(raw).replace(",", "").strip())
    except ValueError:
        return None


def candidate_from_row(row: dict[str, str]) -> KeywordCandidate:
    keyword = (row.get("keyword") or row.get("query") or "").strip()
    return KeywordCandidate(
        keyword=keyword,
        source=(row.get("source") or "csv").strip() or "csv",
        volume=int(_number(row, "volume", "monthly_volume", "search_volume")),
        cpc=_number(row, "cpc", "cost_per_click"),
        kd=_number(row, "kd", "difficulty", "keyword_difficulty", default=100.0),
        intent=(row.get("intent") or "unknown").strip() or "unknown",
        buyer=(row.get("buyer") or "").strip() or None,
        decision_value=_optional_number(row, "decision_value"),
        monetization_ease=_optional_number(row, "monetization_ease"),
        defensibility=_optional_number(row, "defensibility"),
        complexity=_optional_number(row, "complexity"),
        data_leverage=_optional_number(row, "data_leverage"),
        evidence_quality=_optional_number(row, "evidence_quality"),
    )


class RadarRunner:
    def __init__(self, store: RadarStore | None = None) -> None:
        self.store = store or RadarStore()

    def scan_csv(
        self,
        csv_path: str | Path,
        *,
        name: str,
        run_id: str | None = None,
        total_expected: int | None = None,
        batch_size: int = 5000,
        max_rows: int | None = None,
        review_threshold: float = 55.0,
        promote_threshold: float = 65.0,
    ) -> str:
        path = Path(csv_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        run_id = run_id or uuid4().hex
        self.store.create_run(
            run_id,
            name,
            total_expected=total_expected,
            config={
                "batch_size": batch_size,
                "review_threshold": review_threshold,
                "promote_threshold": promote_threshold,
            },
            source_snapshot=str(path),
        )
        summary = self.store.get_summary(run_id)
        resume_after = int(summary.checkpoint) if summary and summary.checkpoint else 0
        self.store.mark_status(run_id, ScanStatus.RUNNING)

        batch = []
        last_row = resume_after
        accepted_this_call = 0
        hit_limit = False
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if not reader.fieldnames or not ({"keyword", "query"} & set(reader.fieldnames)):
                    raise ValueError("CSV must contain a 'keyword' or 'query' column")

                for row_number, row in enumerate(reader, start=1):
                    if row_number <= resume_after:
                        continue
                    if max_rows is not None and accepted_this_call >= max_rows:
                        hit_limit = True
                        break
                    last_row = row_number
                    try:
                        candidate = candidate_from_row(row)
                        result = score_candidate(
                            candidate,
                            review_threshold=review_threshold,
                            promote_threshold=promote_threshold,
                        )
                    except (ValidationError, ValueError):
                        # Do not advance the durable checkpoint independently of an
                        # unsaved batch: a crash here must replay preceding rows rather
                        # than silently skip valid candidates that were only in memory.
                        self.store.record_error(run_id)
                        continue

                    batch.append(result)
                    accepted_this_call += 1
                    if len(batch) >= batch_size:
                        self.store.save_batch(run_id, batch, checkpoint=str(row_number))
                        batch.clear()

            if batch:
                self.store.save_batch(run_id, batch, checkpoint=str(last_row))
            self.store.mark_status(
                run_id,
                ScanStatus.PENDING if hit_limit else ScanStatus.COMPLETED,
            )
            return run_id
        except Exception:
            if batch:
                self.store.save_batch(run_id, batch, checkpoint=str(last_row))
            self.store.record_error(run_id, checkpoint=str(last_row))
            self.store.mark_status(run_id, ScanStatus.FAILED)
            raise
