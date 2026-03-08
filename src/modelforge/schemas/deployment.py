from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from modelforge.core.types import Deployment


class DeploymentCreate(BaseModel):
    name: str = Field(..., max_length=255)
    model_version_id: str


class DeploymentResponse(Deployment):
    """API response — inherits all fields from Deployment domain model."""
    pass


class PredictionRequest(BaseModel):
    input_data: list[list[float]] | dict[str, Any]


class PredictionResponse(BaseModel):
    deployment_id: str
    prediction_id: str
    output: Any
    latency_ms: float
    timestamp: datetime
