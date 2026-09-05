from dsf_optimizer.portfolio import (
    PortfolioAction,
    PortfolioEvidence,
    PortfolioPolicy,
    evaluate_portfolio_item,
)


def test_missing_real_metrics_never_culls() -> None:
    evidence = PortfolioEvidence(
        site_id="site-1",
        days_active=120,
        metric_days=90,
        avg_daily_organic_users=0,
        total_revenue_usd=0,
        verified_metrics=False,
    )
    assert evaluate_portfolio_item(evidence).action == PortfolioAction.METRICS_REQUIRED


def test_low_traffic_alone_is_not_a_destructive_signal() -> None:
    evidence = PortfolioEvidence(
        site_id="site-2",
        days_active=120,
        metric_days=30,
        avg_daily_organic_users=20,
        verified_metrics=True,
    )
    assert evaluate_portfolio_item(evidence).action == PortfolioAction.HOLD


def test_mature_failed_experiment_can_be_culled_with_business_evidence() -> None:
    evidence = PortfolioEvidence(
        site_id="site-3",
        days_active=120,
        metric_days=30,
        avg_daily_organic_users=20,
        growth_rate=-0.5,
        total_revenue_usd=0,
        conversions=0,
        verified_metrics=True,
    )
    decision = evaluate_portfolio_item(evidence)
    assert decision.action == PortfolioAction.CULL
    assert len(decision.reasons) >= 2


def test_revenue_can_identify_b2b_winner_without_huge_traffic() -> None:
    policy = PortfolioPolicy(min_total_revenue_usd=10)
    evidence = PortfolioEvidence(
        site_id="site-4",
        days_active=45,
        metric_days=30,
        avg_daily_organic_users=30,
        total_revenue_usd=250,
        conversions=3,
        verified_metrics=True,
    )
    assert evaluate_portfolio_item(evidence, policy).action == PortfolioAction.SCALE
