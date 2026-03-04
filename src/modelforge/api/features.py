from fastapi import APIRouter, Depends, Query

from modelforge.schemas.features import (
    FeatureDefinitionCreate,
    FeatureDefinitionResponse,
    FeatureDefinitionUpdate,
    FeatureGroupCreate,
    FeatureGroupResponse,
    FeatureGroupUpdate,
)
from modelforge.store import ModelStore, get_store

router = APIRouter(tags=["Feature Management"])

# ── FeatureDefinition ──


@router.post("/features/definitions", response_model=FeatureDefinitionResponse, status_code=201)
def create_definition(data: FeatureDefinitionCreate, store: ModelStore = Depends(get_store)):
    result = store.create_feature_definition(data.model_dump())
    return FeatureDefinitionResponse.model_validate(result)


@router.get("/features/definitions", response_model=list[FeatureDefinitionResponse])
def list_definitions(
    data_type: str | None = None,
    q: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    store: ModelStore = Depends(get_store),
):
    results = store.list_feature_definitions(data_type=data_type, q=q, skip=skip, limit=limit)
    return [FeatureDefinitionResponse.model_validate(f) for f in results]


@router.get("/features/definitions/{feature_id}", response_model=FeatureDefinitionResponse)
def get_definition(feature_id: str, store: ModelStore = Depends(get_store)):
    result = store.get_feature_definition(feature_id)
    return FeatureDefinitionResponse.model_validate(result)


@router.put("/features/definitions/{feature_id}", response_model=FeatureDefinitionResponse)
def update_definition(
    feature_id: str, data: FeatureDefinitionUpdate, store: ModelStore = Depends(get_store)
):
    result = store.update_feature_definition(feature_id, data.model_dump(exclude_unset=True))
    return FeatureDefinitionResponse.model_validate(result)


@router.delete("/features/definitions/{feature_id}", status_code=204)
def delete_definition(feature_id: str, store: ModelStore = Depends(get_store)):
    store.delete_feature_definition(feature_id)


# ── FeatureGroup ──


@router.post("/features/groups", response_model=FeatureGroupResponse, status_code=201)
def create_group(data: FeatureGroupCreate, store: ModelStore = Depends(get_store)):
    result = store.create_feature_group(data.model_dump())
    return FeatureGroupResponse.model_validate(result)


@router.get("/features/groups", response_model=list[FeatureGroupResponse])
def list_groups(
    q: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    store: ModelStore = Depends(get_store),
):
    results = store.list_feature_groups(q=q, skip=skip, limit=limit)
    return [FeatureGroupResponse.model_validate(g) for g in results]


@router.get("/features/groups/{group_id}", response_model=FeatureGroupResponse)
def get_group(group_id: str, store: ModelStore = Depends(get_store)):
    result = store.get_feature_group(group_id)
    return FeatureGroupResponse.model_validate(result)


@router.put("/features/groups/{group_id}", response_model=FeatureGroupResponse)
def update_group(
    group_id: str, data: FeatureGroupUpdate, store: ModelStore = Depends(get_store)
):
    result = store.update_feature_group(group_id, data.model_dump(exclude_unset=True))
    return FeatureGroupResponse.model_validate(result)


@router.delete("/features/groups/{group_id}", status_code=204)
def delete_group(group_id: str, store: ModelStore = Depends(get_store)):
    store.delete_feature_group(group_id)


# ── Model ↔ FeatureGroup association ──


@router.post("/models/{model_id}/feature-groups/{group_id}", status_code=204)
def associate_model_group(
    model_id: str, group_id: str, store: ModelStore = Depends(get_store)
):
    store.associate_model_group(model_id, group_id)


@router.delete("/models/{model_id}/feature-groups/{group_id}", status_code=204)
def disassociate_model_group(
    model_id: str, group_id: str, store: ModelStore = Depends(get_store)
):
    store.disassociate_model_group(model_id, group_id)


@router.get("/models/{model_id}/feature-groups", response_model=list[FeatureGroupResponse])
def list_model_groups(model_id: str, store: ModelStore = Depends(get_store)):
    results = store.list_model_groups(model_id)
    return [FeatureGroupResponse.model_validate(g) for g in results]
