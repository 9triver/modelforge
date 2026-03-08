from typing import Any

from pydantic import BaseModel, Field

from modelforge.core.types import ModelAsset, ModelVersion
from modelforge.enums import AssetStatus, VersionStage

# ── ModelAsset Schemas ──


class ModelAssetCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: str | None = None
    task_type: str = Field(..., max_length=100)
    algorithm_type: str = Field(..., max_length=100)
    framework: str = Field(..., max_length=50)
    owner_org: str = Field(..., max_length=255)
    tags: list[str] | None = None
    applicable_scenarios: dict[str, Any] | None = None
    algorithm_description: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None


class ModelAssetUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    description: str | None = None
    task_type: str | None = Field(None, max_length=100)
    algorithm_type: str | None = Field(None, max_length=100)
    framework: str | None = Field(None, max_length=50)
    owner_org: str | None = Field(None, max_length=255)
    tags: list[str] | None = None
    applicable_scenarios: dict[str, Any] | None = None
    algorithm_description: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None


class ModelAssetResponse(ModelAsset):
    """API response — inherits all fields from ModelAsset domain model."""
    pass


class StatusTransition(BaseModel):
    target_status: AssetStatus


# ── ModelVersion Schemas ──


class ModelVersionCreate(BaseModel):
    version: str = Field(..., max_length=50)
    file_format: str = Field(..., max_length=20)
    metrics: dict[str, Any] | None = None
    parent_version_id: str | None = None
    description: str | None = None


class DraftVersionRequest(BaseModel):
    base_version: str = Field(
        ..., description="Version to copy from, e.g. 'v1.0.0'"
    )
    description: str | None = None


class ModelVersionResponse(ModelVersion):
    """API response — inherits all fields from ModelVersion domain model."""
    pass


class StageTransition(BaseModel):
    target_stage: VersionStage


# ── Pipeline Schemas ──


class PipelineUpdate(BaseModel):
    content: str = Field(
        ..., description="Raw YAML text of pipeline definition"
    )


class PipelineRunRequest(BaseModel):
    base_version: str = Field(
        ..., description="Version to use as base, e.g. 'v1.0.0'"
    )
    overrides: dict[str, str] | None = Field(
        None, description="Optional overrides: dataset, "
        "feature_config, params",
    )
    draft_version: str | None = Field(
        None, description="If set, train this draft version "
        "in-place instead of copying base",
    )


class ForkRequest(BaseModel):
    source_version_id: str = Field(
        ..., description="UUID of the version to fork"
    )
    new_name: str = Field(
        ..., max_length=255, description="Name for the new model"
    )
    new_owner_org: str = Field(
        ..., max_length=255, description="Owner organization"
    )
    description: str | None = None


# ── Artifact Schemas ──


class ArtifactTextSave(BaseModel):
    content: str = Field(..., description="Text content of the file")
