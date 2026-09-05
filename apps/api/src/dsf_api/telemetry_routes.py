"""Protected evidence endpoints for the DataSiteForge control plane."""

from __future__ import annotations

from typing import Any, Literal

from dsf_optimizer.evidence import EvidenceStore
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
