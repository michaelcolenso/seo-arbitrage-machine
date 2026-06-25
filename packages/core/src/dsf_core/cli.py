"""The ``seo-platform`` command-line entry point.

This module owns the top-level Typer application.  Storage commands live in the
``datasiteforge-engine`` package; they are mounted here via a *lazy* import so
that ``dsf_core`` carries no import-time dependency on ``dsf_engine`` (the
dependency only flows engine -> core).  Within a synced uv workspace both
packages are always importable, so the ``db`` group resolves at runtime.
"""

from __future__ import annotations

import typer
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .agent_bridge import AgentBridge
from .config import get_settings
from .telemetry import configure_logging, get_console

app = typer.Typer(
    name="seo-platform",
    help="DataSiteForge control plane — workspace, agent bridge, and storage operations.",
    no_args_is_help=True,
    add_completion=False,
)

config_app = typer.Typer(help="Inspect runtime configuration.", no_args_is_help=True)
agent_app = typer.Typer(help="Interact with the Agent Bridge.", no_args_is_help=True)
app.add_typer(config_app, name="config")
app.add_typer(agent_app, name="agent")


def _mount_engine_commands() -> None:
    """Lazily attach the engine command groups (`db`, `evaluate`)."""
    try:
        from dsf_engine.cli import db_app
        from dsf_engine.eval_cli import eval_app
    except ModuleNotFoundError:  # engine not installed (core used standalone)
        return
    app.add_typer(db_app, name="db")
    app.add_typer(eval_app, name="evaluate")


def _mount_scout_commands() -> None:
    """Lazily attach the scouting (`scout`) command group from the scout package."""
    try:
        from dsf_scout.cli import scout_app
    except ModuleNotFoundError:  # scout not installed (core used standalone)
        return
    app.add_typer(scout_app, name="scout")


def _mount_deployer_commands() -> None:
    """Lazily attach the deployment (`deploy`) command group from the deployer."""
    try:
        from dsf_deployer.cli import deploy_app
    except ModuleNotFoundError:  # deployer not installed (core used standalone)
        return
    app.add_typer(deploy_app, name="deploy")


def _mount_optimizer_commands() -> None:
    """Lazily attach the optimization (`optimize`) command group from the optimizer."""
    try:
        from dsf_optimizer.cli import optimize_app
    except ModuleNotFoundError:  # optimizer not installed (core used standalone)
        return
    app.add_typer(optimize_app, name="optimize")


def _mount_api_commands() -> None:
    """Lazily attach the API server (`serve`) command from the api app."""
    try:
        from dsf_api.cli import serve_app
    except ModuleNotFoundError:  # api app not installed (core used standalone)
        return
    app.add_typer(serve_app, name="serve")


def _mount_compiler_commands() -> None:
    """Lazily attach the compilation (`compile`) command group."""
    try:
        from dsf_compiler.cli import compile_app
    except ModuleNotFoundError:  # compiler not installed (core used standalone)
        return
    app.add_typer(compile_app, name="compile")


@app.callback()
def _main() -> None:
    """Initialise logging before any command runs."""
    configure_logging()


@app.command()
def version() -> None:
    """Print the DataSiteForge version."""
    get_console().print(f"DataSiteForge [bold cyan]v{__version__}[/bold cyan]")


_SECRET_FIELDS = frozenset({"cloudflare_api_token"})


def _redact(name: str, value: object) -> str:
    if value is None:
        return "[dim]<unset>[/dim]"
    if name in _SECRET_FIELDS:
        return "[yellow]***redacted***[/yellow]"
    return str(value)


@config_app.command("show")
def config_show() -> None:
    """Display the resolved settings (secrets redacted)."""
    settings = get_settings()
    table = Table(title="DataSiteForge configuration", show_lines=False)
    table.add_column("Setting", style="bold")
    table.add_column("Value")

    table.add_row("execution_mode", _redact("execution_mode", settings.execution_mode))
    table.add_row("is_production", _redact("is_production", settings.is_production))
    table.add_row("agent_transport", _redact("agent_transport", settings.agent_transport))
    table.add_row("mcp_server_url", _redact("mcp_server_url", settings.mcp_server_url))
    table.add_row(
        "agent_runtime_attached",
        _redact("agent_runtime_attached", settings.agent_runtime_attached),
    )
    table.add_row(
        "cloudflare_api_token",
        _redact("cloudflare_api_token", settings.cloudflare_api_token),
    )
    table.add_row(
        "cloudflare_account_id",
        _redact("cloudflare_account_id", settings.cloudflare_account_id),
    )
    table.add_row("data_dir", _redact("data_dir", settings.data_dir))
    table.add_row("sqlite_path", _redact("sqlite_path", settings.sqlite_path))
    table.add_row("duckdb_path", _redact("duckdb_path", settings.duckdb_path))
    table.add_row("mock_dir", _redact("mock_dir", settings.mock_dir))

    get_console().print(table)


@agent_app.command("ping")
def agent_ping(
    task_type: str = typer.Option(
        "schema_discovery",
        "--task",
        "-t",
        help="Task type to dispatch (must have a matching mock fixture in mock mode).",
    ),
) -> None:
    """Send a probe request through the Agent Bridge and report the result."""
    bridge = AgentBridge()
    transport = bridge.resolve_transport()
    response = bridge.request(task_type, {"probe": True})
    console = get_console()
    status = "[green]OK[/green]" if response.ok else "[red]FAILED[/red]"
    body = (
        f"transport : {transport}\n"
        f"status    : {status}\n"
        f"request_id: {response.request_id}\n"
    )
    if response.ok:
        body += f"result    : {response.result}"
    else:
        body += f"error     : {response.error}"
    console.print(Panel(body, title=f"agent ping · {task_type}", expand=False))
    if not response.ok:
        raise typer.Exit(code=1)


# Attach storage, scouting, and compilation commands at import time so they
# appear in `--help`.
_mount_engine_commands()
_mount_scout_commands()
_mount_compiler_commands()
_mount_deployer_commands()
_mount_optimizer_commands()
_mount_api_commands()


if __name__ == "__main__":  # pragma: no cover
    app()
