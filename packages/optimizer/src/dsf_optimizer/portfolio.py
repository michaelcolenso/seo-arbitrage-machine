"""Evidence-based portfolio decisions inspired by the Agentic Arbitrage Mortician.

The important invariant is safety of evidence: a site is never culled because metrics
are missing. Thresholds are policy inputs, not universal constants.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class PortfolioAction(str, enum.Enum):
    METRICS_REQUIRED = "METRICS_REQUIRED"
    HOLD = "HOLD"
    ACCELERATE = "ACCELERATE"
    SCALE = "SCALE"
    CULL = "CULL"


@dataclass(frozen=True)
class PortfolioPolicy:
    evaluation_days: int = 90
    min_daily_organic_users: float = 100.0
    min_total_revenue_usd: float = 10.0
    promising_daily_users: float = 200.0
    winner_daily_users: float = 500.0
    max_negative_growth: float = -0.30
    min_metric_days: int = 7
    require_verified_metrics: bool = True


@dataclass(frozen=True)
class PortfolioEvidence:
    site_id: str
    days_active: int
    metric_days: int
    avg_daily_organic_users: float
    growth_rate: float | None = None
    total_revenue_usd: float | None = None
    conversions: int | None = None
    verified_metrics: bool = False


@dataclass(frozen=True)
class PortfolioDecision:
    site_id: str
    action: PortfolioAction
    reasons: tuple[str, ...] = field(default_factory=tuple)


def evaluate_portfolio_item(
    evidence: PortfolioEvidence,
    policy: PortfolioPolicy | None = None,
) -> PortfolioDecision:
    policy = policy or PortfolioPolicy()

    if policy.require_verified_metrics and not evidence.verified_metrics:
        return PortfolioDecision(
            evidence.site_id,
            PortfolioAction.METRICS_REQUIRED,
            ("verified production metrics are unavailable",),
        )
    if evidence.metric_days < policy.min_metric_days:
        return PortfolioDecision(
            evidence.site_id,
            PortfolioAction.METRICS_REQUIRED,
            (f"only {evidence.metric_days} metric days; need {policy.min_metric_days}",),
        )

    # Strong traction overrides early cull signals. Revenue/conversion evidence is
    # intentionally allowed to elevate a lower-traffic B2B product.
    meaningful_revenue = (
        evidence.total_revenue_usd is not None
        and evidence.total_revenue_usd >= policy.min_total_revenue_usd * 10
    )
    meaningful_conversions = evidence.conversions is not None and evidence.conversions >= 5
    if evidence.avg_daily_organic_users >= policy.winner_daily_users or meaningful_revenue:
        return PortfolioDecision(
            evidence.site_id,
            PortfolioAction.SCALE,
            ("winner threshold reached",),
        )
    if (
        evidence.avg_daily_organic_users >= policy.promising_daily_users
        or meaningful_conversions
    ):
        return PortfolioDecision(
            evidence.site_id,
            PortfolioAction.ACCELERATE,
            ("promising traction or conversions",),
        )

    if evidence.days_active < policy.evaluation_days:
        return PortfolioDecision(
            evidence.site_id,
            PortfolioAction.HOLD,
            ("experiment has not reached its evaluation window",),
        )

    cull_reasons: list[str] = []
    if evidence.avg_daily_organic_users < policy.min_daily_organic_users:
        cull_reasons.append(
            f"organic users {evidence.avg_daily_organic_users:.1f}/day below "
            f"{policy.min_daily_organic_users:.1f}"
        )
    if (
        evidence.total_revenue_usd is not None
        and evidence.total_revenue_usd < policy.min_total_revenue_usd
    ):
        cull_reasons.append(
            f"revenue ${evidence.total_revenue_usd:.2f} below "
            f"${policy.min_total_revenue_usd:.2f}"
        )
    if evidence.growth_rate is not None and evidence.growth_rate < policy.max_negative_growth:
        cull_reasons.append(f"traffic declining {evidence.growth_rate:.1%}")

    # Traffic alone is not enough to kill a product if the caller has not supplied
    # revenue or conversion evidence. This prevents an SEO-only metric from silently
    # becoming a business decision.
    business_evidence_present = (
        evidence.total_revenue_usd is not None or evidence.conversions is not None
    )
    if cull_reasons and business_evidence_present:
        return PortfolioDecision(evidence.site_id, PortfolioAction.CULL, tuple(cull_reasons))

    return PortfolioDecision(
        evidence.site_id,
        PortfolioAction.HOLD,
        ("insufficient business evidence for a destructive portfolio decision",),
    )
