from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from modelforge.enums import DeploymentStatus
from modelforge.schemas.deployment import (
    DeploymentCreate,
    DeploymentResponse,
    PredictionRequest,
    PredictionResponse,
)
from modelforge.services.inference import inference_manager
from modelforge.store import ModelStore, get_store

router = APIRouter(prefix="/deployments", tags=["Deployment"])


@router.post("", response_model=DeploymentResponse, status_code=201)
def create_deployment(data: DeploymentCreate, store: ModelStore = Depends(get_store)):
    result = store.create_deployment(data.model_dump())
    return DeploymentResponse.model_validate(result)


@router.get("", response_model=list[DeploymentResponse])
def list_deployments(
    status: DeploymentStatus | None = None,
    model_version_id: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    store: ModelStore = Depends(get_store),
):
    results = store.list_deployments(
        status=status, model_version_id=model_version_id, skip=skip, limit=limit
    )
    return [DeploymentResponse.model_validate(d) for d in results]


@router.get("/{deployment_id}", response_model=DeploymentResponse)
def get_deployment(deployment_id: str, store: ModelStore = Depends(get_store)):
    result = store.get_deployment(deployment_id)
    return DeploymentResponse.model_validate(result)


@router.post("/{deployment_id}/start", response_model=DeploymentResponse)
def start_deployment(deployment_id: str, store: ModelStore = Depends(get_store)):
    result = store.start_deployment(deployment_id, inference_manager)
    return DeploymentResponse.model_validate(result)


@router.post("/{deployment_id}/stop", response_model=DeploymentResponse)
def stop_deployment(deployment_id: str, store: ModelStore = Depends(get_store)):
    result = store.stop_deployment(deployment_id, inference_manager)
    return DeploymentResponse.model_validate(result)


@router.delete("/{deployment_id}", status_code=204)
def delete_deployment(deployment_id: str, store: ModelStore = Depends(get_store)):
    store.delete_deployment(deployment_id, inference_manager)


@router.post("/{deployment_id}/predict", response_model=PredictionResponse)
def predict(
    deployment_id: str,
    request: PredictionRequest,
    store: ModelStore = Depends(get_store),
):
    result, latency_ms = store.predict(deployment_id, request.input_data, inference_manager)
    log = store.log_prediction(deployment_id, request.input_data, result, latency_ms)

    return PredictionResponse(
        deployment_id=deployment_id,
        prediction_id=log["id"],
        output=result,
        latency_ms=round(latency_ms, 3),
        timestamp=datetime.now(timezone.utc),
    )


predict_router = APIRouter(prefix="/predict", tags=["Predict"])


@predict_router.post("/{deploy_name}", response_model=PredictionResponse)
def predict_by_name(
    deploy_name: str,
    request: PredictionRequest,
    store: ModelStore = Depends(get_store),
):
    """Predict using deployment name (user-friendly endpoint)."""
    deployment = store.get_deployment_by_name(deploy_name)
    deployment_id = deployment["id"]
    result, latency_ms = store.predict(deployment_id, request.input_data, inference_manager)
    log = store.log_prediction(deployment_id, request.input_data, result, latency_ms)

    return PredictionResponse(
        deployment_id=deployment_id,
        prediction_id=log["id"],
        output=result,
        latency_ms=round(latency_ms, 3),
        timestamp=datetime.now(timezone.utc),
    )
