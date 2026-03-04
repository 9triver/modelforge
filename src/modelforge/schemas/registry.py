from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

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


class ModelAssetResponse(BaseModel):
    id: str
    name: str
    description: str | None
    task_type: str
    algorithm_type: str
    framework: str
    owner_org: str
    status: AssetStatus
    tags: list[str] | None
    applicable_scenarios: dict[str, Any] | None
    algorithm_description: str | None
    input_schema: dict[str, Any] | None
    output_schema: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    version_count: int = 0

    model_config = {"from_attributes": True}


class StatusTransition(BaseModel):
    target_status: AssetStatus


# ── ModelVersion Schemas ──


class ModelVersionCreate(BaseModel):
    version: str = Field(..., max_length=50)
    file_format: str = Field(..., max_length=20)
    metrics: dict[str, Any] | None = None
    parent_version_id: str | None = None
    description: str | None = None


class ModelVersionResponse(BaseModel):
    id: str
    asset_id: str
    version: str
    file_path: str | None
    file_format: str
    file_size_bytes: int | None
    metrics: dict[str, Any] | None
    stage: VersionStage
    parent_version_id: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StageTransition(BaseModel):
    target_stage: VersionStage


# ── Pipeline Schemas ──


class PipelineUpdate(BaseModel):
    content: str = Field(..., description="Raw YAML text of pipeline definition")
