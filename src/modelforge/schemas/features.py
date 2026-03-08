from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from modelforge.core.types import FeatureDefinition

# ── FeatureDefinition ──


class FeatureDefinitionCreate(BaseModel):
    name: str = Field(..., max_length=255)
    data_type: str = Field(..., max_length=50)
    description: str | None = None
    unit: str | None = Field(None, max_length=50)
    computation_logic: str | None = None
    value_range: dict[str, Any] | None = None


class FeatureDefinitionUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    data_type: str | None = Field(None, max_length=50)
    description: str | None = None
    unit: str | None = Field(None, max_length=50)
    computation_logic: str | None = None
    value_range: dict[str, Any] | None = None


class FeatureDefinitionResponse(FeatureDefinition):
    """API response — inherits all fields from FeatureDefinition domain model."""
    pass


# ── FeatureGroup ──


class FeatureGroupCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: str | None = None
    scenario_tags: dict[str, Any] | None = None
    feature_ids: list[str] = Field(default_factory=list)


class FeatureGroupUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    description: str | None = None
    scenario_tags: dict[str, Any] | None = None
    feature_ids: list[str] | None = None


class FeatureGroupResponse(BaseModel):
    """Standalone response — uses resolved FeatureDefinitionResponse list
    instead of raw feature_ids, so it does not inherit from FeatureGroup."""

    id: str
    name: str
    description: str | None
    scenario_tags: dict[str, Any] | None
    features: list[FeatureDefinitionResponse]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
