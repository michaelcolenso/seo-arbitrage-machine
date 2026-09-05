from dsf_compiler.quality import prebuild_quality_gate
from dsf_engine.models import ArbitrageOpportunity, Evaluation, TemplateType


def _evaluation(**overrides) -> Evaluation:
    values = {
        "template_type": TemplateType.DIRECTORY,
        "seo_high_volume_columns": '["city"]',
        "confidence": 0.8,
    }
    values.update(overrides)
    return Evaluation(**values)


def _opportunity(**overrides) -> ArbitrageOpportunity:
    values = {
        "niche_id": "permit-leads",
        "target_dataset_url": "https://example.gov/permits.csv",
        "source": "ckan",
        "uniqueness_potential_ratio": 0.8,
    }
    values.update(overrides)
    return ArbitrageOpportunity(**values)


def test_scored_opportunity_passes_gate() -> None:
    assert prebuild_quality_gate(_evaluation(), _opportunity()).passed is True


def test_low_uniqueness_scored_opportunity_is_blocked() -> None:
    result = prebuild_quality_gate(
        _evaluation(), _opportunity(uniqueness_potential_ratio=0.2)
    )
    assert result.passed is False
    assert any("uniqueness" in reason for reason in result.reasons)


def test_directory_without_route_dimensions_is_blocked() -> None:
    result = prebuild_quality_gate(
        _evaluation(seo_high_volume_columns="[]"), _opportunity()
    )
    assert result.passed is False
    assert any("route dimensions" in reason for reason in result.reasons)


def test_legacy_unscored_row_remains_migratable() -> None:
    legacy = _opportunity(source=None, uniqueness_potential_ratio=0.0)
    assert prebuild_quality_gate(_evaluation(), legacy).passed is True
