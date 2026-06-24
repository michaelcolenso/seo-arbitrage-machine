"""Scoring models for the Scout's arbitrage miner.

``ArbitrageOpportunity`` is the in-memory model the miner scores and ranks; it
serialises into the durable :class:`dsf_engine.models.ArbitrageOpportunity`
ledger table.  Note the deliberate design choice on ``uniqueness_potential_ratio``:
the field is *not* constrained to ``>= 0.60`` at the model level — that threshold
is a business guardrail enforced (and logged) by the miner, so a sub-threshold
candidate produces a structured rejection rather than a swallowed
``ValidationError``.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field


class MonetizationVector(str, enum.Enum):
    """Revenue mechanism a candidate maps to (mirrors the ledger enum)."""

    LEAD_GEN = "LEAD_GEN"
    HIGH_TICKET_AFFILIATE = "HIGH_TICKET_AFFILIATE"
    PER_CLICK = "PER_CLICK"


class RejectionReason(str, enum.Enum):
    """Why a candidate was rejected (surfaced for agent reflection)."""

    SCHEMA_INVALID = "schema_invalid"
    KEYWORD_DIFFICULTY_TOO_HIGH = "keyword_difficulty_too_high"
    UNIQUENESS_BELOW_THRESHOLD = "uniqueness_below_threshold"


class ArbitrageOpportunity(BaseModel):
    """A scored arbitrage candidate."""

    niche_id: str
    target_dataset_url: str
    primary_keywords: list[str] = Field(default_factory=list)
    estimated_monthly_volume: int = Field(default=0, ge=0)
    average_cpc: float = Field(default=0.0, ge=0.0)
    keyword_difficulty: int = Field(default=0, ge=0, le=100)
    data_sources_available: list[str] = Field(default_factory=list)
    monetization_vector: MonetizationVector = MonetizationVector.LEAD_GEN
    estimated_lead_value: float = Field(default=0.0, ge=0.0)
    # Business guardrail (>= 0.60) is enforced by the miner, not the schema.
    uniqueness_potential_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    arbitrage_score: float = 0.0
    source: str | None = None


class RejectedCandidate(BaseModel):
    """A candidate the miner declined, with a machine-readable reason."""

    niche_id: str
    reason: RejectionReason
    detail: str


class MiningResult(BaseModel):
    """The outcome of a single mining pass over a candidate pool."""

    accepted: list[ArbitrageOpportunity] = Field(default_factory=list)
    rejected: list[RejectedCandidate] = Field(default_factory=list)

    @property
    def accepted_count(self) -> int:
        return len(self.accepted)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)
