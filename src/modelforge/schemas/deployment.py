from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from modelforge.enums import DeploymentStatus


class DeploymentCreate(BaseModel):
    name: str = Field(..., max_length=255)
    model_version_id: str


class DeploymentResponse(BaseModel):
    id: str
    name: str
    model_version_id: str
    status: DeploymentStatus
    endpoint_config: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PredictionRequest(BaseModel):
    input_data: list[list[float]] | dict[str, Any]


class PredictionResponse(BaseModel):
    deployment_id: str
    prediction_id: str
    output: Any
    latency_ms: float
    timestamp: datetime
