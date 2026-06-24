# datasiteforge-engine

High-speed analytics and state-storage layer for **DataSiteForge**.

Provides:

- `dsf_engine.models` — SQLModel tables for the orchestration state machine.
- `dsf_engine.sqlite_engine` — engine factory, `init_db`, and a `session_scope` context manager.
- `dsf_engine.duckdb_engine` — a thread-safe `DuckDBBroker` for CSV/JSON/Parquet analytics.
- `dsf_engine.cli` — the `db init` / `db status` command group (mounted under `seo-platform db`).
