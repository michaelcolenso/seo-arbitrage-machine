"""Request/response models for the API gateway."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScoutRunRequest(BaseModel):
    niche: str = Field(min_length=1)
    live: bool = False
    portal: str = "https://catalog.data.gov"
    rows: int = Field(default=20, ge=1, le=100)


class EvaluateRunRequest(BaseModel):
    limit: int | None = Field(default=None, ge=1)
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class CompileRunRequest(BaseModel):
    evaluation_id: int
    dataset: str = Field(min_length=1, description="Path to the source dataset file.")
    build: bool = False


class DeployRunRequest(BaseModel):
    site_generation_id: int
    build: bool = False
    dry_run: bool | None = None


class OptimizeRunRequest(BaseModel):
    deployment_id: int | None = None
    reinforce: bool = True
    redeploy: bool = False
    min_impressions: int = Field(default=300, ge=0)
    max_ctr: float = Field(default=0.02, ge=0.0, le=1.0)


class JobAccepted(BaseModel):
    job_id: str
    kind: str
    status: str


class LeadCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=320)
    company: str | None = Field(default=None, max_length=200)
    niche_id: str | None = Field(default=None, max_length=200)
    source_url: str | None = Field(default=None, max_length=2000)
    website: str | None = Field(default=None, max_length=200, description="Spam honeypot.")
