"""Provider-neutral opportunity evidence scoring.

Evidence quality is deliberately separate from opportunity score: a compelling
hypothesis with weak evidence remains a hypothesis.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EvidenceGrade = Literal["A", "B", "C", "D"]
EvidenceState = Literal["HYPOTHESIS", "EVIDENCE_GATHERING", "VALIDATED", "REJECTED"]


class EvidenceItem(BaseModel):
    kind: Literal["demand", "pain", "money", "serp_weakness", "buildability", "outcome"]
    source: str
    observed_at: str
    summary: str
    url: str | None = None
    strength: int = Field(ge=1, le=5)


class EvidenceDossier(BaseModel):
    opportunity_key: str
    label: str
    demand: int = Field(ge=0, le=5)
    pain: int = Field(ge=0, le=5)
    money: int = Field(ge=0, le=5)
    serp_weakness: int = Field(ge=0, le=5)
    buildability: int = Field(ge=0, le=5)
    evidence_grade: EvidenceGrade
    items: list[EvidenceItem] = Field(default_factory=list)
    paid_commitment: bool = False
    repeat_use: bool = False


class EvidenceVerdict(BaseModel):
    opportunity_key: str
    score: float = Field(ge=0, le=100)
    evidence_grade: EvidenceGrade
    state: EvidenceState
    reasons: list[str]


_WEIGHTS = {
    "demand": 0.20,
    "pain": 0.20,
    "money": 0.25,
    "serp_weakness": 0.15,
    "buildability": 0.20,
}


def score_dossier(d: EvidenceDossier) -> EvidenceVerdict:
    raw = sum(getattr(d, k) * w for k, w in _WEIGHTS.items())
    score = round(raw / 5 * 100, 1)
    reasons: list[str] = []

    if d.money < 2:
        reasons.append("fatal gate: weak evidence that buyers spend money on this job")
    if d.buildability < 2:
        reasons.append("fatal gate: data/product is not presently buildable")
    if d.evidence_grade == "D":
        reasons.append("fatal gate: evidence is too weak to validate")

    if reasons:
        state: EvidenceState = "REJECTED"
    elif d.paid_commitment or d.repeat_use:
        state = "VALIDATED"
        reasons.append("behavioral evidence: payment or repeat use observed")
    elif score >= 80 and d.evidence_grade in ("A", "B"):
        state = "EVIDENCE_GATHERING"
        reasons.append("strong research case; behavioral validation still required")
    elif score >= 60:
        state = "EVIDENCE_GATHERING"
        reasons.append("promising research case; more evidence required")
    else:
        state = "HYPOTHESIS"
        reasons.append("insufficient evidence to advance")

    return EvidenceVerdict(
        opportunity_key=d.opportunity_key,
        score=score,
        evidence_grade=d.evidence_grade,
        state=state,
        reasons=reasons,
    )
