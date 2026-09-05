"""Deterministic build gate combining DataSiteForge and Codex SEO quality rules."""

from __future__ import annotations

from dataclasses import dataclass, field

from dsf_engine.models import ArbitrageOpportunity, Evaluation, TemplateType


@dataclass(frozen=True)
class QualityPolicy:
    min_evaluation_confidence: float = 0.60
    min_uniqueness_ratio: float = 0.60
    require_route_dimensions_for_directory: bool = True


@dataclass(frozen=True)
class QualityDecision:
    passed: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


def prebuild_quality_gate(
    evaluation: Evaluation,
    opportunity: ArbitrageOpportunity | None,
    policy: QualityPolicy | None = None,
) -> QualityDecision:
    """Block known low-quality builds before artifacts are created.

    Scout-produced opportunities carry ``source`` and a measured uniqueness ratio,
    so the ratio is a hard gate for them. Older/manual ledger rows may predate that
    measurement; those remain buildable for migration compatibility, while all new
    discovery paths are expected to persist the score before compilation.
    """
    policy = policy or QualityPolicy()
    reasons: list[str] = []

    if opportunity is None:
        reasons.append("evaluation has no linked opportunity")
    else:
        if (
            opportunity.source is not None
            and opportunity.uniqueness_potential_ratio < policy.min_uniqueness_ratio
        ):
            reasons.append(
                f"uniqueness {opportunity.uniqueness_potential_ratio:.2f} below "
                f"{policy.min_uniqueness_ratio:.2f}"
            )
        if not opportunity.target_dataset_url.strip():
            reasons.append("target dataset URL is missing")

    if evaluation.confidence < policy.min_evaluation_confidence:
        reasons.append(
            f"evaluation confidence {evaluation.confidence:.2f} below "
            f"{policy.min_evaluation_confidence:.2f}"
        )

    if (
        policy.require_route_dimensions_for_directory
        and evaluation.template_type == TemplateType.DIRECTORY
        and evaluation.seo_high_volume_columns.strip() in {"", "[]"}
    ):
        reasons.append("directory has no validated high-volume route dimensions")

    return QualityDecision(passed=not reasons, reasons=tuple(reasons))
