"""Shared pytest fixtures: isolate every test behind a throwaway data dir."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture()
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point DataSiteForge at an isolated data directory and reset caches."""
    data_dir = tmp_path / "data"
    mock_dir = data_dir / "mocks"
    mock_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DSF_DATA_DIR", str(data_dir))
    monkeypatch.setenv("DSF_MOCK_DIR", str(mock_dir))
    monkeypatch.setenv("DSF_EXECUTION_MODE", "standalone")
    monkeypatch.setenv("DSF_IS_PRODUCTION", "false")
    monkeypatch.setenv("DSF_AGENT_TRANSPORT", "mock")

    # Ensure cached settings/engine pick up the overrides.
    from dsf_core.config import reload_settings
    from dsf_engine.sqlite_engine import dispose_engine

    dispose_engine()
    reload_settings()

    yield data_dir

    dispose_engine()
    reload_settings()


@pytest.fixture()
def write_mock(isolated_env: Path):
    """Return a helper that writes a JSON mock fixture for a given task type."""
    mock_dir = isolated_env / "mocks"

    def _write(task_type: str, payload: dict) -> Path:
        path = mock_dir / f"{task_type}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    return _write
