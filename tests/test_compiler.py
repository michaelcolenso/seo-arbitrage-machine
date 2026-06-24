"""End-to-end tests for the SiteCompiler against real templates + ledger."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from dsf_compiler.builder import SiteCompiler, _slugify
from dsf_compiler.cli import compile_list
from dsf_core.config import reload_settings
from dsf_engine.models import (
    ArbitrageOpportunity,
    Evaluation,
    EvaluationVerdict,
    JobStatus,
    MonetizationPattern,
    SiteGeneration,
    TemplateType,
)
from dsf_engine.sqlite_engine import get_engine, init_db, session_scope
from sqlalchemy import inspect, text
from sqlmodel import select


def _write_dataset(directory: Path) -> Path:
    path = directory / "data.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["company", "city", "category", "violations"])
        writer.writerow(["Acme", "Austin", "chemical", 3])
        writer.writerow(["Globex", "Denver", "hvac", 1])
    return path


def _seed_evaluation(
    settings,
    *,
    verdict: EvaluationVerdict = EvaluationVerdict.APPROVED,
    template_type: TemplateType = TemplateType.DIRECTORY,
) -> int:
    init_db(settings)
    with session_scope(settings) as session:
        opp = ArbitrageOpportunity(
            niche_id="b2b_industrial_chemical_compliance",
            target_dataset_url="https://example.gov/data.csv",
        )
        session.add(opp)
        session.flush()
        evaluation = Evaluation(
            opportunity_id=opp.id,
            monetization_pattern=MonetizationPattern.LOCAL_LEAD_GENERATION,
            template_type=template_type,
            seo_route_pattern="/{city}/{category}",
            seo_high_volume_columns='["city", "category"]',
            seo_sample_routes="[]",
            confidence=0.81,
            verdict=verdict,
        )
        session.add(evaluation)
        session.flush()
        evaluation_id = evaluation.id
    assert evaluation_id is not None
    return evaluation_id


def test_compile_hydrates_directory_site(isolated_env: Path) -> None:
    settings = reload_settings()
    evaluation_id = _seed_evaluation(settings)
    dataset = _write_dataset(isolated_env)

    report = SiteCompiler(settings=settings).compile(evaluation_id, dataset)

    assert report.status == "COMPLETED"
    assert report.row_count == 2
    assert report.built is False

    build_dir = Path(report.build_path)
    assert build_dir.is_dir()
    expected = (
        f"{_slugify('b2b_industrial_chemical_compliance')}"
        f"-e{evaluation_id}-s{report.site_generation_id}"
    )
    assert build_dir.name == expected

    rows = json.loads((build_dir / "src" / "data" / "rows.json").read_text())
    meta = json.loads((build_dir / "src" / "data" / "meta.json").read_text())
    assert len(rows) == 2 and rows[0]["company"] == "Acme"
    assert meta["template_type"] == "directory"
    assert meta["seo"]["route_pattern"] == "/{city}/{category}"
    # Template markup was copied (fixed invariant present).
    assert (build_dir / "src" / "pages" / "index.astro").is_file()
    # node_modules / dist are never copied.
    assert not (build_dir / "node_modules").exists()

    with session_scope(settings) as session:
        site = session.exec(select(SiteGeneration)).one()
    assert site.status == JobStatus.COMPLETED
    assert site.evaluation_id == evaluation_id
    assert site.build_path == str(build_dir)


def test_compile_selects_calculator_template(isolated_env: Path) -> None:
    settings = reload_settings()
    evaluation_id = _seed_evaluation(settings, template_type=TemplateType.CALCULATOR)
    dataset = _write_dataset(isolated_env)

    report = SiteCompiler(settings=settings).compile(evaluation_id, dataset)

    assert report.status == "COMPLETED"
    build_dir = Path(report.build_path)
    index = (build_dir / "src" / "pages" / "index.astro").read_text()
    assert "calculator()" in index  # the calculator theme, not the directory one
    meta = json.loads((build_dir / "src" / "data" / "meta.json").read_text())
    assert meta["template_type"] == "calculator"
    assert meta["calculator"]["inputs"]  # numeric column(s) -> inputs


def test_compile_rejects_unapproved_evaluation(isolated_env: Path) -> None:
    settings = reload_settings()
    evaluation_id = _seed_evaluation(settings, verdict=EvaluationVerdict.REJECTED)
    dataset = _write_dataset(isolated_env)

    report = SiteCompiler(settings=settings).compile(evaluation_id, dataset)

    assert report.status == "REJECTED"
    assert report.site_generation_id is None
    with session_scope(settings) as session:
        assert list(session.exec(select(SiteGeneration))) == []


def test_compile_missing_dataset_reflects_and_fails(isolated_env: Path) -> None:
    settings = reload_settings()
    evaluation_id = _seed_evaluation(settings)

    report = SiteCompiler(settings=settings).compile(evaluation_id, isolated_env / "nope.csv")

    assert report.status == "AGENT_ACTION_REQUIRED"
    assert report.error_type == "FileNotFoundError"
    with session_scope(settings) as session:
        site = session.exec(select(SiteGeneration)).one()
    assert site.status == JobStatus.FAILED
    assert site.log_trace is not None


def test_compile_unknown_evaluation(isolated_env: Path) -> None:
    settings = reload_settings()
    init_db(settings)
    report = SiteCompiler(settings=settings).compile(999, isolated_env / "x.csv")
    assert report.status == "AGENT_ACTION_REQUIRED"
    assert report.error_type == "EvaluationNotFound"


def test_failed_requested_build_fails_generation(isolated_env: Path, monkeypatch) -> None:
    """--build that produces no dist/ must fail the generation, not COMPLETE it."""
    settings = reload_settings()
    evaluation_id = _seed_evaluation(settings)
    dataset = _write_dataset(isolated_env)

    # Simulate npm install / astro build failing (returns no dist/).
    monkeypatch.setattr(SiteCompiler, "_maybe_build", lambda self, build_dir: False)
    report = SiteCompiler(settings=settings).compile(evaluation_id, dataset, run_build=True)

    assert report.status == "AGENT_ACTION_REQUIRED"
    assert report.error_type == "BuildFailed"
    assert report.built is False
    with session_scope(settings) as session:
        site = session.exec(select(SiteGeneration)).one()
    assert site.status == JobStatus.FAILED


def test_compile_list_runs_migration_on_stale_ledger(isolated_env: Path) -> None:
    """`compile list` must migrate a pre-evaluation_id ledger before querying."""
    settings = reload_settings()
    engine = get_engine(settings)
    # Legacy site_generations table without the newer mapped columns.
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS site_generations"))
        connection.execute(
            text("CREATE TABLE site_generations (id INTEGER PRIMARY KEY, template_type VARCHAR)")
        )
    assert "evaluation_id" not in {
        c["name"] for c in inspect(engine).get_columns("site_generations")
    }

    # Should not raise "no such column"; it migrates, then finds no rows.
    compile_list(limit=20)

    assert "evaluation_id" in {
        c["name"] for c in inspect(engine).get_columns("site_generations")
    }


def test_recompiling_same_evaluation_uses_distinct_build_dirs(isolated_env: Path) -> None:
    """A retry of the same evaluation must not clobber the prior generation's dir."""
    settings = reload_settings()
    evaluation_id = _seed_evaluation(settings)
    dataset = _write_dataset(isolated_env)

    compiler = SiteCompiler(settings=settings)
    first = compiler.compile(evaluation_id, dataset)
    second = compiler.compile(evaluation_id, dataset)

    assert first.status == "COMPLETED" and second.status == "COMPLETED"
    assert first.site_generation_id != second.site_generation_id
    assert first.build_path != second.build_path
    assert Path(first.build_path).is_dir() and Path(second.build_path).is_dir()


def test_compile_same_niche_uses_distinct_build_dirs(isolated_env: Path) -> None:
    """Two approved evaluations sharing a niche must not overwrite each other."""
    settings = reload_settings()
    eval_a = _seed_evaluation(settings, template_type=TemplateType.DIRECTORY)
    eval_b = _seed_evaluation(settings, template_type=TemplateType.CALCULATOR)
    dataset = _write_dataset(isolated_env)

    compiler = SiteCompiler(settings=settings)
    report_a = compiler.compile(eval_a, dataset)
    report_b = compiler.compile(eval_b, dataset)

    assert report_a.build_path != report_b.build_path
    # The earlier build survives the later compile of the same niche.
    assert Path(report_a.build_path).is_dir()
    assert Path(report_b.build_path).is_dir()
    meta_a = json.loads((Path(report_a.build_path) / "src" / "data" / "meta.json").read_text())
    meta_b = json.loads((Path(report_b.build_path) / "src" / "data" / "meta.json").read_text())
    assert meta_a["template_type"] == "directory"
    assert meta_b["template_type"] == "calculator"
