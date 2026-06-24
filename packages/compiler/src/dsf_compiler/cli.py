"""The ``compile`` command group, mounted under ``seo-platform compile``.

* ``compile run``  — hydrate an approved evaluation into an Astro build.
* ``compile list`` — list site generations (template, status, build path).
"""

from __future__ import annotations

from pathlib import Path

import typer
from dsf_core.config import get_settings
from dsf_core.telemetry import get_console
from dsf_engine.models import SiteGeneration
from dsf_engine.sqlite_engine import session_scope
from rich.panel import Panel
from rich.table import Table
from sqlmodel import select

from .builder import SiteCompiler

compile_app = typer.Typer(
    name="compile",
    help="Astro compilation & hydration (Phase 4).",
    no_args_is_help=True,
)


@compile_app.command("run")
def compile_run(
    evaluation_id: int = typer.Option(..., "--evaluation-id", "-e", help="Evaluation to compile."),
    dataset: Path = typer.Option(..., "--dataset", "-d", help="Path to the source dataset file."),
    build: bool = typer.Option(
        False, "--build/--no-build", help="Also run `npm install && astro build`."
    ),
) -> None:
    """Hydrate an approved evaluation into a site build under data/builds/."""
    console = get_console()
    report = SiteCompiler().compile(evaluation_id, dataset, run_build=build)

    if report.status == "COMPLETED":
        body = (
            f"niche      : {report.niche_id}\n"
            f"template   : {report.template_type}\n"
            f"rows       : {report.row_count}\n"
            f"build_path : {report.build_path}\n"
            f"astro built: {report.built}"
        )
        console.print(Panel(body, title=f"[green]compiled[/green] (site {report.site_generation_id})", expand=False))
        return

    color = "yellow" if report.status == "REJECTED" else "red"
    body = f"status : {report.status}\nmessage: {report.message}"
    if report.error_type:
        body = f"error  : {report.error_type}\n" + body
    console.print(Panel(body, title=f"[{color}]not compiled[/{color}] (evaluation {report.evaluation_id})", expand=False))
    raise typer.Exit(code=1)


@compile_app.command("list")
def compile_list(
    limit: int = typer.Option(20, "--limit", "-l", help="Max site generations to show."),
) -> None:
    """List site generations from the ledger, most recent first."""
    console = get_console()
    settings = get_settings()
    if settings.sqlite_path is None or not settings.sqlite_path.is_file():
        console.print(
            "[yellow]Ledger not initialised.[/yellow] Run [bold]seo-platform db init[/bold]."
        )
        raise typer.Exit(code=1)

    with session_scope(settings) as session:
        statement = (
            select(SiteGeneration)
            .order_by(SiteGeneration.created_at.desc())  # type: ignore[attr-defined]
            .limit(limit)
        )
        records = list(session.exec(statement))

    if not records:
        console.print("[dim]No site generations recorded yet.[/dim]")
        return

    table = Table(title="Site generations (ledger)")
    table.add_column("ID", justify="right")
    table.add_column("Eval", justify="right")
    table.add_column("Template")
    table.add_column("Status")
    table.add_column("Build path")
    for record in records:
        table.add_row(
            str(record.id),
            str(record.evaluation_id) if record.evaluation_id is not None else "-",
            record.template_type.value,
            record.status.value,
            record.build_path or "-",
        )
    console.print(table)
