from datetime import datetime

from fastapi import APIRouter, Depends, Query

from modelforge.schemas.monitoring import (
    ActualsBatchRequest,
    ActualsBatchResponse,
    MetricsResponse,
    PredictionLogResponse,
    StatsResponse,
)
from modelforge.store import ModelStore, get_store

router = APIRouter(prefix="/deployments", tags=["Monitoring"])


@router.get("/{deployment_id}/predictions", response_model=list[PredictionLogResponse])
def list_predictions(
    deployment_id: str,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    store: ModelStore = Depends(get_store),
):
    results = store.list_predictions(
        deployment_id, start_time=start_time, end_time=end_time, skip=skip, limit=limit
    )
    return [PredictionLogResponse.model_validate(r) for r in results]


@router.post("/{deployment_id}/actuals", response_model=ActualsBatchResponse)
def submit_actuals(
    deployment_id: str,
    request: ActualsBatchRequest,
    store: ModelStore = Depends(get_store),
):
    actuals_data = [a.model_dump() for a in request.actuals]
    updated, not_found = store.submit_actuals(deployment_id, actuals_data)
    return ActualsBatchResponse(updated=updated, not_found=not_found)


@router.get("/{deployment_id}/metrics", response_model=MetricsResponse)
def get_metrics(
    deployment_id: str,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    store: ModelStore = Depends(get_store),
):
    result = store.compute_metrics(deployment_id, start_time=start_time, end_time=end_time)
    return MetricsResponse(**result)


@router.get("/{deployment_id}/stats", response_model=StatsResponse)
def get_stats(
    deployment_id: str,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    store: ModelStore = Depends(get_store),
):
    result = store.compute_stats(deployment_id, start_time=start_time, end_time=end_time)
    return StatsResponse(**result)
