"""The ``db`` command group, mounted under ``seo-platform db``.

Exposes the Phase 1 verification hooks:

* ``seo-platform db init``   — create the data directory and all storage engines.
* ``seo-platform db status`` — report SQLite table counts and DuckDB health.
"""

from __future__ import annotations

import typer
from dsf_core.config import get_settings
from dsf_core.telemetry import get_console
from rich.table import Table

from .duckdb_engine import DuckDBBroker, DuckDBError
from .sqlite_engine import init_db, table_counts

db_app = typer.Typer(
    name="db",
    help="Storage engine operations (SQLite state + DuckDB analytics).",
    no_args_is_help=True,
)


@db_app.command("init")
def db_init() -> None:
    """Initialise the SQLite state store and the DuckDB analytics store."""
    console = get_console()
    settings = get_settings()
    try:
        init_db(settings)
        broker = DuckDBBroker(settings)
        try:
            duck_version = broker.version()
            broker.checkpoint()
        finally:
            broker.close()
    except (DuckDBError, OSError) as exc:
        console.print(f"[red]db init failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="DataSiteForge storage initialised", show_lines=False)
    table.add_column("Component", style="bold")
    table.add_column("Location / Version")
    table.add_row("SQLite state", str(settings.sqlite_path))
    table.add_row("DuckDB analytics", str(settings.duckdb_path))
    table.add_row("DuckDB version", duck_version)
    table.add_row("Data dir", str(settings.data_dir))
    console.print(table)


@db_app.command("status")
def db_status() -> None:
    """Report SQLite table row counts and DuckDB connectivity."""
    console = get_console()
    settings = get_settings()

    if settings.sqlite_path is None or not settings.sqlite_path.is_file():
        console.print(
            "[yellow]SQLite state store not initialised.[/yellow] "
            "Run [bold]seo-platform db init[/bold] first."
        )
        raise typer.Exit(code=1)

    try:
        counts = table_counts(settings)
    except Exception as exc:  # noqa: BLE001 — report cleanly instead of crashing
        console.print(f"[red]failed to read SQLite state:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    sqlite_table = Table(title="SQLite state store", show_lines=False)
    sqlite_table.add_column("Table", style="bold")
    sqlite_table.add_column("Rows", justify="right")
    for name, count in counts.items():
        sqlite_table.add_row(name, str(count))
    console.print(sqlite_table)

    duck_table = Table(title="DuckDB analytics store", show_lines=False)
    duck_table.add_column("Metric", style="bold")
    duck_table.add_column("Value")
    duck_table.add_row("Path", str(settings.duckdb_path))
    exists = settings.duckdb_path is not None and settings.duckdb_path.is_file()
    duck_table.add_row("File present", "yes" if exists else "no")
    if settings.duckdb_path is not None and exists:
        size_bytes = settings.duckdb_path.stat().st_size
        duck_table.add_row("File size", f"{size_bytes:,} bytes")
    broker = DuckDBBroker(settings)
    try:
        duck_table.add_row("Version", broker.version())
    except DuckDBError as exc:
        duck_table.add_row("Version", f"[red]error: {exc}[/red]")
    finally:
        broker.close()
    console.print(duck_table)
