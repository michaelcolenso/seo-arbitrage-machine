"""Tests for the Scout candidate sources."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from dsf_scout.sources import ManifestSource, OpenDataSource, SourceError


def test_manifest_source_reads_candidates(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps({"candidates": [{"niche_id": "a"}, {"niche_id": "b"}]}), encoding="utf-8"
    )
    source = ManifestSource(path)
    results = source.discover("")
    assert {c["niche_id"] for c in results} == {"a", "b"}
    assert all(c["source"] == "manifest" for c in results)


def test_manifest_source_filters_by_seed(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            [
                {"niche_id": "osha_safety", "primary_keywords": ["osha lookup"]},
                {"niche_id": "faa_drone", "primary_keywords": ["airspace"]},
            ]
        ),
        encoding="utf-8",
    )
    source = ManifestSource(path)
    results = source.discover("osha")
    assert [c["niche_id"] for c in results] == ["osha_safety"]


def test_manifest_source_missing_file_raises(tmp_path: Path) -> None:
    source = ManifestSource(tmp_path / "nope.json")
    with pytest.raises(SourceError):
        source.discover("")


def test_open_data_source_parses_ckan_packages() -> None:
    ckan_payload = {
        "success": True,
        "result": {
            "results": [
                {
                    "name": "osha-inspections",
                    "tags": [{"name": "safety"}, {"name": "osha"}],
                    "resources": [
                        {"format": "CSV", "url": "https://data.gov/osha.csv"},
                        {"format": "PDF", "url": "https://data.gov/osha.pdf"},
                    ],
                },
                {
                    "name": "no-resources",
                    "resources": [],
                },
            ]
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/3/action/package_search"
        assert request.url.params.get("q") == "osha"
        return httpx.Response(200, json=ckan_payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    source = OpenDataSource("https://catalog.data.gov", client=client)
    results = source.discover("osha")

    assert len(results) == 1  # the resource-less package is skipped
    candidate = results[0]
    assert candidate["niche_id"] == "osha-inspections"
    assert candidate["target_dataset_url"] == "https://data.gov/osha.csv"
    assert "csv" in candidate["data_sources_available"]
    assert candidate["source"] == "opendata"
    client.close()


def test_open_data_source_http_error_raises_source_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    source = OpenDataSource("https://catalog.data.gov", client=client)
    with pytest.raises(SourceError):
        source.discover("osha")
    client.close()
