"""Protected evidence endpoints for the DataSiteForge control plane."""

from __future__ import annotations

from typing import Any, Literal

from dsf_core.config import get_settings
from dsf_optimizer.evidence import (
    CloudflareHTTPAnalyticsClient,
    EvidenceStore,
    EvidenceSync,
    SearchConsoleClient,
)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

telemetry_router = APIRouter(prefix="/telemetry", tags=["telemetry"])


class SiteRegistration(BaseModel):
    site_key: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    deployment_id: int | None = None
    gsc_property: str | None = None
    cloudflare_zone_id: str | None = None
    opportunity_node_id: int | None = None


class BusinessEventRequest(BaseModel):
    event_id: str = Field(min_length=1)
    site_key: str = Field(min_length=1)
    event_type: Literal["LEAD", "CONVERSION", "REVENUE"]
    occurred_at: str = Field(min_length=10)
    path: str | None = None
    lead_key: str | None = None
    value_cents: int = Field(default=0, ge=0)
    currency: str = "USD"
    metadata: dict[str, Any] = Field(default_factory=dict)
    verified: bool = True


class SyncWindow(BaseModel):
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


@telemetry_router.post("/sites")
def register_site(req: SiteRegistration) -> dict[str, Any]:
    store = EvidenceStore()
    store.register_site(**req.model_dump())
    return {"status": "ok", "site": store.get_site(req.site_key)}


@telemetry_router.post("/events")
def record_event(req: BusinessEventRequest) -> dict[str, Any]:
    store = EvidenceStore()
    if store.get_site(req.site_key) is None:
        raise HTTPException(status_code=404, detail="telemetry site not found")
    inserted = store.record_business_event(**req.model_dump())
    return {"status": "recorded" if inserted else "duplicate", "event_id": req.event_id}


@telemetry_router.post("/{site_key}/sync/gsc")
def sync_gsc(site_key: str, window: SyncWindow) -> dict[str, Any]:
    settings = get_settings()
    token = settings.google_search_console_access_token
    if not token:
        raise HTTPException(status_code=503, detail="Search Console access token is not configured")
    store = EvidenceStore(settings)
    if store.get_site(site_key) is None:
        raise HTTPException(status_code=404, detail="telemetry site not found")
    try:
        rows = EvidenceSync(store).sync_search_console(
            site_key,
            SearchConsoleClient(token),
            start_date=window.start_date,
            end_date=window.end_date,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "source": "gsc", "rows": rows}


@telemetry_router.post("/{site_key}/sync/cloudflare")
def sync_cloudflare(site_key: str, window: SyncWindow) -> dict[str, Any]:
    settings = get_settings()
    token = settings.cloudflare_api_token
    if not token:
        raise HTTPException(status_code=503, detail="Cloudflare API token is not configured")
    store = EvidenceStore(settings)
    if store.get_site(site_key) is None:
        raise HTTPException(status_code=404, detail="telemetry site not found")
    try:
        rows = EvidenceSync(store).sync_cloudflare(
            site_key,
            CloudflareHTTPAnalyticsClient(token),
            start_date=window.start_date,
            end_date=window.end_date,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "source": "cloudflare", "rows": rows}


@telemetry_router.get("/{site_key}/summary")
def evidence_summary(
    site_key: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    store = EvidenceStore()
    if store.get_site(site_key) is None:
        raise HTTPException(status_code=404, detail="telemetry site not found")
    return store.summary(site_key, start_date=start_date, end_date=end_date)
