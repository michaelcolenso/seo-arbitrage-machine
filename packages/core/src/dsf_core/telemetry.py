"""Structured, ``rich``-backed telemetry for DataSiteForge.

A single shared :class:`~rich.console.Console` is used so that CLI output and
log records interleave cleanly.  ``get_logger`` returns standard library loggers
wired to a :class:`~rich.logging.RichHandler`; ``log_event`` emits a compact,
key/value structured line for machine-friendly run traces.
"""

from __future__ import annotations

import logging
from typing import Any

from rich.console import Console
from rich.logging import RichHandler

_CONSOLE: Console = Console(stderr=True)
_CONFIGURED: bool = False
_DEFAULT_LEVEL: int = logging.INFO


def get_console() -> Console:
    """Return the shared rich console (writes to stderr)."""
    return _CONSOLE


def configure_logging(level: int = _DEFAULT_LEVEL) -> None:
    """Idempotently install a :class:`RichHandler` on the ``dsf`` logger tree."""
    global _CONFIGURED
    root = logging.getLogger("dsf")
    root.setLevel(level)
    if _CONFIGURED:
        return
    handler = RichHandler(
        console=_CONSOLE,
        show_time=True,
        show_path=False,
        rich_tracebacks=True,
        markup=True,
    )
    handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))
    root.addHandler(handler)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str, level: int | None = None) -> logging.Logger:
    """Return a namespaced logger under the ``dsf`` tree."""
    configure_logging(level if level is not None else _DEFAULT_LEVEL)
    logger = logging.getLogger(f"dsf.{name}")
    if level is not None:
        logger.setLevel(level)
    return logger


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Emit a structured ``event key=value`` log line.

    Example::

        log_event(log, "scout.job.started", job_id=4, niche="solar")
    """
    if fields:
        rendered = " ".join(f"{key}={value!r}" for key, value in fields.items())
        message = f"[bold]{event}[/bold] {rendered}"
    else:
        message = f"[bold]{event}[/bold]"
    logger.log(level, message)
