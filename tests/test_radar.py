"""Tests for the high-volume Radar funnel."""

from __future__ import annotations

import csv
from pathlib import Path

from dsf_core.config import reload_settings
from dsf_radar.models import KeywordCandidate, RadarDecision
from dsf_radar.runner import RadarRunner
from dsf_radar.scoring import score_candidate
from dsf_radar.store import RadarStore


def test_keyword_only_candidate_can_review_but_not_promote() -> None:
    candidate = KeywordCandidate(
        keyword="commercial building permits seattle",
        volume=6000,
        cpc=8.0,
        kd=18,
        intent="commercial",
    )
    result = score_candidate(candidate)
    assert result.scan_score >= 55
    assert result.decision == RadarDecision.REVIEW
    assert result.opportunity_score is None


def test_business_evidence_unlocks_promotion() -> None:
    candidate = KeywordCandidate(
        keyword="commercial building permits seattle",
        volume=6000,
        cpc=8.0,
        kd=18,
        intent="commercial",
        buyer="commercial contractors",
        decision_value=9,
        monetization_ease=8,
        defensibility=8,
        complexity=4,
        data_leverage=9,
        evidence_quality=8,
    )
    result = score_candidate(candidate)
    assert result.business_score is not None
    assert result.opportunity_score is not None
    assert result.decision == RadarDecision.PROMOTE


def test_high_traffic_without_business_case_never_promotes() -> None:
    candidate = KeywordCandidate(
        keyword="free celebrity wallpapers",
        volume=1_000_000,
        cpc=0.01,
        kd=2,
        intent="informational",
    )
    result = score_candidate(candidate)
    assert result.decision != RadarDecision.PROMOTE


def test_scan_persists_counts_and_top_candidates(isolated_env: Path) -> None:
    settings = reload_settings()
    csv_path = isolated_env / "keywords.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "keyword", "volume", "cpc", "kd", "intent", "buyer",
                "decision_value", "monetization_ease", "defensibility", "complexity",
                "data_leverage", "evidence_quality",
            ],
        )
        writer.writeheader()
        writer.writerow({
            "keyword": "building permit leads",
            "volume": 9000,
            "cpc": 12,
            "kd": 15,
            "intent": "commercial",
            "buyer": "contractors",
            "decision_value": 9,
            "monetization_ease": 9,
            "defensibility": 8,
            "complexity": 4,
            "data_leverage": 9,
            "evidence_quality": 9,
        })
        writer.writerow({
            "keyword": "random trivia",
            "volume": 10,
            "cpc": 0,
            "kd": 90,
            "intent": "informational",
        })

    store = RadarStore(settings)
    run_id = RadarRunner(store).scan_csv(
        csv_path, name="test", run_id="run-test", total_expected=2, batch_size=1
    )
    summary = store.get_summary(run_id)
    assert summary is not None
    assert summary.processed_count == 2
    assert summary.promoted_count == 1
    assert summary.rejected_count == 1
    assert summary.completion_ratio == 1.0
    assert store.top_candidates(run_id, limit=1)[0]["keyword"] == "building permit leads"


def test_scan_resume_does_not_duplicate_rows(isolated_env: Path) -> None:
    settings = reload_settings()
    csv_path = isolated_env / "resume.csv"
    csv_path.write_text(
        "keyword,volume,cpc,kd,intent\n"
        "permit leads,5000,7,20,commercial\n"
        "license lookup,3000,5,25,commercial\n",
        encoding="utf-8",
    )
    store = RadarStore(settings)
    runner = RadarRunner(store)
    runner.scan_csv(csv_path, name="resume", run_id="same", total_expected=2)
    runner.scan_csv(csv_path, name="resume", run_id="same", total_expected=2)
    summary = store.get_summary("same")
    assert summary is not None
    assert summary.processed_count == 2
