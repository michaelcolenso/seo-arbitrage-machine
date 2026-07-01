"""Real keyword metrics from the Ahrefs API v3.

When an ``AHREFS_API_TOKEN`` is configured, the Scout uses this to replace the
mock keyword volume / CPC / difficulty with *real* market data, so arbitrage
scores reflect reality.  Without a token it is simply unavailable and the Scout
falls back to the Agent Bridge (mock) enrichment.

Response-envelope parsing is intentionally defensive: the exact JSON shape of
``keywords-explorer/overview`` is pinned by the gated live test
(``tests/test_live.py``), not guessed here.
"""

from __future__ import annotations

from typing import Any

import httpx
from dsf_core.config import Settings, get_settings
from dsf_core.telemetry import get_logger, log_event

_log = get_logger("scout.ahrefs")

_AHREFS_BASE = "https://api.ahrefs.com/v3"
# Fields Ahrefs owns for a keyword; these override any candidate estimates.
_OVERVIEW_SELECT = "keyword,volume,cpc,difficulty"


class AhrefsError(RuntimeError):
    """Raised when the Ahrefs API is unavailable or returns an error."""


class AhrefsEnricher:
    """Fetches real keyword metrics for a candidate's primary keywords."""

    source_id = "ahrefs"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        country: str = "us",
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.country = country
        self._client = client

    def available(self) -> bool:
        return bool(self.settings.ahrefs_api_token)

    def enrich(self, candidate: dict[str, Any]) -> dict[str, Any]:
        """Return real ``{estimated_monthly_volume, average_cpc, keyword_difficulty}``.

        Uses the highest-volume of the candidate's ``primary_keywords`` as the
        representative term.  Returns ``{}`` when there are no keywords or no data.
        """
        if not self.settings.ahrefs_api_token:
            raise AhrefsError("AHREFS_API_TOKEN is not configured")
        keywords = [str(k) for k in (candidate.get("primary_keywords") or []) if k]
        if not keywords:
            return {}

        rows = self._overview(keywords)
        if not rows:
            return {}
        best = max(rows, key=lambda r: _num(r.get("volume")))
        volume = int(_num(best.get("volume")))
        # Ahrefs returns CPC in USD cents (per the API convention).
        cpc_usd = round(_num(best.get("cpc")) / 100.0, 2)
        difficulty = int(_num(best.get("difficulty") or best.get("keyword_difficulty")))
        log_event(
            _log,
            "ahrefs.enrich",
            niche_id=candidate.get("niche_id"),
            keyword=best.get("keyword"),
            volume=volume,
            kd=difficulty,
        )
        return {
            "estimated_monthly_volume": volume,
            "average_cpc": cpc_usd,
            "keyword_difficulty": difficulty,
        }

    def _overview(self, keywords: list[str]) -> list[dict[str, Any]]:
        params = {
            "select": _OVERVIEW_SELECT,
            "country": self.country,
            "keywords": ", ".join(keywords),
        }
        headers = {
            "Authorization": f"Bearer {self.settings.ahrefs_api_token}",
            "Accept": "application/json",
        }
        url = f"{_AHREFS_BASE}/keywords-explorer/overview"
        try:
            if self._client is not None:
                response = self._client.get(url, params=params, headers=headers)
            else:
                with httpx.Client(timeout=60.0, follow_redirects=True) as client:
                    response = client.get(url, params=params, headers=headers)
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            raise AhrefsError(f"Ahrefs API request failed: {exc}") from exc
        return _extract_rows(body)


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _extract_rows(body: Any) -> list[dict[str, Any]]:
    """Pull the keyword-row list out of an Ahrefs response (shape-tolerant)."""
    if isinstance(body, list):
        return [r for r in body if isinstance(r, dict)]
    if isinstance(body, dict):
        for key in ("keywords", "metrics", "results", "data"):
            value = body.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    return []
