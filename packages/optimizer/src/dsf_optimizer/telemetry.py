"""Telemetry sources for the optimizer.

A :class:`TelemetrySource` returns per-page interaction metrics for a deployed
site.  Two implementations:

* :class:`MockTelemetrySource` — deterministic, offline; always available so the
  reinforcement loop runs without an analytics account.  It synthesises a small,
  realistic set of pages including a deliberate underperformer (high impressions,
  weak click-through) so analysis and reinforcement are exercised.
* :class:`CloudflareWebAnalyticsSource` — live, via the Cloudflare GraphQL
  Analytics API (``httpx``, injectable client), parsing RUM pageview groups.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import httpx
from dsf_core.config import Settings
from dsf_core.telemetry import get_logger, log_event
from dsf_engine.models import Deployment
from pydantic import BaseModel, Field

_log = get_logger("optimizer.telemetry")

_CF_GRAPHQL = "https://api.cloudflare.com/client/v4/graphql"


class TelemetryError(RuntimeError):
    """Raised when a telemetry source cannot produce metrics."""


class PageMetric(BaseModel):
    """Interaction metrics for a single page over the reporting window."""

    page_path: str
    impressions: int = Field(default=0, ge=0)
    clicks: int = Field(default=0, ge=0)
    revenue_cents: int = Field(default=0, ge=0)

    @property
    def ctr(self) -> float:
        return (self.clicks / self.impressions) if self.impressions else 0.0


@runtime_checkable
class TelemetrySource(Protocol):
    """A provider of per-page interaction metrics for a deployment."""

    source_id: str

    def fetch(self, deployment: Deployment) -> list[PageMetric]:
        """Return page metrics for ``deployment`` over the reporting window."""
        ...


class MockTelemetrySource:
    """Deterministic, offline telemetry for testing the full loop."""

    source_id = "mock"

    def fetch(self, deployment: Deployment) -> list[PageMetric]:
        # A high-traffic landing page that converts poorly (the underperformer),
        # plus a healthy secondary page.  Deterministic per deployment id.
        seed = (deployment.id or 1)
        landing_impressions = 1000 + seed * 10
        metrics = [
            PageMetric(
                page_path="/",
                impressions=landing_impressions,
                clicks=max(1, landing_impressions // 200),  # ~0.5% CTR -> flagged
                revenue_cents=0,
            ),
            PageMetric(
                page_path="/directory",
                impressions=240,
                clicks=18,  # ~7.5% CTR -> healthy
                revenue_cents=4200,
            ),
        ]
        log_event(
            _log, "telemetry.mock.fetch", deployment_id=deployment.id, pages=len(metrics)
        )
        return metrics


class CloudflareWebAnalyticsSource:
    """Live telemetry via the Cloudflare GraphQL Analytics API."""

    source_id = "cloudflare"

    def __init__(self, settings: Settings, *, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = client

    def fetch(self, deployment: Deployment) -> list[PageMetric]:
        token = self.settings.cloudflare_api_token
        account = self.settings.cloudflare_account_id
        if not token or not account:
            raise TelemetryError("Cloudflare credentials are not configured")

        query = _RUM_QUERY
        variables = {"accountTag": account, "limit": 100}
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"query": query, "variables": variables}
        try:
            if self._client is not None:
                response = self._client.post(_CF_GRAPHQL, json=payload, headers=headers)
            else:
                with httpx.Client(timeout=60.0) as client:
                    response = client.post(_CF_GRAPHQL, json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            raise TelemetryError(f"Cloudflare analytics request failed: {exc}") from exc

        if body.get("errors"):
            raise TelemetryError(f"Cloudflare analytics returned errors: {body['errors']}")
        metrics = _parse_rum_groups(body)
        log_event(
            _log,
            "telemetry.cloudflare.fetch",
            deployment_id=deployment.id,
            pages=len(metrics),
        )
        return metrics


_RUM_QUERY = """
query PageViews($accountTag: string!, $limit: Int!) {
  viewer {
    accounts(filter: {accountTag: $accountTag}) {
      rumPageloadEventsAdaptiveGroups(limit: $limit) {
        count
        sum { visits }
        dimensions { requestPath }
      }
    }
  }
}
""".strip()


def _parse_rum_groups(body: dict[str, Any]) -> list[PageMetric]:
    """Parse Cloudflare RUM pageview groups into :class:`PageMetric` rows."""
    metrics: list[PageMetric] = []
    accounts = (
        body.get("data", {}).get("viewer", {}).get("accounts", []) or []
    )
    for account in accounts:
        groups = account.get("rumPageloadEventsAdaptiveGroups", []) or []
        for group in groups:
            path = (group.get("dimensions", {}) or {}).get("requestPath", "/")
            impressions = int(group.get("count", 0) or 0)
            visits = int((group.get("sum", {}) or {}).get("visits", 0) or 0)
            metrics.append(
                PageMetric(page_path=path, impressions=impressions, clicks=visits)
            )
    return metrics
