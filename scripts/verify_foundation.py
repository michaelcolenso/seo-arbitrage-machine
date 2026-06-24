#!/usr/bin/env python
"""Standalone foundation smoke test for DataSiteForge (Phase 0 + Phase 1).

Run via::

    uv run python scripts/verify_foundation.py

It exercises every foundation component end to end:

1. Load settings and force a clean, isolated data directory under ``data/tmp``.
2. Dispatch an Agent Bridge request in mock mode and assert the fixture round-trips.
3. Initialise the SQLite + DuckDB stores.
4. Insert and read back a ``ScoutJob`` (state machine round-trip).
5. Profile a generated CSV through the DuckDB broker (schema-discovery hook).

The script catches failures per stage, prints a clear PASS/FAIL ledger, cleans up
all resources, and exits non-zero on any failure.
"""

from __future__ import annotations

import csv
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _configure_isolated_env() -> None:
    """Point the platform at a throwaway data directory before importing modules."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="dsf-verify-", dir=REPO_ROOT / "data"))
    os.environ["DSF_DATA_DIR"] = str(tmp_dir)
    # Mirror the canonical mock fixtures into the isolated mock dir.
    os.environ["DSF_MOCK_DIR"] = str(REPO_ROOT / "data" / "mocks")
    os.environ["DSF_EXECUTION_MODE"] = "standalone"
    os.environ["DSF_IS_PRODUCTION"] = "false"
    os.environ["DSF_AGENT_TRANSPORT"] = "mock"


def main() -> int:
    _configure_isolated_env()

    # Imports happen after env setup so cached settings pick up the overrides.
    from dsf_core.agent_bridge import AgentBridge
    from dsf_core.config import get_settings
    from dsf_core.telemetry import get_console
    from dsf_engine.duckdb_engine import DuckDBBroker
    from dsf_engine.models import JobStatus, ScoutJob
    from dsf_engine.sqlite_engine import dispose_engine, init_db, session_scope

    console = get_console()
    settings = get_settings()
    results: list[tuple[str, bool, str]] = []
    broker: DuckDBBroker | None = None

    try:
        # --- Stage 1: settings ------------------------------------------
        assert settings.data_dir is not None, "data_dir failed to resolve"
        assert settings.sqlite_path is not None and settings.duckdb_path is not None
        results.append(("settings.resolve", True, str(settings.data_dir)))

        # --- Stage 2: agent bridge (mock) -------------------------------
        bridge = AgentBridge(settings)
        response = bridge.request("schema_discovery", {"probe": True})
        assert response.ok, f"agent bridge failed: {response.error}"
        assert response.transport == "mock", f"expected mock transport, got {response.transport}"
        assert "schema" in response.result, "mock fixture missing 'schema' key"
        results.append(("agent_bridge.mock", True, f"fields={len(response.result['schema']['fields'])}"))

        # --- Stage 3: db init -------------------------------------------
        init_db(settings)
        assert settings.sqlite_path is not None and settings.sqlite_path.is_file()
        results.append(("db.init", True, str(settings.sqlite_path)))

        # --- Stage 4: state machine round-trip --------------------------
        with session_scope(settings) as session:
            job = ScoutJob(seed_niche="solar installers", source_portal="data.gov")
            session.add(job)
            session.flush()
            job.status = JobStatus.COMPLETED
            new_id = job.id
        assert new_id is not None
        with session_scope(settings) as session:
            fetched = session.get(ScoutJob, new_id)
            assert fetched is not None, "ScoutJob did not persist"
            assert fetched.status == JobStatus.COMPLETED
            assert fetched.seed_niche == "solar installers"
        results.append(("sqlite.roundtrip", True, f"scout_job_id={new_id}"))

        # --- Stage 5: duckdb profiling ----------------------------------
        csv_path = settings.data_dir / "sample.csv"  # type: ignore[operator]
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["id", "name", "city", "rating"])
            writer.writerow([1, "Sunrun", "Austin", 4.5])
            writer.writerow([2, "Tesla Energy", "Denver", 4.7])
            writer.writerow([3, "SunPower", "Phoenix", 4.2])

        broker = DuckDBBroker(settings)
        profile = broker.profile_dataset(csv_path, limit=10)
        assert profile["row_count"] == 3, f"expected 3 rows, got {profile['row_count']}"
        assert profile["column_count"] == 4, f"expected 4 columns, got {profile['column_count']}"
        view = broker.register_file("sample_view", csv_path)
        top = broker.query(
            f"SELECT name FROM {view} ORDER BY rating DESC LIMIT 1"
        )
        assert top and top[0]["name"] == "Tesla Energy", f"unexpected top row: {top}"
        results.append(
            ("duckdb.profile", True, f"rows={profile['row_count']} cols={profile['column_count']}")
        )

    except Exception as exc:  # noqa: BLE001 — verification harness reports cleanly
        results.append(("FAILURE", False, f"{type(exc).__name__}: {exc}"))
    finally:
        if broker is not None:
            broker.close()
        dispose_engine()
        # Remove the throwaway data directory created for this run.
        if settings.data_dir is not None and settings.data_dir.exists():
            shutil.rmtree(settings.data_dir, ignore_errors=True)

    # --- Ledger ---------------------------------------------------------
    console.print("\n[bold]DataSiteForge foundation verification[/bold]")
    all_ok = True
    for stage, ok, detail in results:
        marker = "[green]PASS[/green]" if ok else "[red]FAIL[/red]"
        console.print(f"  {marker}  {stage:<22} {detail}")
        all_ok = all_ok and ok

    if all_ok:
        console.print("\n[bold green]All foundation checks passed.[/bold green]")
        return 0
    console.print("\n[bold red]Foundation verification failed.[/bold red]")
    return 1


if __name__ == "__main__":
    sys.exit(main())
