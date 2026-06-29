"""Durable background job worker for long-running lifecycle actions.

The API submits scouting, compilation, deployment, and optimization runs to a
thread pool and returns a ``job_id`` the operator can poll.  Every job is
**persisted to the SQLite ledger** (the ``jobs`` table), so its state and history
survive a process restart — satisfying the platform's durable-state principle.

Jobs are dispatched by ``kind`` through a registry of handlers
(``Callable[[dict], dict]``) that reconstruct the work from JSON-serialisable
params.  Because params are durable (unlike a Python closure), a restart can
**recover** orphaned jobs: queued ones (never started) are re-run, and running
ones (whose thread died) are flagged ``failed`` as interrupted.

``inline=True`` runs jobs synchronously in :meth:`submit` for deterministic tests.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from dsf_core.config import Settings, get_settings
from dsf_core.telemetry import get_logger, log_event
from dsf_engine.models import Job
from dsf_engine.sqlite_engine import init_db, session_scope
from pydantic import BaseModel, Field
from sqlmodel import select

_log = get_logger("api.jobs")

JobHandler = Callable[[dict[str, Any]], dict[str, Any]]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobRecord(BaseModel):
    """The observable state of a background job (API response shape)."""

    id: str
    kind: str
    status: str = "queued"  # queued / running / succeeded / failed
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


def _to_record(job: Job) -> JobRecord:
    return JobRecord(
        id=job.id,
        kind=job.kind,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        result=json.loads(job.result) if job.result else None,
        error=job.error,
    )


class JobManager:
    """Thread-pool worker whose job state is persisted to the ledger."""

    def __init__(
        self,
        handlers: dict[str, JobHandler],
        *,
        settings: Settings | None = None,
        inline: bool = False,
        max_workers: int = 4,
    ) -> None:
        self.handlers = handlers
        self.settings = settings or get_settings()
        self._inline = inline
        self._executor = None if inline else ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()
        init_db(self.settings)

    # -- submission --------------------------------------------------------

    def submit(self, kind: str, params: dict[str, Any] | None = None) -> JobRecord:
        """Register a job and run it (inline now, or on the thread pool)."""
        if kind not in self.handlers:
            raise KeyError(f"unknown job kind: {kind}")
        job_id = uuid.uuid4().hex
        params = params or {}
        with session_scope(self.settings) as session:
            session.add(Job(id=job_id, kind=kind, status="queued", params=json.dumps(params)))
        self._dispatch(job_id, kind, params)
        record = self.get(job_id)
        assert record is not None
        return record

    def _dispatch(self, job_id: str, kind: str, params: dict[str, Any]) -> None:
        if self._inline:
            self._run(job_id, kind, params)
        else:
            assert self._executor is not None
            self._executor.submit(self._run, job_id, kind, params)

    def _run(self, job_id: str, kind: str, params: dict[str, Any]) -> None:
        self._update(job_id, status="running", started_at=_utcnow())
        try:
            result = self.handlers[kind](params)
            self._update(
                job_id, status="succeeded", finished_at=_utcnow(), result=json.dumps(result)
            )
        except Exception as exc:  # noqa: BLE001 — surfaced on the job record
            self._update(job_id, status="failed", finished_at=_utcnow(), error=str(exc))

    # -- recovery ----------------------------------------------------------

    def recover(self) -> dict[str, int]:
        """Reconcile orphaned jobs after a restart.

        Jobs left ``running`` when the process died are flagged ``failed``
        (their thread is gone); jobs still ``queued`` (never started) are re-run.
        """
        requeued = 0
        interrupted = 0
        with session_scope(self.settings) as session:
            orphaned = list(
                session.exec(select(Job).where(Job.status.in_(["queued", "running"])))  # type: ignore[attr-defined]
            )
        for job in orphaned:
            if job.status == "running":
                self._update(
                    job.id, status="failed", finished_at=_utcnow(),
                    error="interrupted by restart",
                )
                interrupted += 1
            elif job.kind in self.handlers:
                params = json.loads(job.params or "{}")
                self._dispatch(job.id, job.kind, params)
                requeued += 1
        if requeued or interrupted:
            log_event(_log, "jobs.recover", requeued=requeued, interrupted=interrupted)
        return {"requeued": requeued, "interrupted": interrupted}

    # -- reads -------------------------------------------------------------

    def get(self, job_id: str) -> JobRecord | None:
        with session_scope(self.settings) as session:
            job = session.get(Job, job_id)
            return _to_record(job) if job is not None else None

    def list(self, limit: int = 50) -> list[JobRecord]:
        with session_scope(self.settings) as session:
            jobs = list(
                session.exec(
                    select(Job).order_by(Job.created_at.desc()).limit(limit)  # type: ignore[attr-defined]
                )
            )
        return [_to_record(job) for job in jobs]

    # -- internals ---------------------------------------------------------

    def _update(self, job_id: str, **changes: Any) -> None:
        with session_scope(self.settings) as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            for key, value in changes.items():
                setattr(job, key, value)
            session.add(job)

    def shutdown(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False)
