"""Typer commands for Radar."""

from __future__ import annotations

from pathlib import Path

import typer
from dsf_engine.opportunity_graph import OpportunityGraphStore
from rich.table import Table

from dsf_core.telemetry import get_console

from .enrichment import OpportunityResolver
from .metric_enrichment import MetricQueueRunner
from .runner import RadarRunner
from .store import RadarStore

radar_app = typer.Typer(help="Run and inspect large keyword opportunity scans.", no_args_is_help=True)


@radar_app.command("init")
def init_radar() -> None:
    store = RadarStore()
    store.init_schema()
    OpportunityGraphStore(store.settings).init_schema()
    get_console().print("[green]Radar + Opportunity Graph schema ready.[/green]")


@radar_app.command("scan")
def scan(
    csv_path: Path = typer.Argument(..., exists=True, readable=True),
    name: str = typer.Option("keyword-scan", "--name"),
    run_id: str | None = typer.Option(None, "--run-id", help="Reuse to resume a prior run."),
    total: int | None = typer.Option(None, "--total", min=1),
    batch_size: int = typer.Option(5000, "--batch-size", min=1),
    max_rows: int | None = typer.Option(None, "--max-rows", min=1),
    review_threshold: float = typer.Option(55.0, "--review-threshold", min=0, max=100),
    promote_threshold: float = typer.Option(65.0, "--promote-threshold", min=0, max=100),
) -> None:
    runner = RadarRunner()
    resolved = runner.scan_csv(
        csv_path,
        name=name,
        run_id=run_id,
        total_expected=total,
        batch_size=batch_size,
        max_rows=max_rows,
        review_threshold=review_threshold,
        promote_threshold=promote_threshold,
    )
    _render_summary(RadarStore(), resolved)


@radar_app.command("million")
def million(
    name: str = typer.Option("public-data-million-v1", "--name"),
    run_id: str | None = typer.Option(None, "--run-id", help="Reuse to resume a prior run."),
    batch_size: int = typer.Option(5000, "--batch-size", min=1),
    max_rows: int | None = typer.Option(None, "--max-rows", min=1),
    review_threshold: float = typer.Option(55.0, "--review-threshold", min=0, max=100),
    resolve: bool = typer.Option(True, "--resolve/--no-resolve"),
) -> None:
    """Run the canonical deterministic one-million-row discovery universe."""
    runner = RadarRunner()
    resolved_run = runner.scan_universe(
        name=name,
        run_id=run_id,
        batch_size=batch_size,
        max_rows=max_rows,
        review_threshold=review_threshold,
    )
    store = RadarStore()
    _render_summary(store, resolved_run)
    summary = store.get_summary(resolved_run)
    if resolve and summary is not None and summary.status.value == "COMPLETED":
        report = OpportunityResolver(store).resolve_run(resolved_run, min_scan_score=review_threshold)
        get_console().print(
            f"[green]Resolved[/green] {report.reviewed_keywords:,} REVIEW keywords → "
            f"{report.clusters:,} opportunity clusters; {report.metric_queue:,} metric checks queued."
        )


@radar_app.command("resolve")
def resolve_run(
    run_id: str = typer.Argument(...),
    min_scan_score: float = typer.Option(55.0, "--min-scan-score", min=0, max=100),
    max_keywords: int | None = typer.Option(None, "--max-keywords", min=1),
    provider: str = typer.Option("ahrefs", "--provider"),
) -> None:
    report = OpportunityResolver().resolve_run(
        run_id,
        min_scan_score=min_scan_score,
        max_keywords=max_keywords,
        metric_provider=provider,
    )
    get_console().print(
        f"Resolved {report.reviewed_keywords:,} keywords into {report.clusters:,} clusters; "
        f"metric queue={report.metric_queue:,}; skipped={report.skipped:,}."
    )


@radar_app.command("verify-metrics")
def verify_metrics(
    limit: int = typer.Option(200, "--limit", min=1, max=1000),
) -> None:
    """Apply verified Ahrefs metrics to queued cluster representatives."""
    report = MetricQueueRunner().run(limit=limit)
    get_console().print(
        f"Metric enrichment attempted={report.attempted:,}; verified={report.verified:,}; "
        f"empty={report.empty:,}; failed={report.failed:,}."
    )


@radar_app.command("clusters")
def clusters(
    run_id: str = typer.Argument(...),
    limit: int = typer.Option(25, "--limit", min=1, max=200),
) -> None:
    rows = OpportunityGraphStore().top_clusters(run_id, limit=limit)
    table = Table(title=f"Opportunity clusters · {run_id}")
    for heading in ("Opportunity", "Keywords", "Max scan", "Avg scan", "Readiness"):
        table.add_column(heading)
    for row in rows:
        table.add_row(
            str(row["label"]),
            f"{row['keyword_count']:,}",
            f"{row['max_scan_score']:.1f}",
            f"{row['avg_scan_score']:.1f}",
            str(row["readiness"]),
        )
    get_console().print(table)


@radar_app.command("status")
def status(run_id: str | None = typer.Argument(None)) -> None:
    store = RadarStore()
    summary = store.get_summary(run_id)
    if summary is None:
        get_console().print("[yellow]No Radar runs found.[/yellow]")
        raise typer.Exit(code=1)
    _render_summary(store, summary.run_id)


@radar_app.command("top")
def top(
    run_id: str | None = typer.Argument(None),
    limit: int = typer.Option(20, "--limit", min=1, max=200),
) -> None:
    store = RadarStore()
    summary = store.get_summary(run_id)
    if summary is None:
        get_console().print("[yellow]No Radar runs found.[/yellow]")
        raise typer.Exit(code=1)
    rows = store.top_candidates(summary.run_id, limit=limit)
    table = Table(title=f"Radar top candidates · {summary.name}")
    for heading in ("Decision", "Keyword", "Volume", "CPC", "KD", "Scan", "Opportunity", "Buyer"):
        table.add_column(heading)
    for row in rows:
        table.add_row(
            str(row["decision"]),
            str(row["keyword"]),
            f"{row['volume']:,}",
            f"${row['cpc']:.2f}",
            f"{row['kd']:.1f}",
            f"{row['scan_score']:.1f}",
            "—" if row["opportunity_score"] is None else f"{row['opportunity_score']:.1f}",
            row["buyer"] or "—",
        )
    get_console().print(table)


def _render_summary(store: RadarStore, run_id: str) -> None:
    summary = store.get_summary(run_id)
    if summary is None:
        return
    table = Table(title=f"Radar scan · {summary.name}")
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    completion = "unknown"
    if summary.completion_ratio is not None:
        completion = f"{summary.completion_ratio:.1%}"
    for key, value in (
        ("run_id", summary.run_id),
        ("status", summary.status.value),
        ("processed", f"{summary.processed_count:,}"),
        ("expected", "—" if summary.total_expected is None else f"{summary.total_expected:,}"),
        ("completion", completion),
        ("promoted", f"{summary.promoted_count:,}"),
        ("review", f"{summary.review_count:,}"),
        ("rejected", f"{summary.rejected_count:,}"),
        ("errors", f"{summary.error_count:,}"),
        ("spend_usd", f"${summary.spend_usd:,.2f}"),
        ("checkpoint", summary.checkpoint or "—"),
    ):
        table.add_row(key, str(value))
    get_console().print(table)
