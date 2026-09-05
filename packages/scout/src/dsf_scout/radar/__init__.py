"""Radar — scalable keyword discovery and money-first opportunity triage."""

from .models import KeywordCandidate, RadarDecision, ScoredCandidate, ScanStatus
from .scoring import score_candidate

__all__ = [
    "KeywordCandidate",
    "RadarDecision",
    "ScoredCandidate",
    "ScanStatus",
    "score_candidate",
]
