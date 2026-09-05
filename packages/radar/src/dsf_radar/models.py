"""Domain models for high-volume keyword scanning and business promotion."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScanStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RadarDecision(str, enum.Enum):
    REJECT = "REJECT"
    REVIEW = "REVIEW"
    PROMOTE = "PROMOTE"


class KeywordCandidate(BaseModel):
    """One keyword plus optional business-enrichment evidence.

    SEO fields are sufficient for first-pass triage. Business fields are optional
    because they are expected to be populated only for the much smaller REVIEW set.
    A row with missing business evidence can never be PROMOTED.
    """

    keyword: str = Field(min_length=1)
    source: str = "unknown"
    volume: int = Field(default=0, ge=0)
    cpc: float = Field(default=0.0, ge=0.0)
    kd: float = Field(default=100.0, ge=0.0, le=100.0)
    intent: str = "unknown"

    buyer: str | None = None
    decision_value: float | None = Field(default=None, ge=0.0, le=10.0)
    monetization_ease: float | None = Field(default=None, ge=0.0, le=10.0)
    defensibility: float | None = Field(default=None, ge=0.0, le=10.0)
    complexity: float | None = Field(default=None, ge=1.0, le=10.0)
    data_leverage: float | None = Field(default=None, ge=0.0, le=10.0)
    evidence_quality: float | None = Field(default=None, ge=0.0, le=10.0)


class ScoredCandidate(BaseModel):
    keyword: str
    source: str
    scan_score: float = Field(ge=0.0, le=100.0)
    business_score: float | None = Field(default=None, ge=0.0, le=100.0)
    opportunity_score: float | None = Field(default=None, ge=0.0, le=100.0)
    decision: RadarDecision
    reasons: list[str] = Field(default_factory=list)
    scored_at: datetime = Field(default_factory=utcnow)
    candidate: KeywordCandidate


class ScanSummary(BaseModel):
    run_id: str
    name: str
    status: ScanStatus
    total_expected: int | None = None
    processed_count: int = 0
    promoted_count: int = 0
    review_count: int = 0
    rejected_count: int = 0
    error_count: int = 0
    spend_usd: float = 0.0
    checkpoint: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def completion_ratio(self) -> float | None:
        if not self.total_expected:
            return None
        return min(1.0, self.processed_count / self.total_expected)
