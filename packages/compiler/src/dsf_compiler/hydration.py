"""Pure payload builders for the data-hydration layer.

These functions contain no I/O and no database access — they transform ledger
objects and DuckDB rows into the strict JSON contract that the fixed-invariant
Astro templates consume.  Keeping them pure makes the riskiest part of
compilation (the template/data contract) trivially unit-testable.

The objects passed in are duck-typed: any object exposing the same attributes as
:class:`dsf_engine.models.Evaluation` / ``ArbitrageOpportunity`` works, so tests
can construct lightweight stand-ins or real (unsaved) SQLModel instances.
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Protocol

# DuckDB type-name fragments that indicate a numeric column.
_NUMERIC_TOKENS = (
    "INT", "DOUBLE", "FLOAT", "REAL", "DECIMAL", "NUMERIC", "HUGEINT", "BIGINT",
)


class _EvaluationLike(Protocol):
    seo_route_pattern: str | None
    seo_high_volume_columns: str
    seo_sample_routes: str
    confidence: float

    @property
    def template_type(self) -> Any: ...
    @property
    def monetization_pattern(self) -> Any: ...


def _enum_value(value: Any) -> Any:
    """Return ``value.value`` for enums, else the value unchanged."""
    return getattr(value, "value", value)


def _sanitise(value: Any) -> Any:
    """Coerce a DuckDB cell into a JSON-serialisable scalar.

    Non-finite floats (``NaN`` / ``±Infinity``) are coerced to ``None``: with
    ``json.dumps``'s default they would serialise to bare ``NaN``/``Infinity``
    tokens, which are invalid JSON and break Astro's JSON import at build time.
    """
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        # Preserve integers as ints, otherwise fall back to float.
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return str(value)


def build_rows_payload(rows: list[dict[str, Any]], limit: int = 500) -> list[dict[str, Any]]:
    """Trim and JSON-coerce DuckDB rows for ``src/data/rows.json``."""
    payload: list[dict[str, Any]] = []
    for row in rows[: max(limit, 0)]:
        payload.append({key: _sanitise(val) for key, val in row.items()})
    return payload


def _is_numeric(type_name: str | None) -> bool:
    upper = (type_name or "").upper()
    return any(token in upper for token in _NUMERIC_TOKENS)


def _title_from(niche_id: str | None) -> str:
    if not niche_id:
        return "DataSiteForge Site"
    return niche_id.replace("_", " ").replace("-", " ").title()


def title_from(niche_id: str | None) -> str:
    """Public alias for deriving a human title from a niche id."""
    return _title_from(niche_id)


def route_slug(value: str) -> str:
    """Slugify a single route segment value (lowercase alnum + hyphens)."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return slug


def build_routes_payload(
    rows: list[dict[str, Any]],
    columns: list[dict[str, Any]],
    *,
    route_columns: list[str],
    niche_title: str,
    max_routes: int = 500,
    max_dimensions: int = 2,
) -> list[dict[str, Any]]:
    """Materialise programmatic per-route pages from high-volume columns.

    Groups the (already-sanitised) rows by the distinct value combinations of the
    SEO route columns, producing one routed page per group — the long-tail fleet
    the SEO strategy depends on.  Returns ``[]`` when no usable route columns are
    present (the site then has only its hub/index page).
    """
    names = {c.get("name") for c in columns}
    cols = [c for c in route_columns if c in names][:max_dimensions]
    if not cols or not rows:
        return []

    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        key = tuple(row.get(col) for col in cols)
        if any(value is None or str(value).strip() == "" for value in key):
            continue
        groups.setdefault(key, []).append(row)

    # Biggest groups first so the route cap keeps the most populated pages.
    ordered = sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)
    routes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key, group in ordered[:max_routes]:
        values = [str(value) for value in key]
        segments = [route_slug(value) for value in values]
        if not all(segments):
            continue
        path = "/" + "/".join(segments)
        candidate = path
        suffix = 2
        while candidate in seen:  # disambiguate slug collisions
            candidate = f"{path}-{suffix}"
            suffix += 1
        seen.add(candidate)

        label = " · ".join(values)
        routes.append(
            {
                "path": candidate,
                "params": dict(zip(cols, values, strict=True)),
                "columns_used": cols,
                "title": f"{label} — {niche_title}" if niche_title else label,
                "description": (
                    f"{niche_title}: {label}. {len(group)} matching record(s)."
                    if niche_title
                    else f"{label}. {len(group)} matching record(s)."
                ),
                "row_count": len(group),
                "rows": group,
            }
        )
    return routes


def build_calculator_block(columns: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive a generic parametric calculator config from numeric columns."""
    numeric = [c for c in columns if _is_numeric(c.get("type"))]
    inputs = [
        {
            "key": col["name"],
            "label": str(col["name"]).replace("_", " ").title(),
            "default": 1,
            "weight": 1,
        }
        for col in numeric[:5]
    ]
    return {"base": 0, "result_label": "Estimated Value", "inputs": inputs}


def build_meta_payload(
    evaluation: _EvaluationLike,
    opportunity: Any | None,
    columns: list[dict[str, Any]],
    *,
    canonical_base: str | None = None,
    route_count: int = 0,
) -> dict[str, Any]:
    """Assemble the strict ``src/data/meta.json`` contract.

    ``columns`` is the DuckDB profile column list (``[{"name", "type"}, ...]``).
    ``canonical_base`` is the site's absolute origin (e.g. ``https://<slug>.pages.dev``)
    used for canonical links and the sitemap; ``route_count`` is the number of
    programmatic pages generated alongside the index.
    """
    niche_id = getattr(opportunity, "niche_id", None)
    monetization = _enum_value(evaluation.monetization_pattern)
    template_type = _enum_value(evaluation.template_type)

    meta: dict[str, Any] = {
        "niche_id": niche_id,
        "title": _title_from(niche_id),
        "description": getattr(opportunity, "target_dataset_url", "") or "",
        "template_type": template_type,
        "monetization_pattern": monetization,
        "canonical_base": canonical_base or "",
        "route_count": route_count,
        "seo": {
            "route_pattern": evaluation.seo_route_pattern,
            "high_volume_columns": json.loads(evaluation.seo_high_volume_columns or "[]"),
            "sample_routes": json.loads(evaluation.seo_sample_routes or "[]"),
        },
        "columns": [c["name"] for c in columns],
        "lead_gen": monetization == "local_lead_generation",
        "lead_webhook": "",
        "confidence": evaluation.confidence,
        "calculator": build_calculator_block(columns),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return meta
