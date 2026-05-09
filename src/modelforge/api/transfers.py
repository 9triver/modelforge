"""迁移学习 REST API（两阶段：preview → save）。

POST /api/v1/repos/{ns}/{name}/transfer/preview   预览迁移效果（不建仓库）
POST /api/v1/transfers/{id}/save                   满意后 fork 新仓库
GET  /api/v1/transfers/{id}                        查状态/结果
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, UploadFile
from pydantic import BaseModel

from .. import db, repo_reader
from ..services import transfer as tr_svc
from ..services.dataset import resolve_dataset_payload

router = APIRouter(prefix="/api/v1", tags=["transfers"])


# ---------- response models ----------

class TransferCreated(BaseModel):
    transfer_id: int
    status: str


class TransferStatus(BaseModel):
    id: int
    source_repo: str
    source_revision: str
    target_repo: str | None = None
    target_revision: str | None = None
    method: str
    classes: list[str] | None = None
    n_classes: int | None = None
    n_samples: int | None = None
    after_metrics: dict | None = None
    primary_metric: str | None = None
    after_value: float | None = None
    hparams: dict | None = None
    current_epoch: int | None = None
    total_epochs: int | None = None
    status: str
    duration_ms: int | None = None
    error: str | None = None
    created_at: str


class SaveRequest(BaseModel):
    target_namespace: str
    target_name: str


class SaveResponse(BaseModel):
    target_repo: str
    target_revision: str


# ---------- endpoints ----------

@router.post(
    "/repos/{namespace}/{name}/transfer/preview",
    response_model=TransferCreated,
    status_code=202,
)
async def preview_transfer(
    namespace: str,
    name: str,
    bg: BackgroundTasks,
    dataset: UploadFile | None = None,
    revision: str = Query("main"),
    method: str = Query("linear_probe"),
    epochs: int = Query(10),
    lr: float = Query(1e-5),
    unfreeze_layers: int = Query(2),
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
        sha = repo_reader.resolve_revision(namespace, name, revision)
    except FileNotFoundError:
        raise HTTPException(400, f"Revision '{revision}' not found")

    hparams = {"epochs": epochs, "lr": lr, "unfreeze_layers": unfreeze_layers}

    if dataset_repo:
        try:
            payload, ds_name = resolve_dataset_payload(dataset_repo, force_zip=True)
        except (ValueError, FileNotFoundError) as e:
            raise HTTPException(400, str(e))
    else:
        payload = await dataset.read()
        ds_name = Path(dataset.filename or "data.zip").name

    record = db.create_transfer(repo.id, sha, method)
    bg.add_task(tr_svc.run_transfer_preview, record.id, namespace, name, sha, payload, ds_name, method, hparams)
    return TransferCreated(transfer_id=record.id, status="queued")


@router.post(
    "/transfers/{transfer_id}/save",
    response_model=SaveResponse,
    status_code=202,
)
async def save_transfer(transfer_id: int, body: SaveRequest, bg: BackgroundTasks):
    rec = db.get_transfer(transfer_id)
    if not rec:
        raise HTTPException(404, f"Transfer {transfer_id} not found")
    if rec.status != "previewed":
        raise HTTPException(400, f"只有 previewed 状态可以 save（当前：{rec.status}）")

    source_name = db.get_repo_name(rec.source_repo_id)
    if not source_name:
        raise HTTPException(404, "Source repo not found")

    ns, nm = source_name.split("/", 1)
    result_data = {
        "method": rec.method,
        "classes": json.loads(rec.classes_json) if rec.classes_json else [],
        "n_samples": rec.n_samples,
        "weights_b64": rec.weights_b64 or "",
        "hparams": json.loads(rec.hparams_json) if rec.hparams_json else {},
        "after_metrics": json.loads(rec.after_metrics_json) if rec.after_metrics_json else {},
        "after_value": rec.after_value,
    }

    bg.add_task(
        tr_svc.do_transfer_fork, transfer_id,
        ns, nm, rec.source_revision,
        result_data, body.target_namespace, body.target_name,
    )
    return SaveResponse(
        target_repo=f"{body.target_namespace}/{body.target_name}",
        target_revision="pending",
    )


@router.get("/transfers/{transfer_id}", response_model=TransferStatus)
def get_transfer(transfer_id: int):
    rec = db.get_transfer(transfer_id)
    if not rec:
        raise HTTPException(404, f"Transfer {transfer_id} not found")

    return TransferStatus(
        id=rec.id,
        source_repo=db.get_repo_name(rec.source_repo_id) or "<deleted>",
        source_revision=rec.source_revision,
        target_repo=rec.target_repo,
        target_revision=rec.target_revision,
        method=rec.method,
        classes=json.loads(rec.classes_json) if rec.classes_json else None,
        n_classes=rec.n_classes,
        n_samples=rec.n_samples,
        after_metrics=json.loads(rec.after_metrics_json) if rec.after_metrics_json else None,
        primary_metric=rec.primary_metric,
        after_value=rec.after_value,
        hparams=json.loads(rec.hparams_json) if rec.hparams_json else None,
        current_epoch=rec.current_epoch,
        total_epochs=rec.total_epochs,
        status=rec.status,
        duration_ms=rec.duration_ms,
        error=rec.error,
        created_at=rec.created_at,
    )
