"""Live integration tests for external boundaries.

These are skipped by default (collected but marked ``live``); run them with
``uv run pytest -m live --run-live`` or ``RUN_LIVE=1``.  Each test skips (rather
than fails) if the external service is unreachable, so a sandboxed/offline CI
never goes red on them — they exist to validate the *real* integration on demand.
"""

from __future__ import annotations

import os

import pytest
from dsf_scout.sources import OpenDataSource, SourceError

# Override with DSF_LIVE_CKAN_PORTAL. catalog.data.gov's action API currently
# 404s for automated clients, so the default points at a known-working CKAN host.
_LIVE_PORTAL = os.environ.get("DSF_LIVE_CKAN_PORTAL", "https://ckan.publishing.service.gov.uk")


@pytest.mark.live
def test_opendata_live_returns_candidates() -> None:
    try:
        results = OpenDataSource(_LIVE_PORTAL, rows=5).discover("health")
    except SourceError as exc:  # network blocked / portal down -> not a failure
        pytest.skip(f"live CKAN portal unavailable: {exc}")

    assert results, "expected at least one candidate from the live portal"
    candidate = results[0]
    assert candidate["source"] == "opendata"
    assert str(candidate["target_dataset_url"]).startswith("http")
    assert isinstance(candidate["data_sources_available"], list)
    assert candidate["niche_id"]


@pytest.mark.live
def test_opendata_live_follows_redirects() -> None:
    # data.gov.uk 301-redirects to its CKAN host; this breaks without
    # follow_redirects=True, so it guards that regression against the real API.
    try:
        results = OpenDataSource("https://data.gov.uk", rows=3).discover("health")
    except SourceError as exc:
        pytest.skip(f"live CKAN portal unavailable: {exc}")

    assert results, "redirect-followed portal returned no candidates"
