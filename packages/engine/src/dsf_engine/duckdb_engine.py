"""Thread-safe DuckDB analytical broker.

DuckDB permits a single read/write connection to a database file per process, but
exposes cheap, thread-local *cursors* over that connection.  :class:`DuckDBBroker`
maintains one base connection guarded by a lock and hands each calling thread its
own cursor via :class:`threading.local`, giving safe concurrent reads for the
analytics layer.  File ingestion auto-detects CSV / JSON / Parquet by extension.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import duckdb
from dsf_core.config import Settings, get_settings
from dsf_core.telemetry import get_logger, log_event

_log = get_logger("duckdb_engine")

# Map file suffixes to the DuckDB reader function that ingests them.
_READERS: dict[str, str] = {
    ".csv": "read_csv_auto",
    ".tsv": "read_csv_auto",
    ".json": "read_json_auto",
    ".ndjson": "read_json_auto",
    ".parquet": "read_parquet",
    ".pq": "read_parquet",
}


class DuckDBError(RuntimeError):
    """Raised for broker-level failures (missing files, unsupported formats)."""


def reader_for(path: Path) -> str:
    """Return the DuckDB reader function name appropriate for ``path``."""
    suffix = path.suffix.lower()
    reader = _READERS.get(suffix)
    if reader is None:
        raise DuckDBError(
            f"unsupported data format {suffix!r} for {path}; "
            f"expected one of {sorted(_READERS)}"
        )
    return reader


class DuckDBBroker:
    """A lazily-connected, thread-safe broker over a single DuckDB database."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings: Settings = settings or get_settings()
        assert self.settings.duckdb_path is not None
        self._db_path: Path = self.settings.duckdb_path
        self._lock = threading.Lock()
        self._local = threading.local()
        self._base: duckdb.DuckDBPyConnection | None = None

    # -- connection management --------------------------------------------

    def _base_connection(self) -> duckdb.DuckDBPyConnection:
        """Open (once) and return the process-wide base connection."""
        if self._base is None:
            with self._lock:
                if self._base is None:
                    self._db_path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        self._base = duckdb.connect(str(self._db_path))
                    except (duckdb.Error, OSError) as exc:
                        raise DuckDBError(
                            f"failed to open DuckDB at {self._db_path}: {exc}"
                        ) from exc
                    log_event(_log, "duckdb.connect", path=str(self._db_path))
        return self._base

    def connect(self) -> duckdb.DuckDBPyConnection:
        """Return this thread's cursor over the shared base connection."""
        cursor = getattr(self._local, "cursor", None)
        if cursor is None:
            cursor = self._base_connection().cursor()
            self._local.cursor = cursor
        return cursor

    # -- queries -----------------------------------------------------------

    def execute(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> duckdb.DuckDBPyConnection:
        """Execute a statement on this thread's cursor and return the cursor."""
        cursor = self.connect()
        try:
            return cursor.execute(sql, params) if params is not None else cursor.execute(sql)
        except duckdb.Error as exc:
            raise DuckDBError(f"query failed: {exc}") from exc

    def query(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> list[dict[str, Any]]:
        """Run a query and return rows as a list of column-keyed dictionaries."""
        cursor = self.execute(sql, params)
        description = cursor.description or []
        columns = [col[0] for col in description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def scalar(
        self, sql: str, params: list[Any] | tuple[Any, ...] | None = None
    ) -> Any:
        """Run a query and return the first column of the first row (or ``None``)."""
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        return row[0] if row else None

    # -- ingestion / profiling --------------------------------------------

    def register_file(self, name: str, path: str | Path) -> str:
        """Register a CSV/JSON/Parquet file as a DuckDB view named ``name``."""
        file_path = Path(path).expanduser().resolve()
        if not file_path.is_file():
            raise DuckDBError(f"data file not found: {file_path}")
        reader = reader_for(file_path)
        # DDL statements (CREATE VIEW) and DESCRIBE cannot use prepared
        # parameters in DuckDB, so the validated view name and the escaped path
        # literal are inlined directly.
        safe_name = self._safe_identifier(name)
        sql = (
            f"CREATE OR REPLACE VIEW {safe_name} AS "
            f"SELECT * FROM {reader}({self._quote_literal(str(file_path))})"
        )
        self.execute(sql)
        log_event(_log, "duckdb.register", view=safe_name, path=str(file_path), reader=reader)
        return safe_name

    def profile_dataset(self, path: str | Path, limit: int = 100) -> dict[str, Any]:
        """Profile a data file: column names/types, row count, and sample rows.

        This is the schema-discovery hook consumed by the Phase 2 Scout: the
        sample rows and column types are fed into the Agent Bridge to derive a
        clean structural JSON schema.
        """
        file_path = Path(path).expanduser().resolve()
        if not file_path.is_file():
            raise DuckDBError(f"data file not found: {file_path}")
        reader = reader_for(file_path)
        # DESCRIBE cannot be prepared in DuckDB; inline the escaped path literal.
        relation = f"{reader}({self._quote_literal(str(file_path))})"

        columns_rows = self.query(f"DESCRIBE SELECT * FROM {relation}")
        columns = [
            {"name": row.get("column_name"), "type": row.get("column_type")}
            for row in columns_rows
        ]
        row_count = int(self.scalar(f"SELECT COUNT(*) FROM {relation}") or 0)
        sample = self.query(f"SELECT * FROM {relation} LIMIT {int(limit)}")
        return {
            "source_path": str(file_path),
            "reader": reader,
            "row_count": row_count,
            "column_count": len(columns),
            "columns": columns,
            "sample_rows": sample,
        }

    def version(self) -> str:
        """Return the underlying DuckDB engine version string."""
        return str(self.scalar("SELECT version()"))

    # -- lifecycle ---------------------------------------------------------

    def checkpoint(self) -> None:
        """Flush the write-ahead log to the database file."""
        try:
            self.execute("CHECKPOINT")
        except DuckDBError:
            # CHECKPOINT is best-effort (e.g. unsupported for in-memory DBs).
            pass

    def close(self) -> None:
        """Close this thread's cursor and the shared base connection."""
        cursor = getattr(self._local, "cursor", None)
        if cursor is not None:
            try:
                cursor.close()
            except duckdb.Error:
                pass
            self._local.cursor = None
        with self._lock:
            if self._base is not None:
                try:
                    self._base.close()
                except duckdb.Error:
                    pass
                self._base = None
                log_event(_log, "duckdb.close", path=str(self._db_path))

    def __enter__(self) -> DuckDBBroker:
        self._base_connection()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @staticmethod
    def _safe_identifier(name: str) -> str:
        """Validate a SQL identifier for views (alnum + underscore only)."""
        candidate = name.strip()
        if not candidate or not all(ch.isalnum() or ch == "_" for ch in candidate):
            raise DuckDBError(f"invalid identifier: {name!r}")
        if candidate[0].isdigit():
            raise DuckDBError(f"identifier may not start with a digit: {name!r}")
        return candidate

    @staticmethod
    def _quote_literal(value: str) -> str:
        """Render ``value`` as a safely-escaped SQL single-quoted string literal."""
        return "'" + value.replace("'", "''") + "'"
