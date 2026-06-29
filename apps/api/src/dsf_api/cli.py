"""The ``serve`` command, mounted under ``seo-platform serve``."""

from __future__ import annotations

import typer

serve_app = typer.Typer(
    name="serve",
    help="Run the DataSiteForge control-plane API + operator console.",
    invoke_without_command=True,
    no_args_is_help=False,
)


@serve_app.callback()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host."),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port."),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes."),
) -> None:
    """Start the FastAPI gateway with uvicorn."""
    import uvicorn

    uvicorn.run(
        "dsf_api.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=reload,
    )
