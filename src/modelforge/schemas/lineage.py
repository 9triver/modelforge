"""Pydantic schemas for lineage/provenance API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VersionProvenance(BaseModel):
    """Provenance record for a single version."""

    version_id: str
    version: str | None = None
    model_id: str
    stage: str | None = None
    parent_version_id: str | None = None
    source_model_id: str | None = None
    created_at: str | None = None
    metrics: dict | None = None
    artifacts: dict[str, list[str]] = Field(
        default_factory=dict,
    )
    training_run: dict | None = None


class UpstreamLineage(BaseModel):
    """Upstream lineage chain for a version."""

    version_id: str
    chain: list[VersionProvenance] = Field(
        default_factory=list,
    )


class ArtifactCategoryDiff(BaseModel):
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    unchanged: list[str] = Field(default_factory=list)


class MetricDiff(BaseModel):
    metric: str
    version_a: float | None = None
    version_b: float | None = None
    delta: float | None = None


class VersionDiff(BaseModel):
    """Comparison of two versions' provenance."""

    version_a: dict
    version_b: dict
    artifact_diff: dict[str, ArtifactCategoryDiff] = Field(
        default_factory=dict,
    )
    metric_diff: list[MetricDiff] = Field(
        default_factory=list,
    )
    overrides_a: dict | None = None
    overrides_b: dict | None = None
