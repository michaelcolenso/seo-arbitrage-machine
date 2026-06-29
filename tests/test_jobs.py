"""Tests for the durable, recoverable background JobManager."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from dsf_api.jobs import JobManager
from dsf_core.config import reload_settings
from dsf_engine.models import Job
from dsf_engine.sqlite_engine import session_scope
from sqlmodel import select


def _handlers(record: list[str] | None = None):
    def ok(params):
        if record is not None:
            record.append(params.get("tag", "ran"))
        return {"echo": params}

    def boom(params):
        raise RuntimeError("handler failed")

    return {"ok": ok, "boom": boom}


def test_submit_persists_and_succeeds(isolated_env: Path) -> None:
    settings = reload_settings()
    jm = JobManager(_handlers(), settings=settings, inline=True)
    rec = jm.submit("ok", {"tag": "x"})
    assert rec.status == "succeeded"
    assert rec.result == {"echo": {"tag": "x"}}
    # Persisted to the ledger.
    with session_scope(settings) as session:
        job = session.get(Job, rec.id)
    assert job is not None and job.status == "succeeded"


def test_failed_handler_records_error(isolated_env: Path) -> None:
    settings = reload_settings()
    jm = JobManager(_handlers(), settings=settings, inline=True)
    rec = jm.submit("boom")
    assert rec.status == "failed"
    assert "handler failed" in (rec.error or "")


def test_unknown_kind_rejected(isolated_env: Path) -> None:
    settings = reload_settings()
    jm = JobManager(_handlers(), settings=settings, inline=True)
    with pytest.raises(KeyError):
        jm.submit("does-not-exist")


def test_state_survives_a_new_manager(isolated_env: Path) -> None:
    settings = reload_settings()
    first = JobManager(_handlers(), settings=settings, inline=True)
    rec = first.submit("ok", {"tag": "persisted"})

    # Simulate a restart: a brand-new manager reads job state from the ledger.
    second = JobManager(_handlers(), settings=settings, inline=True)
    seen = second.get(rec.id)
    assert seen is not None
    assert seen.status == "succeeded"
    assert rec.id in {j.id for j in second.list()}


def test_recover_marks_running_as_interrupted(isolated_env: Path) -> None:
    settings = reload_settings()
    jm = JobManager(_handlers(), settings=settings, inline=True)
    # A job left 'running' by a dead process.
    with session_scope(settings) as session:
        session.add(Job(id="stuck", kind="ok", status="running", params="{}"))

    result = jm.recover()

    assert result["interrupted"] == 1
    after = jm.get("stuck")
    assert after is not None and after.status == "failed"
    assert "interrupted by restart" in (after.error or "")


def test_recover_reruns_queued_jobs(isolated_env: Path) -> None:
    settings = reload_settings()
    ran: list[str] = []
    jm = JobManager(_handlers(ran), settings=settings, inline=True)
    # A job that was queued but never started before the restart.
    with session_scope(settings) as session:
        session.add(
            Job(id="pending", kind="ok", status="queued", params=json.dumps({"tag": "resumed"}))
        )

    result = jm.recover()

    assert result["requeued"] == 1
    assert ran == ["resumed"]  # the handler actually ran on recovery
    after = jm.get("pending")
    assert after is not None and after.status == "succeeded"
