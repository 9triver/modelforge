from fastapi import APIRouter, Depends, Query

from modelforge.schemas.parameters import (
    ParameterCompareRequest,
    ParameterCompareResponse,
    ParameterTemplateCreate,
    ParameterTemplateResponse,
    ParameterTemplateUpdate,
)
from modelforge.store import ModelStore, get_store

router = APIRouter(prefix="/parameter-templates", tags=["Parameter Templates"])


@router.post("", response_model=ParameterTemplateResponse, status_code=201)
def create_template(data: ParameterTemplateCreate, store: ModelStore = Depends(get_store)):
    result = store.create_parameter_template(data.model_dump())
    return ParameterTemplateResponse.model_validate(result)


@router.get("", response_model=list[ParameterTemplateResponse])
def list_templates(
    model_asset_id: str | None = None,
    algorithm_type: str | None = None,
    q: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    store: ModelStore = Depends(get_store),
):
    results = store.list_parameter_templates(
        model_asset_id=model_asset_id,
        algorithm_type=algorithm_type,
        q=q,
        skip=skip,
        limit=limit,
    )
    return [ParameterTemplateResponse.model_validate(t) for t in results]


@router.post("/compare", response_model=ParameterCompareResponse)
def compare_parameters(body: ParameterCompareRequest, store: ModelStore = Depends(get_store)):
    return store.compare_parameters(body)


@router.get("/{template_id}", response_model=ParameterTemplateResponse)
def get_template(template_id: str, store: ModelStore = Depends(get_store)):
    result = store.get_parameter_template(template_id)
    return ParameterTemplateResponse.model_validate(result)


@router.put("/{template_id}", response_model=ParameterTemplateResponse)
def update_template(
    template_id: str, data: ParameterTemplateUpdate, store: ModelStore = Depends(get_store)
):
    result = store.update_parameter_template(template_id, data.model_dump(exclude_unset=True))
    return ParameterTemplateResponse.model_validate(result)


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: str, store: ModelStore = Depends(get_store)):
    store.delete_parameter_template(template_id)
