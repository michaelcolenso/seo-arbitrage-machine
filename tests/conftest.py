"""Shared pytest fixtures: isolate every test behind a throwaway data dir."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run @pytest.mark.live tests that hit real external services.",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip live tests unless --run-live or RUN_LIVE=1 is set (e.g. in CI they skip)."""
    if config.getoption("--run-live") or os.environ.get("RUN_LIVE") == "1":
        return
    skip_live = pytest.mark.skip(reason="live test; pass --run-live or set RUN_LIVE=1")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


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
    # Keep tests hermetic: clear any ambient credentials from the real
    # environment (e.g. Cloudflare tokens) so behaviour never depends on them.
    for _var in (
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "DSF_CLOUDFLARE_API_TOKEN",
        "DSF_CLOUDFLARE_ACCOUNT_ID",
        "DSF_API_TOKEN",
    ):
        monkeypatch.delenv(_var, raising=False)

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
