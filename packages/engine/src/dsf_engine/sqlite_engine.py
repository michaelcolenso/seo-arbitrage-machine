"""SQLite/SQLModel state store for DataSiteForge.

A single process-wide SQLAlchemy engine is bound to ``settings.sqlite_path``.
``check_same_thread=False`` lets background task workers share the engine; a
``StaticPool`` is used for in-memory URLs so tests retain their schema across
connections.  :func:`session_scope` provides transactional sessions with
commit/rollback/close semantics.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from dsf_core.config import Settings, get_settings
from dsf_core.telemetry import get_logger, log_event
from sqlalchemy import func
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

# Importing models registers the tables on SQLModel.metadata.
from .models import ALL_TABLES

_log = get_logger("sqlite_engine")

_engine: Engine | None = None
_engine_url: str | None = None


def get_engine(settings: Settings | None = None) -> Engine:
    """Return a cached SQLAlchemy engine, rebuilding it if the URL changed."""
    global _engine, _engine_url
    settings = settings or get_settings()
    url = settings.sqlite_url
    if _engine is not None and _engine_url == url:
        return _engine

    connect_args = {"check_same_thread": False}
    if ":memory:" in url:
        # Keep a single shared connection so in-memory schema survives.
        _engine = create_engine(
            url,
            echo=False,
            connect_args=connect_args,
            poolclass=StaticPool,
        )
    else:
        assert settings.sqlite_path is not None
        settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(url, echo=False, connect_args=connect_args)
    _engine_url = url
    return _engine


def init_db(settings: Settings | None = None) -> Engine:
    """Create the data directory and all tables; return the bound engine."""
    settings = settings or get_settings()
    settings.ensure_directories()
    engine = get_engine(settings)
    SQLModel.metadata.create_all(engine)
    log_event(_log, "sqlite.init", url=settings.sqlite_url, tables=len(ALL_TABLES))
    return engine


@contextmanager
def session_scope(settings: Settings | None = None) -> Iterator[Session]:
    """Provide a transactional :class:`Session`, rolling back on any exception."""
    engine = get_engine(settings)
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception as exc:  # noqa: BLE001 — re-raised after cleanup
        session.rollback()
        log_event(_log, "sqlite.session.rollback", level=40, error=str(exc))
        raise
    finally:
        session.close()


def table_counts(settings: Settings | None = None) -> dict[str, int]:
    """Return a ``{table_name: row_count}`` map for every registered table."""
    counts: dict[str, int] = {}
    with session_scope(settings) as session:
        for model in ALL_TABLES:
            statement = select(func.count()).select_from(model)
            counts[model.__tablename__] = int(session.exec(statement).one())
    return counts


def dispose_engine() -> None:
    """Dispose of the cached engine (used by tests to reset state)."""
    global _engine, _engine_url
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _engine_url = None
