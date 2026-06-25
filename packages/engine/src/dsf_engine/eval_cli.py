"""The ``evaluate`` command group, mounted under ``seo-platform evaluate``.

* ``evaluate run``  — run the financial-evaluation loop over pending opportunities.
* ``evaluate list`` — list persisted evaluations (verdict, pattern, template).
"""

from __future__ import annotations

import typer
from dsf_core.config import get_settings
from dsf_core.telemetry import get_console
from rich.table import Table
from sqlmodel import select

from .evaluator import Evaluator
from .models import ArbitrageOpportunity, Evaluation
from .sqlite_engine import init_db, session_scope

eval_app = typer.Typer(
    name="evaluate",
    help="Monetisation & opportunity evaluation (Phase 3).",
    no_args_is_help=True,
)


@eval_app.command("run")
def evaluate_run(
    min_confidence: float = typer.Option(
        0.5, "--min-confidence", "-c", min=0.0, max=1.0,
        help="Minimum agent confidence to APPROVE an opportunity.",
    ),
    limit: int = typer.Option(
        None, "--limit", "-l", help="Max pending opportunities to evaluate."
    ),
) -> None:
    """Evaluate pending opportunities and persist verdicts to the ledger."""
    console = get_console()
    evaluator = Evaluator(min_confidence=min_confidence)
    report = evaluator.run(limit=limit)

    table = Table(title="Evaluation outcomes")
    table.add_column("Opp", justify="right")
    table.add_column("Niche", style="bold")
    table.add_column("Verdict")
    table.add_column("Pattern")
    table.add_column("Template")
    table.add_column("Conf", justify="right")
    for outcome in report.outcomes:
        verdict_style = {
            "APPROVED": "[green]APPROVED[/green]",
            "REJECTED": "[yellow]REJECTED[/yellow]",
            "FAILED": "[red]FAILED[/red]",
        }.get(outcome.status, outcome.status)
        table.add_row(
            str(outcome.opportunity_id),
            outcome.niche_id,
            verdict_style,
            outcome.monetization_pattern or "-",
            outcome.template_type or "-",
            f"{outcome.confidence:.2f}" if outcome.confidence is not None else "-",
        )
    console.print(table)
    console.print(
        f"evaluated={report.evaluated} "
        f"[green]approved[/green]={report.approved} "
        f"[yellow]rejected[/yellow]={report.rejected} "
        f"[red]failed[/red]={report.failed}"
    )
    for outcome in report.outcomes:
        if outcome.status == "FAILED":
            console.print(f"  [red]error[/red] opp {outcome.opportunity_id}: {outcome.error}")


@eval_app.command("list")
def evaluate_list(
    limit: int = typer.Option(20, "--limit", "-l", help="Max evaluations to show."),
) -> None:
    """List persisted evaluations joined with their opportunity niche."""
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
            select(Evaluation, ArbitrageOpportunity)
            .join(
                ArbitrageOpportunity,
                Evaluation.opportunity_id == ArbitrageOpportunity.id,  # type: ignore[arg-type]
                isouter=True,
            )
            .order_by(Evaluation.created_at.desc())  # type: ignore[attr-defined]
            .limit(limit)
        )
        rows = list(session.exec(statement))

    if not rows:
        console.print("[dim]No evaluations recorded yet.[/dim]")
        return

    table = Table(title="Evaluations (ledger)")
    table.add_column("ID", justify="right")
    table.add_column("Niche", style="bold")
    table.add_column("Verdict")
    table.add_column("Pattern")
    table.add_column("Template")
    table.add_column("Route")
    table.add_column("Conf", justify="right")
    for evaluation, opportunity in rows:
        niche = opportunity.niche_id if opportunity is not None else "-"
        table.add_row(
            str(evaluation.id),
            niche,
            evaluation.verdict.value,
            evaluation.monetization_pattern.value,
            evaluation.template_type.value,
            evaluation.seo_route_pattern or "-",
            f"{evaluation.confidence:.2f}",
        )
    console.print(table)
