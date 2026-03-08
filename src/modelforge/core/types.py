"""Core domain models — the canonical shape of every entity in the platform.

These Pydantic models define the persisted structure of each entity.
The MetadataStore layer currently returns plain dicts that conform to
these shapes; the API Response schemas inherit from these models to
avoid field duplication.

Usage::

    from modelforge.core.types import ModelAsset, ModelVersion, Deployment
    asset = ModelAsset.model_validate(store.get_model(model_id))
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from modelforge.enums import AssetStatus, DeploymentStatus, VersionStage


# ── ModelAsset ──


class ModelAsset(BaseModel):
    """A registered model asset (top-level entity)."""

    id: str
    name: str
    slug: str = ""
    description: str | None = None
    task_type: str
    algorithm_type: str
    framework: str
    owner_org: str
    status: AssetStatus = AssetStatus.DRAFT
    tags: list[str] | None = None
    applicable_scenarios: dict[str, Any] | None = None
    algorithm_description: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    version_count: int = 0

    model_config = {"from_attributes": True}


# ── Artifact Location ──


class ArtifactLocation(BaseModel):
    """Describes where a single artifact category is stored.

    When backend="local", uri is a relative path under the version directory.
    For remote backends (s3, oss, git, dvc, ...), uri is a backend-specific
    resource locator.
    """

    backend: str = "local"          # local, s3, oss, git, dvc, ...
    uri: str = ""                   # 后端特定的资源定位符
    size_bytes: int | None = None
    checksum: str | None = None     # 如 "sha256:abc123..."
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── ModelVersion ──


class ModelVersion(BaseModel):
    """A specific version of a model asset, with weights and artifacts."""

    id: str
    asset_id: str = ""
    version: str
    description: str | None = None
    file_format: str = "joblib"
    file_path: str | None = None
    file_size_bytes: int | None = 0
    metrics: dict[str, Any] | None = None
    stage: VersionStage = VersionStage.DEVELOPMENT
    parent_version_id: str | None = None   # retrain: 同模型上一版本; fork: 来源模型的版本
    source_model_id: str | None = None    # 非空表示 fork，指向来源 ModelAsset
    artifacts: dict[str, ArtifactLocation] | None = None  # 制品清单
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Deployment ──


class Deployment(BaseModel):
    """A deployed model version serving predictions."""

    id: str
    name: str
    model_version_id: str
    model_id: str = ""
    model_slug: str = ""
    version_string: str = ""
    file_format: str = ""
    status: DeploymentStatus = DeploymentStatus.PENDING
    endpoint_config: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── PipelineRun ──


class PipelineRun(BaseModel):
    """A single execution of a training pipeline."""

    id: str
    model_id: str
    status: str = "pending"  # pending, running, success, failed, cancelled
    base_version: str = ""
    target_version: str | None = None
    pipeline_snapshot: dict[str, Any] | None = None
    overrides: dict[str, Any] | None = None
    log: str = ""
    metrics: dict[str, Any] | None = None
    result_version_id: str | None = None
    result_version: str | None = None
    error: str | None = None
    started_at: datetime
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── PredictionLog ──


class PredictionLog(BaseModel):
    """A single prediction record for monitoring."""

    id: str
    deployment_id: str
    input_data: Any = None
    output_data: Any = None
    actual_value: Any | None = None
    latency_ms: float = 0.0
    error: str | None = None
    created_at: datetime
    actual_submitted_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── FeatureDefinition ──


class FeatureDefinition(BaseModel):
    """A global feature definition in the feature catalog."""

    id: str
    name: str
    data_type: str
    description: str | None = None
    unit: str | None = None
    computation_logic: str | None = None
    value_range: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── FeatureGroup ──


class FeatureGroup(BaseModel):
    """A named group of features, optionally tagged by scenario."""

    id: str
    name: str
    description: str | None = None
    scenario_tags: dict[str, Any] | None = None
    feature_ids: list[str] = Field(default_factory=list)
    features: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── ParameterTemplate ──


class ParameterTemplate(BaseModel):
    """A recommended hyperparameter configuration."""

    id: str
    name: str
    model_asset_id: str | None = None
    algorithm_type: str | None = None
    scenario_tags: dict[str, Any] | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    performance_notes: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
