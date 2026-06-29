"""SQLModel tables describing the DataSiteForge orchestration state machine.

Every long-running operation in the platform — harvesting a dataset, generating
a site, deploying it, and recording its analytics — is tracked as a row whose
``status`` advances through the :class:`JobStatus` lifecycle.  On failure the row
is moved to ``FAILED`` and its ``log_trace`` captures the diagnostic, satisfying
the defensive-failure-isolation mandate.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp used for all record stamps."""
    return datetime.now(timezone.utc)


class JobStatus(str, enum.Enum):
    """Shared lifecycle states for every tracked unit of work."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TemplateType(str, enum.Enum):
    """Astro template families a dataset can be compiled into."""

    DIRECTORY = "directory"
    CALCULATOR = "calculator"


class MonetizationVector(str, enum.Enum):
    """How a discovered opportunity is intended to generate revenue."""

    LEAD_GEN = "LEAD_GEN"
    HIGH_TICKET_AFFILIATE = "HIGH_TICKET_AFFILIATE"
    PER_CLICK = "PER_CLICK"


class MonetizationPattern(str, enum.Enum):
    """The concrete monetisation pattern chosen by the Evaluator (Phase 3)."""

    LOCAL_LEAD_GENERATION = "local_lead_generation"
    CONTEXTUAL_AFFILIATION = "contextual_affiliation"
    PREMIUM_CPC = "premium_cpc"


class EvaluationVerdict(str, enum.Enum):
    """Whether an evaluated opportunity is cleared to be built into a site."""

    APPROVED = "approved"
    REJECTED = "rejected"


class ScoutJob(SQLModel, table=True):
    """A data-harvesting run seeded by a target niche."""

    __tablename__ = "scout_jobs"

    id: int | None = Field(default=None, primary_key=True)
    seed_niche: str = Field(index=True)
    source_portal: str | None = Field(default=None, description="CKAN/Socrata/data.gov origin.")
    source_url: str | None = Field(default=None)
    status: JobStatus = Field(default=JobStatus.PENDING, index=True)
    log_trace: str | None = Field(default=None)
    dataset_profile_id: int | None = Field(
        default=None, foreign_key="dataset_profiles.id", index=True
    )
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class DatasetProfile(SQLModel, table=True):
    """Structural metadata for a harvested dataset (output of schema discovery)."""

    __tablename__ = "dataset_profiles"

    id: int | None = Field(default=None, primary_key=True)
    source_dataset: str = Field(index=True, description="Logical dataset identifier.")
    source_path: str | None = Field(default=None, description="Local CSV/JSON/Parquet path.")
    row_count: int | None = Field(default=None)
    column_count: int | None = Field(default=None)
    schema_profile: str | None = Field(
        default=None, description="Agent-derived JSON schema constraint (serialised)."
    )
    duckdb_view: str | None = Field(default=None, description="Registered DuckDB view name.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class SiteGeneration(SQLModel, table=True):
    """A compilation run turning a dataset profile into an Astro build."""

    __tablename__ = "site_generations"

    id: int | None = Field(default=None, primary_key=True)
    dataset_profile_id: int | None = Field(
        default=None, foreign_key="dataset_profiles.id", index=True
    )
    evaluation_id: int | None = Field(
        default=None, foreign_key="evaluations.id", index=True
    )
    template_type: TemplateType = Field(default=TemplateType.DIRECTORY)
    status: JobStatus = Field(default=JobStatus.PENDING, index=True)
    build_path: str | None = Field(default=None)
    log_trace: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Deployment(SQLModel, table=True):
    """A Cloudflare Pages deployment record for a generated site."""

    __tablename__ = "deployments"

    id: int | None = Field(default=None, primary_key=True)
    site_generation_id: int | None = Field(
        default=None, foreign_key="site_generations.id", index=True
    )
    project_slug: str = Field(index=True)
    cloudflare_project_id: str | None = Field(default=None)
    cloudflare_deployment_id: str | None = Field(default=None)
    live_url: str | None = Field(default=None, description="The live *.pages.dev target URL.")
    status: JobStatus = Field(default=JobStatus.PENDING, index=True)
    log_trace: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ArbitrageOpportunity(SQLModel, table=True):
    """A scored arbitrage candidate produced by the Scout's miner.

    This is the durable ledger record; the Scout's in-memory scoring model lives
    in ``dsf_scout.models`` and serialises into this table.  List-valued fields
    (keywords, data sources) are stored as JSON strings for portability.
    """

    __tablename__ = "arbitrage_opportunities"

    id: int | None = Field(default=None, primary_key=True)
    scout_job_id: int | None = Field(default=None, foreign_key="scout_jobs.id", index=True)
    niche_id: str = Field(index=True)
    target_dataset_url: str
    primary_keywords: str = Field(default="[]", description="JSON-encoded list of keywords.")
    estimated_monthly_volume: int = Field(default=0)
    average_cpc: float = Field(default=0.0, description="Average cost-per-click in USD.")
    keyword_difficulty: int = Field(default=0, description="Ahrefs-style KD, 0-100.")
    data_sources_available: str = Field(default="[]", description="JSON-encoded source list.")
    monetization_vector: MonetizationVector = Field(default=MonetizationVector.LEAD_GEN)
    estimated_lead_value: float = Field(default=0.0)
    uniqueness_potential_ratio: float = Field(default=0.0)
    arbitrage_score: float = Field(default=0.0, index=True)
    source: str | None = Field(default=None, description="Candidate provider id.")
    status: JobStatus = Field(default=JobStatus.PENDING, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Evaluation(SQLModel, table=True):
    """The Evaluator's verified financial/structural verdict for an opportunity.

    Produced by ``dsf_engine.evaluator`` from an Agent Bridge financial-evaluation
    loop.  Captures the chosen monetisation pattern, the Astro template mapping,
    and the SEO routing layout.  Phase 4 reads ``APPROVED`` evaluations to build.
    """

    __tablename__ = "evaluations"

    id: int | None = Field(default=None, primary_key=True)
    opportunity_id: int | None = Field(
        default=None, foreign_key="arbitrage_opportunities.id", index=True
    )
    monetization_pattern: MonetizationPattern = Field(
        default=MonetizationPattern.LOCAL_LEAD_GENERATION
    )
    template_type: TemplateType = Field(default=TemplateType.DIRECTORY)
    seo_route_pattern: str | None = Field(default=None)
    seo_high_volume_columns: str = Field(default="[]", description="JSON-encoded column list.")
    seo_sample_routes: str = Field(default="[]", description="JSON-encoded sample routes.")
    confidence: float = Field(default=0.0)
    verdict: EvaluationVerdict = Field(default=EvaluationVerdict.REJECTED, index=True)
    rationale: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class AnalyticsLog(SQLModel, table=True):
    """A single rolled-up analytics observation for a deployed page."""

    __tablename__ = "analytics_logs"

    id: int | None = Field(default=None, primary_key=True)
    deployment_id: int | None = Field(default=None, foreign_key="deployments.id", index=True)
    page_path: str = Field(index=True)
    impressions: int = Field(default=0)
    clicks: int = Field(default=0)
    revenue_cents: int = Field(default=0, description="Attributed revenue in USD cents.")
    captured_at: datetime = Field(default_factory=utcnow, index=True)


class Optimization(SQLModel, table=True):
    """A reinforcement action taken on an underperforming page (Phase 6/7).

    The optimizer flags pages with high impressions but weak click-through,
    requests a rewrite from the Agent Bridge, applies it to the hydration layer,
    and (optionally) silently redeploys.  Each attempt is recorded here.
    """

    __tablename__ = "optimizations"

    id: int | None = Field(default=None, primary_key=True)
    deployment_id: int | None = Field(default=None, foreign_key="deployments.id", index=True)
    page_path: str = Field(index=True)
    impressions: int = Field(default=0)
    clicks: int = Field(default=0)
    ctr: float = Field(default=0.0, description="Click-through ratio at flag time.")
    action: str = Field(default="meta_rewrite", description="Reinforcement action applied.")
    detail: str | None = Field(default=None)
    redeployed: bool = Field(default=False)
    status: JobStatus = Field(default=JobStatus.PENDING, index=True)
    created_at: datetime = Field(default_factory=utcnow)


class Job(SQLModel, table=True):
    """A background control-plane job (Phase 8 API worker), persisted for durability.

    The API submits long-running lifecycle actions to a thread-pool worker and
    returns this job's id.  Persisting it to the ledger means job state and
    history survive a process restart, and orphaned in-flight jobs can be
    recovered (queued ones re-run; running ones flagged interrupted).

    ``status`` uses the worker vocabulary (``queued`` / ``running`` /
    ``succeeded`` / ``failed``); ``params`` and ``result`` are JSON strings.
    """

    __tablename__ = "jobs"

    id: str = Field(primary_key=True)
    kind: str = Field(index=True)
    status: str = Field(default="queued", index=True)
    params: str = Field(default="{}", description="JSON-encoded request parameters.")
    result: str | None = Field(default=None, description="JSON-encoded handler result.")
    error: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    started_at: datetime | None = Field(default=None)
    finished_at: datetime | None = Field(default=None)


# Convenience collection used by status reporting / verification helpers.
ALL_TABLES: tuple[type[SQLModel], ...] = (
    ScoutJob,
    DatasetProfile,
    SiteGeneration,
    Deployment,
    ArbitrageOpportunity,
    Evaluation,
    AnalyticsLog,
    Optimization,
    Job,
)
