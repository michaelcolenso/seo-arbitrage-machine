"""Pluggable candidate sources for the Scout.

Two sources feed a single shared candidate pool (the "both in parallel" model):

* :class:`ManifestSource` — deterministic, offline, reads a curated
  ``data/manifest.json``.  Always available; ideal for testing the full pipeline.
* :class:`OpenDataSource` — live discovery against a CKAN-style open-data portal
  (e.g. ``catalog.data.gov``).  Network-bound, so it is only included by the agent
  when explicitly enabled, keeping standalone/test runs deterministic.

Sources may return *partial* candidate dicts (e.g. open-data results lack keyword
volume / CPC).  The :class:`~dsf_scout.agent.ScoutAgent` enriches partial
candidates via the Agent Bridge before scoring.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import httpx
from dsf_core.telemetry import get_logger, log_event

_log = get_logger("scout.sources")

# Polite, identifiable User-Agent for open-data portal requests.
_USER_AGENT = "DataSiteForge/0.1 (+https://github.com/michaelcolenso/seo-arbitrage-machine)"


class SourceError(RuntimeError):
    """Raised when a candidate source cannot produce results."""


@runtime_checkable
class CandidateSource(Protocol):
    """A provider of raw arbitrage candidate dicts."""

    source_id: str

    def discover(self, seed_niche: str) -> list[dict[str, Any]]:
        """Return candidate dicts relevant to ``seed_niche`` (may be partial)."""
        ...


class ManifestSource:
    """Reads curated candidates from a local JSON manifest.

    The manifest is a JSON object with a ``candidates`` array, or a bare array.
    When ``seed_niche`` is provided, candidates are filtered by a case-insensitive
    substring match against ``niche_id`` and ``primary_keywords``.
    """

    source_id = "manifest"

    def __init__(self, manifest_path: str | Path) -> None:
        self.manifest_path = Path(manifest_path)

    def discover(self, seed_niche: str = "") -> list[dict[str, Any]]:
        if not self.manifest_path.is_file():
            raise SourceError(f"manifest not found: {self.manifest_path}")
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SourceError(f"failed to read manifest {self.manifest_path}: {exc}") from exc

        if isinstance(data, dict):
            candidates = data.get("candidates", [])
        elif isinstance(data, list):
            candidates = data
        else:
            raise SourceError("manifest must be a JSON object or array")

        if not isinstance(candidates, list):
            raise SourceError("manifest 'candidates' must be an array")

        results = [c for c in candidates if isinstance(c, dict)]
        for candidate in results:
            candidate.setdefault("source", self.source_id)

        if seed_niche:
            needle = seed_niche.lower()
            results = [c for c in results if _matches_seed(c, needle)]

        log_event(
            _log,
            "source.manifest.discover",
            path=str(self.manifest_path),
            seed=seed_niche or "<all>",
            count=len(results),
        )
        return results


class OpenDataSource:
    """Live discovery against a CKAN-style open-data portal.

    Uses the CKAN ``package_search`` action API.  Returns *partial* candidates:
    ``niche_id``, ``target_dataset_url``, and detected ``data_sources_available``
    (resource formats).  Keyword/monetisation fields are left for Agent Bridge
    enrichment downstream.

    Note: ``catalog.data.gov``'s action API currently returns 404 to automated
    clients, so pass a working ``portal_url`` (e.g. ``https://data.gov.uk`` or
    another CKAN host).  Requests send a descriptive User-Agent and follow
    redirects, which real portals require.
    """

    source_id = "opendata"

    def __init__(
        self,
        portal_url: str = "https://catalog.data.gov",
        *,
        rows: int = 20,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.portal_url = portal_url.rstrip("/")
        self.rows = rows
        self.timeout = timeout
        self._client = client

    def discover(self, seed_niche: str) -> list[dict[str, Any]]:
        if not seed_niche:
            raise SourceError("OpenDataSource requires a non-empty seed niche")
        endpoint = f"{self.portal_url}/api/3/action/package_search"
        params = {"q": seed_niche, "rows": str(self.rows)}
        try:
            payload = self._fetch(endpoint, params)
        except httpx.HTTPError as exc:
            raise SourceError(f"open-data portal request failed: {exc}") from exc

        if not payload.get("success", False):
            raise SourceError("open-data portal returned success=false")

        packages = payload.get("result", {}).get("results", [])
        candidates: list[dict[str, Any]] = []
        for package in packages:
            candidate = self._package_to_candidate(package)
            if candidate is not None:
                candidates.append(candidate)

        log_event(
            _log,
            "source.opendata.discover",
            portal=self.portal_url,
            seed=seed_niche,
            count=len(candidates),
        )
        return candidates

    def _fetch(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        # A descriptive User-Agent (polite crawling) and redirect-following are
        # required by real portals — e.g. data.gov.uk 301-redirects to its CKAN
        # host. Learned from live integration testing.
        headers = {"User-Agent": _USER_AGENT}
        if self._client is not None:
            response = self._client.get(endpoint, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            response = client.get(endpoint, params=params, headers=headers)
            response.raise_for_status()
            return response.json()

    def _package_to_candidate(self, package: dict[str, Any]) -> dict[str, Any] | None:
        resources = package.get("resources", []) or []
        if not resources:
            return None
        # Prefer a tabular resource for the primary dataset URL.
        primary = _pick_primary_resource(resources)
        if primary is None:
            return None
        formats = sorted(
            {str(r.get("format", "")).lower() for r in resources if r.get("format")}
        )
        name = package.get("name") or package.get("id") or "unknown-dataset"
        return {
            "niche_id": str(name),
            "target_dataset_url": str(primary.get("url", "")),
            "primary_keywords": _extract_keywords(package),
            "data_sources_available": formats,
            "source": self.source_id,
        }


_TABULAR_FORMATS = {"csv", "tsv", "json", "parquet", "xls", "xlsx"}


def _pick_primary_resource(resources: list[dict[str, Any]]) -> dict[str, Any] | None:
    for resource in resources:
        if str(resource.get("format", "")).lower() in _TABULAR_FORMATS and resource.get("url"):
            return resource
    # Fall back to the first resource with any URL.
    for resource in resources:
        if resource.get("url"):
            return resource
    return None


def _extract_keywords(package: dict[str, Any]) -> list[str]:
    tags = package.get("tags", []) or []
    keywords = [str(t.get("name")) for t in tags if isinstance(t, dict) and t.get("name")]
    return keywords[:10]


def _matches_seed(candidate: dict[str, Any], needle: str) -> bool:
    if needle in str(candidate.get("niche_id", "")).lower():
        return True
    for keyword in candidate.get("primary_keywords", []) or []:
        if needle in str(keyword).lower():
            return True
    return False
