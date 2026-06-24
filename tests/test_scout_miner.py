"""Tests for the arbitrage miner's scoring and reflective filtering."""

from __future__ import annotations

from dsf_scout.miner import ArbitrageMiner
from dsf_scout.models import MonetizationVector, RejectionReason


def _candidate(**overrides) -> dict:
    base = {
        "niche_id": "compliance_demo",
        "target_dataset_url": "https://example.gov/dataset.csv",
        "primary_keywords": ["compliance lookup"],
        "estimated_monthly_volume": 45000,
        "average_cpc": 14.50,
        "keyword_difficulty": 12,
        "data_sources_available": ["a", "b", "c"],
        "monetization_vector": "LEAD_GEN",
        "estimated_lead_value": 175.00,
        "uniqueness_potential_ratio": 0.82,
    }
    base.update(overrides)
    return base


def test_high_value_candidate_is_accepted_and_scored() -> None:
    miner = ArbitrageMiner()
    result = miner.evaluate_candidates([_candidate()])
    assert result.accepted_count == 1
    assert result.rejected_count == 0
    opp = result.accepted[0]
    # (45000 * 14.5) / (12 * 1.0) * (3.5 + 175/100) = 54375 * 5.25 = 285468.75
    assert opp.arbitrage_score == 285468.75


def test_few_sources_incur_extraction_penalty() -> None:
    miner = ArbitrageMiner()
    full = miner.evaluate_candidates([_candidate()]).accepted[0]
    penalised = miner.evaluate_candidates(
        [_candidate(data_sources_available=["only_one"])]
    ).accepted[0]
    # Penalty divides the denominator by 2.5, so the score drops to 40%.
    assert penalised.arbitrage_score < full.arbitrage_score
    assert round(penalised.arbitrage_score / full.arbitrage_score, 2) == 0.40


def test_uniqueness_below_threshold_is_rejected_not_dropped() -> None:
    miner = ArbitrageMiner()
    result = miner.evaluate_candidates([_candidate(uniqueness_potential_ratio=0.55)])
    assert result.accepted_count == 0
    assert result.rejected_count == 1
    assert result.rejected[0].reason == RejectionReason.UNIQUENESS_BELOW_THRESHOLD


def test_high_difficulty_is_rejected() -> None:
    miner = ArbitrageMiner()
    result = miner.evaluate_candidates([_candidate(keyword_difficulty=80)])
    assert result.rejected[0].reason == RejectionReason.KEYWORD_DIFFICULTY_TOO_HIGH


def test_schema_invalid_candidate_is_reflected() -> None:
    miner = ArbitrageMiner()
    # keyword_difficulty out of range (le=100) triggers a ValidationError.
    result = miner.evaluate_candidates(
        [{"niche_id": "bad", "target_dataset_url": "x", "keyword_difficulty": 999}]
    )
    assert result.accepted_count == 0
    assert result.rejected[0].reason == RejectionReason.SCHEMA_INVALID
    assert "keyword_difficulty" in result.rejected[0].detail


def test_results_sorted_by_descending_score() -> None:
    miner = ArbitrageMiner()
    low = _candidate(niche_id="low", estimated_monthly_volume=1000)
    high = _candidate(niche_id="high", estimated_monthly_volume=90000)
    result = miner.evaluate_candidates([low, high])
    assert [o.niche_id for o in result.accepted] == ["high", "low"]


def test_high_ticket_affiliate_multiplier() -> None:
    miner = ArbitrageMiner()
    opp = miner.evaluate_candidates(
        [_candidate(monetization_vector="HIGH_TICKET_AFFILIATE", estimated_lead_value=0.0)]
    ).accepted[0]
    assert opp.monetization_vector == MonetizationVector.HIGH_TICKET_AFFILIATE
    # (45000 * 14.5) / 12 * 2.0 = 108750.0
    assert opp.arbitrage_score == 108750.0
