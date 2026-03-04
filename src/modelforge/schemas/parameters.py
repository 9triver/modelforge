from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ParameterTemplateCreate(BaseModel):
    name: str = Field(..., max_length=255)
    model_asset_id: str | None = None
    algorithm_type: str | None = Field(None, max_length=100)
    scenario_tags: dict[str, Any] | None = None
    parameters: dict[str, Any]
    performance_notes: str | None = None


class ParameterTemplateUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    model_asset_id: str | None = None
    algorithm_type: str | None = Field(None, max_length=100)
    scenario_tags: dict[str, Any] | None = None
    parameters: dict[str, Any] | None = None
    performance_notes: str | None = None


class ParameterTemplateResponse(BaseModel):
    id: str
    name: str
    model_asset_id: str | None
    algorithm_type: str | None
    scenario_tags: dict[str, Any] | None
    parameters: dict[str, Any]
    performance_notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
