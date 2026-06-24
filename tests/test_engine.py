"""Tests for the SQLite state store and DuckDB analytics broker."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from dsf_core.config import reload_settings
from dsf_engine.duckdb_engine import DuckDBBroker, DuckDBError, reader_for
from dsf_engine.models import Deployment, JobStatus, ScoutJob
from dsf_engine.sqlite_engine import init_db, session_scope, table_counts


def test_init_db_creates_store(isolated_env: Path) -> None:
    settings = reload_settings()
    init_db(settings)
    assert settings.sqlite_path is not None and settings.sqlite_path.is_file()
    counts = table_counts(settings)
    assert counts["scout_jobs"] == 0
    assert "deployments" in counts


def test_scout_job_roundtrip(isolated_env: Path) -> None:
    settings = reload_settings()
    init_db(settings)
    with session_scope(settings) as session:
        job = ScoutJob(seed_niche="ev chargers", source_portal="data.gov")
        session.add(job)
        session.flush()
        job_id = job.id
    assert job_id is not None

    with session_scope(settings) as session:
        fetched = session.get(ScoutJob, job_id)
        assert fetched is not None
        assert fetched.seed_niche == "ev chargers"
        assert fetched.status == JobStatus.PENDING

    counts = table_counts(settings)
    assert counts["scout_jobs"] == 1


def test_session_scope_rolls_back_on_error(isolated_env: Path) -> None:
    settings = reload_settings()
    init_db(settings)
    with pytest.raises(ValueError):
        with session_scope(settings) as session:
            session.add(Deployment(project_slug="rollme"))
            session.flush()
            raise ValueError("force rollback")
    assert table_counts(settings)["deployments"] == 0


def test_duckdb_profile_and_register(isolated_env: Path) -> None:
    settings = reload_settings()
    csv_path = isolated_env / "data.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "name", "score"])
        writer.writerow([1, "alpha", 10])
        writer.writerow([2, "beta", 30])
        writer.writerow([3, "gamma", 20])

    broker = DuckDBBroker(settings)
    try:
        profile = broker.profile_dataset(csv_path, limit=2)
        assert profile["row_count"] == 3
        assert profile["column_count"] == 3
        assert len(profile["sample_rows"]) == 2
        column_names = [c["name"] for c in profile["columns"]]
        assert column_names == ["id", "name", "score"]

        view = broker.register_file("scored", csv_path)
        rows = broker.query(f"SELECT name FROM {view} ORDER BY score DESC")
        assert [r["name"] for r in rows] == ["beta", "gamma", "alpha"]
        assert broker.version()
    finally:
        broker.close()


def test_duckdb_rejects_unsupported_format(isolated_env: Path) -> None:
    bad = isolated_env / "data.xlsx"
    bad.write_text("not really excel", encoding="utf-8")
    with pytest.raises(DuckDBError):
        reader_for(bad)


def test_duckdb_rejects_bad_identifier(isolated_env: Path) -> None:
    settings = reload_settings()
    csv_path = isolated_env / "x.csv"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")
    broker = DuckDBBroker(settings)
    try:
        with pytest.raises(DuckDBError):
            broker.register_file("bad name; DROP TABLE", csv_path)
    finally:
        broker.close()
