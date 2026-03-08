from datetime import datetime
from typing import Any

from pydantic import BaseModel

from modelforge.core.types import PredictionLog


class PredictionLogResponse(PredictionLog):
    """API response — inherits all fields from PredictionLog domain model."""
    pass


class ActualSubmission(BaseModel):
    prediction_id: str
    actual_value: Any


class ActualsBatchRequest(BaseModel):
    actuals: list[ActualSubmission]


class ActualsBatchResponse(BaseModel):
    updated: int
    not_found: list[str]


class MetricsResponse(BaseModel):
    count: int
    mae: float | None = None
    rmse: float | None = None
    mape: float | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None


class StatsResponse(BaseModel):
    total_predictions: int
    error_count: int
    error_rate: float
    avg_latency_ms: float
    p95_latency_ms: float
    period_start: datetime | None = None
    period_end: datetime | None = None
