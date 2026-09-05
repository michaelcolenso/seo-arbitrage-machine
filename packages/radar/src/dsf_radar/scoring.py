"""Deterministic two-stage scoring for Radar.

Stage one is intentionally cheap enough for a million-row scan. Stage two follows
the OpportunityForge thesis: demand matters, but a build decision is dominated by
decision value, monetization, defensibility, complexity and evidence.
"""

from __future__ import annotations

import math

from .models import KeywordCandidate, RadarDecision, ScoredCandidate

_INTENT_SCORE = {
    "transactional": 10.0,
    "commercial": 9.0,
    "comparison": 8.5,
    "local": 8.0,
    "navigational": 5.0,
    "informational": 4.0,
    "unknown": 3.0,
}


def _clamp(value: float, low: float = 0.0, high: float = 10.0) -> float:
    return max(low, min(high, value))


def scan_dimensions(candidate: KeywordCandidate) -> dict[str, float]:
    """Return 0-10 dimensions used by the inexpensive scan stage."""
    demand = _clamp(math.log10(candidate.volume + 1) * 2.0)
    cpc = _clamp(candidate.cpc * 2.0)
    feasibility = _clamp(10.0 - candidate.kd / 10.0)
    intent = _INTENT_SCORE.get(candidate.intent.strip().lower(), 3.0)
    return {
        "demand": demand,
        "cpc": cpc,
        "feasibility": feasibility,
        "intent": intent,
    }


def score_candidate(
    candidate: KeywordCandidate,
    *,
    review_threshold: float = 55.0,
    promote_threshold: float = 65.0,
    min_business_dimension: float = 5.0,
    min_evidence_quality: float = 5.0,
) -> ScoredCandidate:
    dims = scan_dimensions(candidate)
    scan_score = round(
        10.0
        * (
            dims["demand"] * 0.30
            + dims["cpc"] * 0.30
            + dims["feasibility"] * 0.25
            + dims["intent"] * 0.15
        ),
        2,
    )

    reasons: list[str] = []
    business_values = (
        candidate.decision_value,
        candidate.monetization_ease,
        candidate.defensibility,
        candidate.complexity,
        candidate.data_leverage,
        candidate.evidence_quality,
    )
    enriched = bool(candidate.buyer and all(v is not None for v in business_values))

    if not enriched:
        if scan_score >= review_threshold:
            return ScoredCandidate(
                keyword=candidate.keyword,
                source=candidate.source,
                scan_score=scan_score,
                decision=RadarDecision.REVIEW,
                reasons=["SEO economics justify business enrichment; buyer/evidence incomplete"],
                candidate=candidate,
            )
        return ScoredCandidate(
            keyword=candidate.keyword,
            source=candidate.source,
            scan_score=scan_score,
            decision=RadarDecision.REJECT,
            reasons=[f"scan score {scan_score:.1f} below review threshold {review_threshold:.1f}"],
            candidate=candidate,
        )

    assert candidate.decision_value is not None
    assert candidate.monetization_ease is not None
    assert candidate.defensibility is not None
    assert candidate.complexity is not None
    assert candidate.data_leverage is not None
    assert candidate.evidence_quality is not None

    # OpportunityForge: (Demand × Decision Value × Monetization Ease × Defensibility)
    # / Complexity. Squash the unbounded raw value into a stable 0-100 scale.
    raw_business = (
        dims["demand"]
        * candidate.decision_value
        * candidate.monetization_ease
        * candidate.defensibility
    ) / max(candidate.complexity, 1.0)
    business_score = round(100.0 * raw_business / (raw_business + 100.0), 2)

    opportunity_score = round(
        business_score * 0.70
        + scan_score * 0.15
        + candidate.data_leverage * 10.0 * 0.075
        + candidate.evidence_quality * 10.0 * 0.075,
        2,
    )

    if candidate.decision_value < min_business_dimension:
        reasons.append("decision value below promotion gate")
    if candidate.monetization_ease < min_business_dimension:
        reasons.append("monetization ease below promotion gate")
    if candidate.defensibility < min_business_dimension:
        reasons.append("defensibility below promotion gate")
    if candidate.evidence_quality < min_evidence_quality:
        reasons.append("evidence quality below promotion gate")
    if opportunity_score < promote_threshold:
        reasons.append(
            f"opportunity score {opportunity_score:.1f} below promotion threshold {promote_threshold:.1f}"
        )

    decision = RadarDecision.PROMOTE if not reasons else RadarDecision.REVIEW
    if decision == RadarDecision.PROMOTE:
        reasons.append("buyer and money-first promotion gates passed")

    return ScoredCandidate(
        keyword=candidate.keyword,
        source=candidate.source,
        scan_score=scan_score,
        business_score=business_score,
        opportunity_score=opportunity_score,
        decision=decision,
        reasons=reasons,
        candidate=candidate,
    )
