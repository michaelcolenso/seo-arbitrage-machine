"""Regression checks for the lean revenue-test microsites."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments" / "revenue_tests"


def _page(slug: str) -> str:
    path = EXPERIMENTS / slug / "index.html"
    assert path.is_file(), f"missing revenue-test page: {slug}"
    return path.read_text(encoding="utf-8")


def test_revenue_test_pages_exist_and_capture_high_intent_actions() -> None:
    for slug in ("permit-signal", "sbir-signal", "site-constraint"):
        text = _page(slug)
        assert f'action="/lead/{slug}"' in text
        assert 'name="email"' in text
        assert 'name="price_intent"' in text
        assert 'name="request_type"' in text
        assert "paid" in text.lower()


def test_permit_signal_is_not_a_homeowner_contact_scraper() -> None:
    text = _page("permit-signal").lower()
    assert "no homeowner scraping" in text
    assert "does not collect or resell private homeowner contact data" in text


def test_site_constraint_keeps_regulatory_boundary_explicit() -> None:
    text = _page("site-constraint").lower()
    for phrase in (
        "not a substitute for ipac",
        "not a substitute for",
        "official species list",
        "esa determination",
        "phase i esa",
    ):
        assert phrase in text


def test_experiment_readme_has_success_and_kill_gates() -> None:
    text = (EXPERIMENTS / "README.md").read_text(encoding="utf-8").lower()
    assert text.count("success gate") >= 3
    assert text.count("kill/reshape signal") >= 3
    assert "actual payment / signed pilot" in text
