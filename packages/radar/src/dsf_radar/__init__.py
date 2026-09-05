"""DataSiteForge Radar — scalable keyword discovery and opportunity triage."""

from .models import KeywordCandidate, RadarDecision, ScoredCandidate, ScanStatus
from .scoring import score_candidate

__all__ = [
    "KeywordCandidate",
    "RadarDecision",
    "ScoredCandidate",
    "ScanStatus",
    "score_candidate",
]

__version__ = "0.1.0"
