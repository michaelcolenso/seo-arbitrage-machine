"""In-process background job worker for long-running lifecycle actions.

Scouting, compilation, deployment, and optimization can take a while, so the API
submits them to a thread-pool and returns a ``job_id`` the operator can poll.
Each job runs a ``Callable[[], dict]`` (an orchestrator returning its structured
report) and records ``queued -> running -> succeeded/failed`` with the result.

``inline=True`` runs jobs synchronously in :meth:`submit` — used in tests so
behaviour is deterministic without polling.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

JobFn = Callable[[], dict[str, Any]]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobRecord(BaseModel):
    """The observable state of a background job."""

    id: str
    kind: str
    status: str = "queued"  # queued / running / succeeded / failed
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class JobManager:
    """Thread-safe registry + executor for background jobs."""

    def __init__(self, *, inline: bool = False, max_workers: int = 4) -> None:
        self._inline = inline
        self._executor = None if inline else ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def submit(self, kind: str, fn: JobFn) -> JobRecord:
        """Register a job and run it (inline now, or on the thread pool)."""
        job_id = uuid.uuid4().hex
        record = JobRecord(id=job_id, kind=kind)
        with self._lock:
            self._jobs[job_id] = record
        if self._inline:
            self._run(job_id, fn)
        else:
            assert self._executor is not None
            self._executor.submit(self._run, job_id, fn)
        return self.get(job_id)  # type: ignore[return-value]

    def _run(self, job_id: str, fn: JobFn) -> None:
        self._update(job_id, status="running", started_at=_utcnow())
        try:
            result = fn()
            self._update(
                job_id, status="succeeded", finished_at=_utcnow(), result=result
            )
        except Exception as exc:  # noqa: BLE001 — surfaced on the job record
            self._update(
                job_id, status="failed", finished_at=_utcnow(), error=str(exc)
            )

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return
            self._jobs[job_id] = record.model_copy(update=changes)

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, limit: int = 50) -> list[JobRecord]:
        with self._lock:
            records = sorted(self._jobs.values(), key=lambda r: r.created_at, reverse=True)
        return records[:limit]

    def shutdown(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False)
