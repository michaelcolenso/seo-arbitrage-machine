"""Regression guard for the real-metric validation query."""

from __future__ import annotations

from pathlib import Path


def test_top25_validator_joins_canonical_opportunity_graph_table() -> None:
    script = (
        Path(__file__).resolve().parents[1] / "scripts" / "validate_top25.py"
    ).read_text(encoding="utf-8")

    assert "JOIN opportunity_graph_nodes n ON n.id = c.opportunity_node_id" in script
    assert "JOIN opportunity_nodes n ON n.id = c.opportunity_node_id" not in script
