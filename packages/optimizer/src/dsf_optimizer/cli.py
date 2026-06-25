"""The ``optimize`` command group, mounted under ``seo-platform optimize``.

* ``optimize run``  — ingest telemetry, flag underperformers, reinforce them.
* ``optimize list`` — list recorded optimizations.
"""

from __future__ import annotations

import typer
from dsf_core.config import get_settings
from dsf_core.telemetry import get_console
from dsf_engine.models import Optimization
from dsf_engine.sqlite_engine import init_db, session_scope
from rich.table import Table
from sqlmodel import select

from .optimizer import Optimizer

optimize_app = typer.Typer(
    name="optimize",
    help="Traffic telemetry & reinforcement loops (Phases 6-7).",
    no_args_is_help=True,
)


@optimize_app.command("run")
def optimize_run(
    deployment_id: int = typer.Option(
        None, "--deployment-id", "-d", help="Single deployment to optimise (default: all)."
    ),
    reinforce: bool = typer.Option(
        True, "--reinforce/--no-reinforce", help="Apply Agent-Bridge meta rewrites."
    ),
    redeploy: bool = typer.Option(
        False, "--redeploy", help="Silently rebuild + redeploy after reinforcing."
    ),
    min_impressions: int = typer.Option(300, "--min-impressions", help="Impression floor to flag."),
    max_ctr: float = typer.Option(0.02, "--max-ctr", help="CTR ceiling to flag (e.g. 0.02 = 2%)."),
) -> None:
    """Run a telemetry + reinforcement pass."""
    console = get_console()
    optimizer = Optimizer(min_impressions=min_impressions, max_ctr=max_ctr)
    report = optimizer.run(deployment_id, reinforce=reinforce, redeploy=redeploy)

    table = Table(title="Optimization outcomes")
    table.add_column("Deploy", justify="right")
    table.add_column("Page", style="bold")
    table.add_column("CTR", justify="right")
    table.add_column("Action")
    table.add_column("New title")
    table.add_column("Redeployed")
    for outcome in report.outcomes:
        action = (
            f"[red]{outcome.action}[/red]" if outcome.status == "FAILED" else outcome.action
        )
        table.add_row(
            str(outcome.deployment_id),
            outcome.page_path,
            f"{outcome.ctr:.2%}",
            action,
            (outcome.new_title or "-")[:40],
            "yes" if outcome.redeployed else "no",
        )
    console.print(table)
    console.print(
        f"deployments={report.deployments_processed} "
        f"ingested={report.pages_ingested} "
        f"[yellow]flagged[/yellow]={report.flagged} "
        f"[green]reinforced[/green]={report.reinforced} "
        f"redeployed={report.redeployed}"
    )


@optimize_app.command("list")
def optimize_list(
    limit: int = typer.Option(20, "--limit", "-l", help="Max optimizations to show."),
) -> None:
    """List recorded optimizations, most recent first."""
    console = get_console()
    settings = get_settings()
    if settings.sqlite_path is None or not settings.sqlite_path.is_file():
        console.print(
            "[yellow]Ledger not initialised.[/yellow] Run [bold]seo-platform db init[/bold]."
        )
        raise typer.Exit(code=1)

    # Apply pending additive migrations before querying mapped columns.
    init_db(settings)

    with session_scope(settings) as session:
        statement = (
            select(Optimization)
            .order_by(Optimization.created_at.desc())  # type: ignore[attr-defined]
            .limit(limit)
        )
        records = list(session.exec(statement))

    if not records:
        console.print("[dim]No optimizations recorded yet.[/dim]")
        return

    table = Table(title="Optimizations (ledger)")
    table.add_column("ID", justify="right")
    table.add_column("Deploy", justify="right")
    table.add_column("Page", style="bold")
    table.add_column("CTR", justify="right")
    table.add_column("Action")
    table.add_column("Status")
    table.add_column("Redeployed")
    for record in records:
        table.add_row(
            str(record.id),
            str(record.deployment_id) if record.deployment_id is not None else "-",
            record.page_path,
            f"{record.ctr:.2%}",
            record.action,
            record.status.value,
            "yes" if record.redeployed else "no",
        )
    console.print(table)
