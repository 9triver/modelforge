"""评估 REST API。

POST /api/v1/repos/{ns}/{name}/evaluate    上传数据 → 返回 evaluation_id
GET  /api/v1/evaluations/{id}              查状态/结果
GET  /api/v1/repos/{ns}/{name}/metrics     聚合匿名指标
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, UploadFile
from pydantic import BaseModel

from .. import db
from ..schema import ModelCardError
from ..services import evaluation as eval_svc
from ..services.dataset import resolve_dataset_payload

router = APIRouter(prefix="/api/v1", tags=["evaluations"])


class EvaluationCreated(BaseModel):
    evaluation_id: int
    status: str


class EvaluationStatus(BaseModel):
    id: int
    repo: str
    revision: str
    task: str
    status: str
    metrics: dict | None = None
    primary_metric: str | None = None
    primary_value: float | None = None
    duration_ms: int | None = None
    error: str | None = None
    created_at: str


class AggregateMetrics(BaseModel):
    count: int
    metric: str | None
    median: float | None
    p25: float | None
    p75: float | None


@router.post(
    "/repos/{namespace}/{name}/evaluate",
    response_model=EvaluationCreated,
    status_code=202,
)
async def create_evaluation(
    namespace: str,
    name: str,
    bg: BackgroundTasks,
    dataset: UploadFile | None = None,
    revision: str = Query("main"),
    dataset_repo: str | None = Query(None, description="已有 dataset 仓库（namespace/name）"),
):
    if not dataset and not dataset_repo:
        raise HTTPException(400, "必须上传数据文件或指定 dataset_repo")
    if dataset and dataset_repo:
        raise HTTPException(400, "dataset 和 dataset_repo 不能同时指定")

    repo = db.get_repo(namespace, name)
    if not repo:
        raise HTTPException(404, f"Repository '{namespace}/{name}' not found")

    try:
        sha, metadata = eval_svc.read_metadata(namespace, name, revision)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ModelCardError as e:
        raise HTTPException(400, str(e))

    if not metadata.pipeline_tag:
        raise HTTPException(400, "model_card.yaml 必须声明 pipeline_tag")

    if dataset_repo:
        try:
            payload, ds_name = resolve_dataset_payload(dataset_repo)
        except (ValueError, FileNotFoundError) as e:
            raise HTTPException(400, str(e))
    else:
        payload = await dataset.read()
        ds_name = Path(dataset.filename or "data.bin").name

    record = db.create_evaluation(repo.id, sha, metadata.pipeline_tag)
    bg.add_task(eval_svc.run_evaluation, record.id, namespace, name, sha, payload, ds_name)
    return EvaluationCreated(evaluation_id=record.id, status="queued")


@router.get("/evaluations/{eval_id}", response_model=EvaluationStatus)
def get_evaluation(eval_id: int):
    rec = db.get_evaluation(eval_id)
    if not rec:
        raise HTTPException(404, f"Evaluation {eval_id} not found")

    return EvaluationStatus(
        id=rec.id,
        repo=db.get_repo_name(rec.repo_id) or "<deleted>",
        revision=rec.revision,
        task=rec.task,
        status=rec.status,
        metrics=json.loads(rec.metrics_json) if rec.metrics_json else None,
        primary_metric=rec.primary_metric,
        primary_value=rec.primary_value,
        duration_ms=rec.duration_ms,
        error=rec.error,
        created_at=rec.created_at,
    )


@router.get(
    "/repos/{namespace}/{name}/metrics", response_model=AggregateMetrics
)
def repo_aggregate_metrics(namespace: str, name: str):
    repo = db.get_repo(namespace, name)
    if not repo:
        raise HTTPException(404, f"Repository '{namespace}/{name}' not found")
    return AggregateMetrics(**db.aggregate_repo_metrics(repo.id))
