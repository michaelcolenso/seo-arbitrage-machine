from dsf_scout.radar.evidence_validation import EvidenceDossier, score_dossier


def dossier(**overrides):
    base = dict(
        opportunity_key="permit|roofers",
        label="Permit intelligence for roofers",
        demand=4,
        pain=4,
        money=5,
        serp_weakness=2,
        buildability=5,
        evidence_grade="B",
        items=[],
    )
    base.update(overrides)
    return EvidenceDossier(**base)


def test_strong_research_does_not_masquerade_as_validation():
    verdict = score_dossier(dossier())
    assert verdict.score >= 80
    assert verdict.state == "EVIDENCE_GATHERING"


def test_payment_promotes_to_validated():
    assert score_dossier(dossier(paid_commitment=True)).state == "VALIDATED"


def test_weak_money_is_a_fatal_gate():
    verdict = score_dossier(dossier(money=1))
    assert verdict.state == "REJECTED"
    assert any("money" in reason for reason in verdict.reasons)


def test_weak_evidence_grade_is_a_fatal_gate():
    assert score_dossier(dossier(evidence_grade="D")).state == "REJECTED"
