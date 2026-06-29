"""The ``mcp`` command, mounted under ``seo-platform mcp``."""

from __future__ import annotations

import typer

mcp_app = typer.Typer(
    name="mcp",
    help="Run the DataSiteForge MCP server (stdio) for agent runners.",
    invoke_without_command=True,
    no_args_is_help=False,
)


@mcp_app.callback()
def serve_mcp() -> None:
    """Start the MCP server over stdio."""
    from .server import build_server

    build_server().run()
