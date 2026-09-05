"""Verified acquisition + business evidence for portfolio learning.

Search Console and Cloudflare are read-only acquisition sources. Leads,
conversions and revenue enter a first-party idempotent business-event ledger so
portfolio decisions do not depend on analytics-tool attribution conventions.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from dsf_core.config import Settings, get_settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvidenceStore:
    """Canonical evidence store for acquisition and commercial outcomes."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_directories()
        assert self.settings.sqlite_path is not None
        self.path = Path(self.settings.sqlite_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS telemetry_sites (
                    site_key TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    deployment_id INTEGER,
                    gsc_property TEXT,
                    cloudflare_zone_id TEXT,
                    opportunity_node_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS telemetry_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site_key TEXT NOT NULL REFERENCES telemetry_sites(site_key) ON DELETE CASCADE,
                    observed_date TEXT NOT NULL,
                    source TEXT NOT NULL,
                    path TEXT NOT NULL DEFAULT '',
                    query TEXT NOT NULL DEFAULT '',
                    impressions INTEGER NOT NULL DEFAULT 0,
                    clicks INTEGER NOT NULL DEFAULT 0,
                    requests INTEGER NOT NULL DEFAULT 0,
                    visits INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    verified INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL,
                    UNIQUE(site_key, observed_date, source, path, query)
                );
                CREATE INDEX IF NOT EXISTS idx_telemetry_obs_site_date
                    ON telemetry_observations(site_key, observed_date);

                CREATE TABLE IF NOT EXISTS business_events (
                    event_id TEXT PRIMARY KEY,
                    site_key TEXT NOT NULL REFERENCES telemetry_sites(site_key) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    path TEXT,
                    lead_key TEXT,
                    value_cents INTEGER NOT NULL DEFAULT 0,
                    currency TEXT NOT NULL DEFAULT 'USD',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    verified INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_business_events_site_time
                    ON business_events(site_key, occurred_at);
                CREATE INDEX IF NOT EXISTS idx_business_events_site_type
                    ON business_events(site_key, event_type);
                """
            )

    def register_site(
        self,
        site_key: str,
        domain: str,
        *,
        deployment_id: int | None = None,
        gsc_property: str | None = None,
        cloudflare_zone_id: str | None = None,
        opportunity_node_id: int | None = None,
    ) -> None:
        self.init_schema()
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO telemetry_sites
                    (site_key, domain, deployment_id, gsc_property, cloudflare_zone_id,
                     opportunity_node_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(site_key) DO UPDATE SET
                    domain = excluded.domain,
                    deployment_id = COALESCE(excluded.deployment_id, telemetry_sites.deployment_id),
                    gsc_property = COALESCE(excluded.gsc_property, telemetry_sites.gsc_property),
                    cloudflare_zone_id = COALESCE(excluded.cloudflare_zone_id, telemetry_sites.cloudflare_zone_id),
                    opportunity_node_id = COALESCE(excluded.opportunity_node_id, telemetry_sites.opportunity_node_id),
                    updated_at = excluded.updated_at
                """,
                (
                    site_key, domain, deployment_id, gsc_property, cloudflare_zone_id,
                    opportunity_node_id, now, now,
                ),
            )

    def get_site(self, site_key: str) -> dict[str, Any] | None:
        self.init_schema()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM telemetry_sites WHERE site_key = ?", (site_key,)).fetchone()
        return dict(row) if row else None

    def record_observation(
        self,
        *,
        site_key: str,
        observed_date: str,
        source: str,
        path: str = "",
        query: str = "",
        impressions: int = 0,
        clicks: int = 0,
        requests: int = 0,
        visits: int = 0,
        metadata: dict[str, Any] | None = None,
        verified: bool = True,
    ) -> None:
        self.init_schema()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO telemetry_observations
                    (site_key, observed_date, source, path, query, impressions, clicks,
                     requests, visits, metadata_json, verified, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(site_key, observed_date, source, path, query) DO UPDATE SET
                    impressions = excluded.impressions,
                    clicks = excluded.clicks,
                    requests = excluded.requests,
                    visits = excluded.visits,
                    metadata_json = excluded.metadata_json,
                    verified = excluded.verified,
                    updated_at = excluded.updated_at
                """,
                (
                    site_key, observed_date, source, path, query, impressions, clicks,
                    requests, visits, json.dumps(metadata or {}, sort_keys=True), int(verified), _now(),
                ),
            )

    def record_business_event(
        self,
        *,
        event_id: str,
        site_key: str,
        event_type: str,
        occurred_at: str,
        path: str | None = None,
        lead_key: str | None = None,
        value_cents: int = 0,
        currency: str = "USD",
        metadata: dict[str, Any] | None = None,
        verified: bool = True,
    ) -> bool:
        """Insert one idempotent first-party event; return True only on first receipt."""
        self.init_schema()
        normalized_type = event_type.upper()
        if normalized_type not in {"LEAD", "CONVERSION", "REVENUE"}:
            raise ValueError("event_type must be LEAD, CONVERSION, or REVENUE")
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO business_events
                    (event_id, site_key, event_type, occurred_at, path, lead_key, value_cents,
                     currency, metadata_json, verified, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id, site_key, normalized_type, occurred_at, path, lead_key,
                    value_cents, currency.upper(), json.dumps(metadata or {}, sort_keys=True),
                    int(verified), _now(),
                ),
            )
        return cursor.rowcount == 1

    def summary(
        self,
        site_key: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        self.init_schema()
        clauses = ["site_key = ?"]
        params: list[Any] = [site_key]
        if start_date:
            clauses.append("observed_date >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("observed_date <= ?")
            params.append(end_date)
        where = " AND ".join(clauses)
        with self._connect() as conn:
            acquisition = conn.execute(
                f"""
                SELECT
                    COALESCE(SUM(impressions), 0) AS impressions,
                    COALESCE(SUM(clicks), 0) AS clicks,
                    COALESCE(SUM(requests), 0) AS requests,
                    COALESCE(SUM(visits), 0) AS visits,
                    COUNT(DISTINCT CASE WHEN verified = 1 THEN source END) AS verified_sources
                FROM telemetry_observations WHERE {where}
                """,
                tuple(params),
            ).fetchone()

            event_clauses = ["site_key = ?"]
            event_params: list[Any] = [site_key]
            if start_date:
                event_clauses.append("substr(occurred_at, 1, 10) >= ?")
                event_params.append(start_date)
            if end_date:
                event_clauses.append("substr(occurred_at, 1, 10) <= ?")
                event_params.append(end_date)
            event_where = " AND ".join(event_clauses)
            business = conn.execute(
                f"""
                SELECT
                    COALESCE(SUM(CASE WHEN event_type = 'LEAD' THEN 1 ELSE 0 END), 0) AS leads,
                    COALESCE(SUM(CASE WHEN event_type = 'CONVERSION' THEN 1 ELSE 0 END), 0) AS conversions,
                    COALESCE(SUM(CASE WHEN event_type = 'REVENUE' THEN value_cents ELSE 0 END), 0) AS revenue_cents,
                    COALESCE(SUM(CASE WHEN verified = 1 THEN 1 ELSE 0 END), 0) AS verified_events
                FROM business_events WHERE {event_where}
                """,
                tuple(event_params),
            ).fetchone()
        impressions = int(acquisition["impressions"])
        clicks = int(acquisition["clicks"])
        leads = int(business["leads"])
        conversions = int(business["conversions"])
        return {
            "site_key": site_key,
            "impressions": impressions,
            "clicks": clicks,
            "ctr": round(clicks / impressions, 6) if impressions else 0.0,
            "requests": int(acquisition["requests"]),
            "visits": int(acquisition["visits"]),
            "leads": leads,
            "conversions": conversions,
            "lead_to_conversion": round(conversions / leads, 6) if leads else 0.0,
            "revenue_cents": int(business["revenue_cents"]),
            "revenue_usd": round(int(business["revenue_cents"]) / 100.0, 2),
            "verified_acquisition_sources": int(acquisition["verified_sources"]),
            "verified_business_events": int(business["verified_events"]),
        }


class SearchConsoleClient:
    """Minimal Search Analytics API client; access token is never persisted."""

    ENDPOINT = "https://www.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"

    def __init__(self, access_token: str, *, timeout: float = 30.0, client: httpx.Client | None = None) -> None:
        self.access_token = access_token
        self.timeout = timeout
        self._client = client

    def rows(self, site_url: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        endpoint = self.ENDPOINT.format(site=quote(site_url, safe=""))
        output: list[dict[str, Any]] = []
        start_row = 0
        while True:
            payload = {
                "startDate": start_date,
                "endDate": end_date,
                "dimensions": ["date", "page", "query"],
                "rowLimit": 25000,
                "startRow": start_row,
            }
            headers = {"Authorization": f"Bearer {self.access_token}"}
            if self._client is not None:
                response = self._client.post(endpoint, headers=headers, json=payload)
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            rows = response.json().get("rows", [])
            output.extend(rows)
            if len(rows) < 25000:
                break
            start_row += len(rows)
        return output


class CloudflareHTTPAnalyticsClient:
    """Current Cloudflare HTTP analytics client using httpRequestsAdaptiveGroups."""

    ENDPOINT = "https://api.cloudflare.com/client/v4/graphql"
    QUERY = """
    query Traffic($zoneTag: string, $start: Time, $end: Time) {
      viewer {
        zones(filter: {zoneTag: $zoneTag}) {
          groups: httpRequestsAdaptiveGroups(
            limit: 10000
            orderBy: [count_DESC]
            filter: {datetime_geq: $start, datetime_lt: $end, requestSource: \"eyeball\"}
          ) {
            count
            avg { sampleInterval }
            sum { visits }
            dimensions { clientRequestPath }
          }
        }
      }
    }
    """

    def __init__(self, api_token: str, *, timeout: float = 30.0, client: httpx.Client | None = None) -> None:
        self.api_token = api_token
        self.timeout = timeout
        self._client = client

    def path_rows(self, zone_id: str, day: date) -> list[dict[str, Any]]:
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        payload = {
            "query": self.QUERY,
            "variables": {"zoneTag": zone_id, "start": start.isoformat(), "end": end.isoformat()},
        }
        headers = {"Authorization": f"Bearer {self.api_token}"}
        if self._client is not None:
            response = self._client.post(self.ENDPOINT, headers=headers, json=payload)
        else:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(self.ENDPOINT, headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()
        if body.get("errors"):
            raise RuntimeError(f"Cloudflare GraphQL error: {body['errors']}")
        zones = body.get("data", {}).get("viewer", {}).get("zones", [])
        return zones[0].get("groups", []) if zones else []


class EvidenceSync:
    def __init__(self, store: EvidenceStore | None = None) -> None:
        self.store = store or EvidenceStore()

    def sync_search_console(
        self,
        site_key: str,
        client: SearchConsoleClient,
        *,
        start_date: str,
        end_date: str,
    ) -> int:
        site = self.store.get_site(site_key)
        if not site or not site.get("gsc_property"):
            raise KeyError(f"site {site_key!r} has no gsc_property")
        count = 0
        for row in client.rows(site["gsc_property"], start_date, end_date):
            keys = row.get("keys", ["", "", ""])
            self.store.record_observation(
                site_key=site_key,
                observed_date=str(keys[0]),
                source="gsc",
                path=_page_path(str(keys[1])),
                query=str(keys[2]),
                impressions=int(row.get("impressions", 0)),
                clicks=int(row.get("clicks", 0)),
                metadata={"ctr": row.get("ctr"), "position": row.get("position")},
                verified=True,
            )
            count += 1
        return count

    def sync_cloudflare(
        self,
        site_key: str,
        client: CloudflareHTTPAnalyticsClient,
        *,
        start_date: str,
        end_date: str,
    ) -> int:
        site = self.store.get_site(site_key)
        if not site or not site.get("cloudflare_zone_id"):
            raise KeyError(f"site {site_key!r} has no cloudflare_zone_id")
        current = date.fromisoformat(start_date)
        last = date.fromisoformat(end_date)
        count = 0
        while current <= last:
            for row in client.path_rows(site["cloudflare_zone_id"], current):
                dims = row.get("dimensions", {}) or {}
                avg = row.get("avg", {}) or {}
                self.store.record_observation(
                    site_key=site_key,
                    observed_date=current.isoformat(),
                    source="cloudflare",
                    path=str(dims.get("clientRequestPath", "")),
                    requests=int(row.get("count", 0)),
                    visits=int((row.get("sum", {}) or {}).get("visits", 0)),
                    metadata={"sample_interval": avg.get("sampleInterval")},
                    verified=True,
                )
                count += 1
            current += timedelta(days=1)
        return count


def _page_path(url: str) -> str:
    if "://" not in url:
        return url
    after_host = url.split("://", 1)[1]
    slash = after_host.find("/")
    return after_host[slash:] if slash >= 0 else "/"
