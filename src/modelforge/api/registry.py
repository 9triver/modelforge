import json

import yaml
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

from modelforge.enums import AssetStatus
from modelforge.schemas.registry import (
    ModelAssetCreate,
    ModelAssetResponse,
    ModelAssetUpdate,
    ModelVersionCreate,
    ModelVersionResponse,
    PipelineUpdate,
    StageTransition,
    StatusTransition,
)
from modelforge.store import ModelStore, get_store

router = APIRouter(prefix="/models", tags=["Model Registry"])


# ── ModelAsset endpoints ──


@router.post("", response_model=ModelAssetResponse, status_code=201)
def create_model(data: ModelAssetCreate, store: ModelStore = Depends(get_store)):
    result = store.create_model(data.model_dump())
    return ModelAssetResponse.model_validate(result)


@router.get("", response_model=list[ModelAssetResponse])
def list_models(
    task_type: str | None = None,
    algorithm_type: str | None = None,
    owner_org: str | None = None,
    framework: str | None = None,
    status: AssetStatus | None = None,
    q: str | None = Query(None, description="Search in name and description"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    store: ModelStore = Depends(get_store),
):
    results = store.list_models(
        task_type=task_type,
        algorithm_type=algorithm_type,
        owner_org=owner_org,
        framework=framework,
        status=status,
        q=q,
        skip=skip,
        limit=limit,
    )
    return [ModelAssetResponse.model_validate(m) for m in results]


@router.get("/{model_id}", response_model=ModelAssetResponse)
def get_model(model_id: str, store: ModelStore = Depends(get_store)):
    result = store.get_model(model_id)
    return ModelAssetResponse.model_validate(result)


@router.put("/{model_id}", response_model=ModelAssetResponse)
def update_model(
    model_id: str, data: ModelAssetUpdate, store: ModelStore = Depends(get_store)
):
    result = store.update_model(model_id, data.model_dump(exclude_unset=True))
    return ModelAssetResponse.model_validate(result)


@router.patch("/{model_id}/status", response_model=ModelAssetResponse)
def transition_model_status(
    model_id: str, body: StatusTransition, store: ModelStore = Depends(get_store)
):
    result = store.transition_status(model_id, body.target_status)
    return ModelAssetResponse.model_validate(result)


@router.delete("/{model_id}", status_code=204)
def delete_model(model_id: str, store: ModelStore = Depends(get_store)):
    store.delete_model(model_id)


# ── ModelVersion endpoints ──


@router.post("/{model_id}/versions", response_model=ModelVersionResponse, status_code=201)
def create_version(
    model_id: str,
    file: UploadFile = File(...),
    version: str = Form(...),
    file_format: str = Form(...),
    metrics: str | None = Form(None),
    parent_version_id: str | None = Form(None),
    description: str | None = Form(None),
    store: ModelStore = Depends(get_store),
):
    data = ModelVersionCreate(
        version=version,
        file_format=file_format,
        metrics=json.loads(metrics) if metrics else None,
        parent_version_id=parent_version_id,
        description=description,
    )
    result = store.create_version(model_id, data.model_dump(), file)
    return ModelVersionResponse.model_validate(result)


@router.get("/{model_id}/versions", response_model=list[ModelVersionResponse])
def list_versions(model_id: str, store: ModelStore = Depends(get_store)):
    versions = store.list_versions(model_id)
    return [ModelVersionResponse.model_validate(v) for v in versions]


@router.get("/{model_id}/versions/{version_id}", response_model=ModelVersionResponse)
def get_version(model_id: str, version_id: str, store: ModelStore = Depends(get_store)):
    result = store.get_version(model_id, version_id)
    return ModelVersionResponse.model_validate(result)


@router.patch("/{model_id}/versions/{version_id}/stage", response_model=ModelVersionResponse)
def transition_version_stage(
    model_id: str,
    version_id: str,
    body: StageTransition,
    store: ModelStore = Depends(get_store),
):
    result = store.transition_stage(model_id, version_id, body.target_stage)
    return ModelVersionResponse.model_validate(result)


@router.get("/{model_id}/versions/{version_id}/download")
def download_version(
    model_id: str, version_id: str, store: ModelStore = Depends(get_store)
):
    file_path = store.get_version_file_path(model_id, version_id)
    return FileResponse(file_path)


# ── Version Artifacts ──


@router.get("/{model_id}/versions/{version_id}/artifacts/{category}")
def list_artifacts(
    model_id: str,
    version_id: str,
    category: str,
    store: ModelStore = Depends(get_store),
):
    return store.list_version_artifacts(model_id, version_id, category)


@router.get("/{model_id}/versions/{version_id}/artifacts/{category}/{filename}")
def read_artifact(
    model_id: str,
    version_id: str,
    category: str,
    filename: str,
    store: ModelStore = Depends(get_store),
):
    content = store.read_version_artifact(model_id, version_id, category, filename)
    return PlainTextResponse(content)


@router.get("/{model_id}/versions/{version_id}/datasets/{filename}/preview")
def preview_dataset(
    model_id: str,
    version_id: str,
    filename: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    store: ModelStore = Depends(get_store),
):
    return store.preview_dataset(model_id, version_id, filename, offset, limit)


# ── Pipeline Definition ──


@router.get("/{model_id}/pipeline")
def get_pipeline(
    model_id: str, store: ModelStore = Depends(get_store)
):
    data = store.get_pipeline(model_id)
    if data is None:
        return {"exists": False, "content": "", "data": None}
    content = yaml.dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    return {"exists": True, "content": content, "data": data}


@router.put("/{model_id}/pipeline")
def save_pipeline(
    model_id: str,
    body: PipelineUpdate,
    store: ModelStore = Depends(get_store),
):
    data = store.save_pipeline(model_id, body.content)
    return {"exists": True, "content": body.content, "data": data}


@router.delete("/{model_id}/pipeline", status_code=204)
def delete_pipeline(
    model_id: str, store: ModelStore = Depends(get_store)
):
    store.delete_pipeline(model_id)
