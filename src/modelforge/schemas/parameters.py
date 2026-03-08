from typing import Any

from pydantic import BaseModel, Field

from modelforge.core.types import ParameterTemplate


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


class ParameterTemplateResponse(ParameterTemplate):
    """API response — inherits all fields from ParameterTemplate domain model."""
    pass


# ── Parameter Comparison ──


class ParameterCompareRequest(BaseModel):
    left_type: str  # "template"
    left_id: str
    right_type: str  # "template"
    right_id: str


class ParamDiffEntry(BaseModel):
    key: str
    left_value: Any = None
    right_value: Any = None
    changed: bool


class ParameterCompareResponse(BaseModel):
    left_label: str
    right_label: str
    diff: list[ParamDiffEntry]
    left_only: list[str]
    right_only: list[str]
