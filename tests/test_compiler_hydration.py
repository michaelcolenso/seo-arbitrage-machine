"""Unit tests for the pure hydration payload builders."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from dsf_compiler.hydration import (
    build_calculator_block,
    build_meta_payload,
    build_routes_payload,
    build_rows_payload,
    route_slug,
)
from dsf_engine.models import (
    ArbitrageOpportunity,
    Evaluation,
    MonetizationPattern,
    TemplateType,
)


def test_build_rows_payload_limits_and_sanitises() -> None:
    rows = [
        {"a": 1, "d": date(2026, 1, 2), "n": Decimal("3.50"), "x": Decimal("4")},
        {"a": 2, "d": date(2026, 1, 3), "n": Decimal("1.00"), "x": Decimal("9")},
        {"a": 3, "d": date(2026, 1, 4), "n": Decimal("2.00"), "x": Decimal("7")},
    ]
    out = build_rows_payload(rows, limit=2)
    assert len(out) == 2
    assert out[0]["d"] == "2026-01-02"  # date -> ISO string
    assert out[0]["n"] == 3.5  # non-integral Decimal -> float
    assert out[0]["x"] == 4 and isinstance(out[0]["x"], int)  # integral Decimal -> int


def test_build_rows_payload_nulls_non_finite_floats() -> None:
    rows = [{"a": float("nan"), "b": float("inf"), "c": float("-inf"), "d": 1.5}]
    out = build_rows_payload(rows)
    assert out[0]["a"] is None
    assert out[0]["b"] is None
    assert out[0]["c"] is None
    assert out[0]["d"] == 1.5
    # The result is strict-JSON serialisable (no NaN/Infinity tokens).
    text = json.dumps(out, allow_nan=False)
    assert "NaN" not in text and "Infinity" not in text


def test_build_rows_payload_nulls_non_finite_decimals() -> None:
    out = build_rows_payload([{"x": Decimal("NaN"), "y": Decimal("2.5")}])
    assert out[0]["x"] is None
    assert out[0]["y"] == 2.5


def test_route_slug() -> None:
    assert route_slug("Austin, TX!") == "austin-tx"
    assert route_slug("  Solar / Wind  ") == "solar-wind"


def test_build_routes_payload_groups_by_columns() -> None:
    rows = [
        {"city": "Austin", "category": "chemical", "n": 1},
        {"city": "Austin", "category": "chemical", "n": 2},
        {"city": "Denver", "category": "hvac", "n": 3},
    ]
    columns = [
        {"name": "city", "type": "VARCHAR"},
        {"name": "category", "type": "VARCHAR"},
        {"name": "n", "type": "BIGINT"},
    ]
    routes = build_routes_payload(
        rows, columns, route_columns=["city", "category"], niche_title="Compliance"
    )
    assert sorted(r["path"] for r in routes) == ["/austin/chemical", "/denver/hvac"]
    austin = next(r for r in routes if r["path"] == "/austin/chemical")
    assert austin["row_count"] == 2
    assert austin["params"] == {"city": "Austin", "category": "chemical"}
    assert "Compliance" in austin["title"]


def test_build_routes_payload_empty_without_route_columns() -> None:
    rows = [{"a": 1}]
    columns = [{"name": "a", "type": "BIGINT"}]
    assert build_routes_payload(rows, columns, route_columns=["missing"], niche_title="X") == []


def test_build_routes_payload_skips_null_keys() -> None:
    rows = [{"city": "Austin", "n": 1}, {"city": None, "n": 2}, {"city": "", "n": 3}]
    columns = [{"name": "city", "type": "VARCHAR"}, {"name": "n", "type": "BIGINT"}]
    routes = build_routes_payload(rows, columns, route_columns=["city"], niche_title="X")
    assert [r["path"] for r in routes] == ["/austin"]


def test_build_calculator_block_picks_numeric_columns() -> None:
    columns = [
        {"name": "company", "type": "VARCHAR"},
        {"name": "violations", "type": "BIGINT"},
        {"name": "penalty_usd", "type": "DOUBLE"},
    ]
    block = build_calculator_block(columns)
    keys = [i["key"] for i in block["inputs"]]
    assert keys == ["violations", "penalty_usd"]
    assert "company" not in keys


def _evaluation() -> Evaluation:
    return Evaluation(
        monetization_pattern=MonetizationPattern.LOCAL_LEAD_GENERATION,
        template_type=TemplateType.DIRECTORY,
        seo_route_pattern="/{city}/{category}",
        seo_high_volume_columns='["city", "category"]',
        seo_sample_routes='["/austin/chemical"]',
        confidence=0.81,
    )


def test_build_meta_payload_contract() -> None:
    opportunity = ArbitrageOpportunity(
        niche_id="b2b_industrial_chemical_compliance",
        target_dataset_url="https://example.gov/data.csv",
    )
    columns = [
        {"name": "company", "type": "VARCHAR"},
        {"name": "violations", "type": "BIGINT"},
    ]
    meta = build_meta_payload(_evaluation(), opportunity, columns)

    assert meta["template_type"] == "directory"
    assert meta["monetization_pattern"] == "local_lead_generation"
    assert meta["lead_gen"] is True
    assert meta["niche_id"] == "b2b_industrial_chemical_compliance"
    assert meta["title"] == "B2B Industrial Chemical Compliance"
    assert meta["columns"] == ["company", "violations"]
    assert meta["seo"]["high_volume_columns"] == ["city", "category"]
    assert meta["seo"]["route_pattern"] == "/{city}/{category}"
    assert "generated_at" in meta


def test_build_meta_payload_non_lead_gen() -> None:
    evaluation = _evaluation()
    evaluation.monetization_pattern = MonetizationPattern.PREMIUM_CPC
    meta = build_meta_payload(evaluation, None, [])
    assert meta["lead_gen"] is False
    assert meta["niche_id"] is None
    assert meta["title"] == "DataSiteForge Site"
