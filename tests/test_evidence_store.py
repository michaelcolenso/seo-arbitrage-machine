"""Tests for verified acquisition + business evidence."""

from __future__ import annotations

from pathlib import Path

from dsf_core.config import reload_settings
from dsf_optimizer.evidence import EvidenceStore


def test_business_events_are_idempotent_and_revenue_is_first_party(isolated_env: Path) -> None:
    settings = reload_settings()
    store = EvidenceStore(settings)
    store.register_site(
        "buildingseattle",
        "buildingseattle.com",
        gsc_property="sc-domain:buildingseattle.com",
        cloudflare_zone_id="zone-123",
    )
    store.record_observation(
        site_key="buildingseattle",
        observed_date="2026-09-01",
        source="gsc",
        path="/permits",
        query="seattle building permits",
        impressions=1000,
        clicks=80,
    )
    store.record_observation(
        site_key="buildingseattle",
        observed_date="2026-09-01",
        source="cloudflare",
        path="/permits",
        requests=500,
        visits=300,
    )
    assert store.record_business_event(
        event_id="lead-1",
        site_key="buildingseattle",
        event_type="LEAD",
        occurred_at="2026-09-01T12:00:00Z",
        lead_key="contractor-42",
    )
    assert not store.record_business_event(
        event_id="lead-1",
        site_key="buildingseattle",
        event_type="LEAD",
        occurred_at="2026-09-01T12:00:00Z",
        lead_key="contractor-42",
    )
    assert store.record_business_event(
        event_id="conversion-1",
        site_key="buildingseattle",
        event_type="CONVERSION",
        occurred_at="2026-09-02T12:00:00Z",
        lead_key="contractor-42",
    )
    assert store.record_business_event(
        event_id="revenue-1",
        site_key="buildingseattle",
        event_type="REVENUE",
        occurred_at="2026-09-02T12:00:01Z",
        lead_key="contractor-42",
        value_cents=25000,
    )

    summary = store.summary("buildingseattle")
    assert summary["impressions"] == 1000
    assert summary["clicks"] == 80
    assert summary["requests"] == 500
    assert summary["visits"] == 300
    assert summary["leads"] == 1
    assert summary["conversions"] == 1
    assert summary["revenue_usd"] == 250.0
    assert summary["verified_acquisition_sources"] == 2
    assert summary["verified_business_events"] == 3


def test_rejects_unknown_business_event_type(isolated_env: Path) -> None:
    store = EvidenceStore(reload_settings())
    store.register_site("x", "example.com")
    try:
        store.record_business_event(
            event_id="bad",
            site_key="x",
            event_type="PAGEVIEW",
            occurred_at="2026-09-01T00:00:00Z",
        )
    except ValueError as exc:
        assert "LEAD" in str(exc)
    else:
        raise AssertionError("unknown business event type was accepted")
