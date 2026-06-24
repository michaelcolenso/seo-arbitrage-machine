"""The arbitrage miner: economic leverage scoring and reflective filtering.

This is the corrected, agent-native form of the scoring engine.  Two deliberate
departures from a naive implementation:

1. **No silent drops.**  Every rejected candidate is captured as a
   :class:`~dsf_scout.models.RejectedCandidate` with a machine-readable reason,
   so an orchestrating agent can reflect and correct its inputs (Pillar 3).
2. **The uniqueness guardrail is enforced here, not in the schema.**  Constraining
   the Pydantic field to ``>= 0.60`` would turn a below-threshold candidate into a
   ``ValidationError`` that the filter loop would swallow — making the explicit
   guardrail dead code.  Enforcing it in the miner keeps the rejection observable.
"""

from __future__ import annotations

from typing import Any

from dsf_core.telemetry import get_logger, log_event
from pydantic import ValidationError

from .models import (
    ArbitrageOpportunity,
    MiningResult,
    MonetizationVector,
    RejectedCandidate,
    RejectionReason,
)

_log = get_logger("scout.miner")

# Tuning constants for the leverage equation.
_EXTRACTION_PENALTY_FEW_SOURCES = 2.5
_MIN_DISTINCT_SOURCES = 3
_LEAD_GEN_BASE_MULTIPLIER = 3.5
_HIGH_TICKET_MULTIPLIER = 2.0


class ArbitrageMiner:
    """Scores and filters candidate niches by structural arbitrage yield."""

    def __init__(
        self,
        *,
        min_uniqueness_threshold: float = 0.60,
        max_difficulty_ceiling: int = 35,
    ) -> None:
        self.min_uniqueness_threshold = min_uniqueness_threshold
        self.max_difficulty_ceiling = max_difficulty_ceiling

    def calculate_leverage_score(self, opp: ArbitrageOpportunity) -> float:
        """Compute the structural yield score for an opportunity.

        ``score = (volume * cpc) / (difficulty * extraction_complexity) * multiplier``

        where extraction complexity penalises candidates that cannot cross-reference
        at least three distinct data sources, and the multiplier rewards immediate
        cash-injection monetisation vectors.
        """
        difficulty_weight = max(opp.keyword_difficulty, 1)

        extraction_complexity = 1.0
        if len(opp.data_sources_available) < _MIN_DISTINCT_SOURCES:
            extraction_complexity = _EXTRACTION_PENALTY_FEW_SOURCES

        base_traffic_value = opp.estimated_monthly_volume * opp.average_cpc
        efficiency_denominator = difficulty_weight * extraction_complexity

        multiplier = 1.0
        if opp.monetization_vector == MonetizationVector.LEAD_GEN:
            multiplier = _LEAD_GEN_BASE_MULTIPLIER + (opp.estimated_lead_value / 100.0)
        elif opp.monetization_vector == MonetizationVector.HIGH_TICKET_AFFILIATE:
            multiplier = _HIGH_TICKET_MULTIPLIER

        score = (base_traffic_value / efficiency_denominator) * multiplier
        return round(score, 2)

    def evaluate_candidates(self, candidates: list[dict[str, Any]]) -> MiningResult:
        """Score and filter raw candidate dicts into an observable result.

        Candidates are accepted only if they parse cleanly, fall within the
        difficulty ceiling, and meet the uniqueness threshold.  Accepted
        opportunities are returned sorted by descending arbitrage score.
        """
        result = MiningResult()

        for item in candidates:
            niche_id = str(item.get("niche_id", "<unknown>"))
            try:
                opp = ArbitrageOpportunity(**item)
            except ValidationError as exc:
                result.rejected.append(
                    RejectedCandidate(
                        niche_id=niche_id,
                        reason=RejectionReason.SCHEMA_INVALID,
                        detail=_summarise_validation_error(exc),
                    )
                )
                log_event(
                    _log, "miner.reject", niche_id=niche_id, reason="schema_invalid"
                )
                continue

            if opp.keyword_difficulty > self.max_difficulty_ceiling:
                result.rejected.append(
                    RejectedCandidate(
                        niche_id=opp.niche_id,
                        reason=RejectionReason.KEYWORD_DIFFICULTY_TOO_HIGH,
                        detail=(
                            f"KD {opp.keyword_difficulty} exceeds ceiling "
                            f"{self.max_difficulty_ceiling}"
                        ),
                    )
                )
                log_event(
                    _log,
                    "miner.reject",
                    niche_id=opp.niche_id,
                    reason="keyword_difficulty_too_high",
                    kd=opp.keyword_difficulty,
                )
                continue

            if opp.uniqueness_potential_ratio < self.min_uniqueness_threshold:
                result.rejected.append(
                    RejectedCandidate(
                        niche_id=opp.niche_id,
                        reason=RejectionReason.UNIQUENESS_BELOW_THRESHOLD,
                        detail=(
                            f"uniqueness {opp.uniqueness_potential_ratio:.2f} below "
                            f"threshold {self.min_uniqueness_threshold:.2f}"
                        ),
                    )
                )
                log_event(
                    _log,
                    "miner.reject",
                    niche_id=opp.niche_id,
                    reason="uniqueness_below_threshold",
                    ratio=opp.uniqueness_potential_ratio,
                )
                continue

            opp.arbitrage_score = self.calculate_leverage_score(opp)
            result.accepted.append(opp)
            log_event(
                _log, "miner.accept", niche_id=opp.niche_id, score=opp.arbitrage_score
            )

        result.accepted.sort(key=lambda o: o.arbitrage_score, reverse=True)
        return result


def _summarise_validation_error(exc: ValidationError) -> str:
    """Render a compact, LLM-friendly summary of a Pydantic validation error."""
    parts: list[str] = []
    for error in exc.errors():
        location = ".".join(str(loc) for loc in error.get("loc", ()))
        parts.append(f"{location or '<root>'}: {error.get('msg', 'invalid')}")
    return "; ".join(parts) if parts else str(exc)
