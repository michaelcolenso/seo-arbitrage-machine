"""The ``scout`` command group, mounted under ``seo-platform scout``.

Commands:

* ``scout run``     — run an arbitrage scan over manifest (+ optional live) sources.
* ``scout list``    — list scored opportunities from the ledger.
* ``scout sources`` — show which candidate sources are configured.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from dsf_core.config import get_settings
from dsf_core.telemetry import get_console
from dsf_engine.models import ArbitrageOpportunity as OpportunityRecord
from dsf_engine.sqlite_engine import session_scope
from rich.panel import Panel
from rich.table import Table
from sqlmodel import select

from .agent import ScoutAgent
from .sources import CandidateSource, ManifestSource, OpenDataSource

scout_app = typer.Typer(
    name="scout",
    help="Autonomous arbitrage scouting (candidate discovery + scoring).",
    no_args_is_help=True,
)


def _default_manifest_path() -> Path:
    settings = get_settings()
    assert settings.data_dir is not None
    return settings.data_dir / "manifest.json"


@scout_app.command("run")
def scout_run(
    niche: str = typer.Option(..., "--niche", "-n", help="Seed niche to scout."),
    manifest: Path = typer.Option(
        None, "--manifest", "-m", help="Manifest path (defaults to <data>/manifest.json)."
    ),
    live: bool = typer.Option(
        False, "--live/--no-live", help="Also query the live open-data portal."
    ),
    portal: str = typer.Option(
        "https://catalog.data.gov", "--portal", help="CKAN portal URL for --live."
    ),
    rows: int = typer.Option(20, "--rows", help="Max rows to request from the portal."),
) -> None:
    """Run an arbitrage scan and persist accepted opportunities to the ledger."""
    console = get_console()
    manifest_path = manifest or _default_manifest_path()

    sources: list[CandidateSource] = [ManifestSource(manifest_path)]
    if live:
        sources.append(OpenDataSource(portal, rows=rows))

    agent = ScoutAgent(sources)
    report = agent.run(niche)

    if report.status == "AGENT_ACTION_REQUIRED":
        console.print(
            Panel(
                f"error_type: {report.error_type}\nmessage   : {report.message}",
                title=f"[red]scout run failed[/red] (job {report.scout_job_id})",
                expand=False,
            )
        )
        raise typer.Exit(code=1)

    table = Table(title=f"Accepted opportunities · seed='{niche}' · job {report.scout_job_id}")
    table.add_column("Rank", justify="right")
    table.add_column("Niche", style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Vector")
    table.add_column("Source")
    for rank, opp in enumerate(report.accepted, start=1):
        table.add_row(
            str(rank),
            opp.niche_id,
            f"{opp.arbitrage_score:,.2f}",
            opp.monetization_vector.value,
            opp.source or "-",
        )
    console.print(table)

    console.print(
        f"[green]accepted[/green]={len(report.accepted)} "
        f"[yellow]rejected[/yellow]={len(report.rejected)} "
        f"persisted={len(report.persisted_ids)}"
    )
    for reflection in report.sources:
        state = "[green]ok[/green]" if reflection.ok else f"[red]error: {reflection.error}[/red]"
        console.print(f"  source {reflection.source_id}: {state} ({reflection.candidate_count})")
    for rejected in report.rejected:
        console.print(
            f"  [dim]rejected[/dim] {rejected.niche_id}: {rejected.reason.value} — {rejected.detail}"
        )


@scout_app.command("list")
def scout_list(
    limit: int = typer.Option(20, "--limit", "-l", help="Max opportunities to show."),
) -> None:
    """List scored opportunities from the ledger, highest score first."""
    console = get_console()
    settings = get_settings()
    if settings.sqlite_path is None or not settings.sqlite_path.is_file():
        console.print(
            "[yellow]Ledger not initialised.[/yellow] Run [bold]seo-platform db init[/bold]."
        )
        raise typer.Exit(code=1)

    with session_scope(settings) as session:
        statement = (
            select(OpportunityRecord)
            .order_by(OpportunityRecord.arbitrage_score.desc())  # type: ignore[attr-defined]
            .limit(limit)
        )
        records = list(session.exec(statement))

    if not records:
        console.print("[dim]No opportunities recorded yet.[/dim]")
        return

    table = Table(title="Arbitrage opportunities (ledger)")
    table.add_column("ID", justify="right")
    table.add_column("Niche", style="bold")
    table.add_column("Score", justify="right")
    table.add_column("KD", justify="right")
    table.add_column("Vector")
    table.add_column("Status")
    for record in records:
        table.add_row(
            str(record.id),
            record.niche_id,
            f"{record.arbitrage_score:,.2f}",
            str(record.keyword_difficulty),
            record.monetization_vector.value,
            record.status.value,
        )
    console.print(table)


@scout_app.command("sources")
def scout_sources() -> None:
    """Show the candidate sources available to the scout."""
    console = get_console()
    manifest_path = _default_manifest_path()
    present = manifest_path.is_file()
    count = 0
    if present:
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            candidates = data.get("candidates", data) if isinstance(data, dict) else data
            count = len(candidates) if isinstance(candidates, list) else 0
        except (OSError, json.JSONDecodeError):
            present = False

    table = Table(title="Scout candidate sources")
    table.add_column("Source", style="bold")
    table.add_column("Status")
    table.add_column("Detail")
    table.add_row(
        "manifest",
        "[green]ready[/green]" if present else "[yellow]missing[/yellow]",
        f"{manifest_path} ({count} candidates)" if present else str(manifest_path),
    )
    table.add_row("opendata", "[dim]on-demand[/dim]", "enable per-run with --live")
    console.print(table)
