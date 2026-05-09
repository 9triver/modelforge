"""校准 REST API（两阶段：preview → save）。

POST /api/v1/repos/{ns}/{name}/calibrate/preview   预览校准效果（不建仓库）
POST /api/v1/calibrations/{id}/save                满意后 fork 新仓库
GET  /api/v1/calibrations/{id}                     查状态/结果
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, UploadFile
from pydantic import BaseModel

from .. import db, repo_reader
from ..services import calibration as cal_svc
from ..services.dataset import resolve_dataset_payload

router = APIRouter(prefix="/api/v1", tags=["calibrations"])


# ---------- response models ----------

class CalibrationCreated(BaseModel):
    calibration_id: int
    status: str


class CalibrationStatus(BaseModel):
    id: int
    source_repo: str
    source_revision: str
    target_repo: str | None = None
    target_revision: str | None = None
    method: str
    params: dict | None = None
    before_metrics: dict | None = None
    after_metrics: dict | None = None
    primary_metric: str | None = None
    before_value: float | None = None
    after_value: float | None = None
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
    "/repos/{namespace}/{name}/calibrate/preview",
    response_model=CalibrationCreated,
    status_code=202,
)
async def preview_calibration(
    namespace: str,
    name: str,
    bg: BackgroundTasks,
    dataset: UploadFile | None = None,
    revision: str = Query("main"),
    method: str = Query("linear_bias", description="校准方法：linear_bias / segmented / stacking"),
    dataset_repo: str | None = Query(None, description="已有 dataset 仓库（namespace/name）"),
):
    """预览校准效果。不创建任何仓库，只返回 before/after 指标。"""
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

    if dataset_repo:
        try:
            payload, ds_name = resolve_dataset_payload(dataset_repo)
        except (ValueError, FileNotFoundError) as e:
            raise HTTPException(400, str(e))
    else:
        payload = await dataset.read()
        ds_name = Path(dataset.filename or "data.csv").name

    record = db.create_calibration(repo.id, sha, method)
    bg.add_task(cal_svc.run_preview, record.id, namespace, name, sha, payload, ds_name, method)
    return CalibrationCreated(calibration_id=record.id, status="queued")


@router.post(
    "/calibrations/{cal_id}/save",
    response_model=SaveResponse,
    status_code=202,
)
async def save_calibration(cal_id: int, body: SaveRequest, bg: BackgroundTasks):
    """满意后 fork 新仓库。只有 status=previewed 的校准记录可以 save。"""
    rec = db.get_calibration(cal_id)
    if not rec:
        raise HTTPException(404, f"Calibration {cal_id} not found")
    if rec.status != "previewed":
        raise HTTPException(
            400, f"只有 previewed 状态的校准可以 save（当前：{rec.status}）"
        )

    source_name = db.get_repo_name(rec.source_repo_id)
    if not source_name:
        raise HTTPException(404, "Source repo not found")

    ns, nm = source_name.split("/", 1)
    params = json.loads(rec.params_json) if rec.params_json else {}
    before = json.loads(rec.before_metrics_json) if rec.before_metrics_json else {}
    after = json.loads(rec.after_metrics_json) if rec.after_metrics_json else {}

    bg.add_task(
        cal_svc.do_fork, cal_id,
        ns, nm, rec.source_revision,
        params, before, after,
        body.target_namespace, body.target_name,
    )
    return SaveResponse(
        target_repo=f"{body.target_namespace}/{body.target_name}",
        target_revision="pending",
    )


@router.get("/calibrations/{cal_id}", response_model=CalibrationStatus)
def get_calibration(cal_id: int):
    rec = db.get_calibration(cal_id)
    if not rec:
        raise HTTPException(404, f"Calibration {cal_id} not found")

    return CalibrationStatus(
        id=rec.id,
        source_repo=db.get_repo_name(rec.source_repo_id) or "<deleted>",
        source_revision=rec.source_revision,
        target_repo=rec.target_repo,
        target_revision=rec.target_revision,
        method=rec.method,
        params=json.loads(rec.params_json) if rec.params_json else None,
        before_metrics=json.loads(rec.before_metrics_json) if rec.before_metrics_json else None,
        after_metrics=json.loads(rec.after_metrics_json) if rec.after_metrics_json else None,
        primary_metric=rec.primary_metric,
        before_value=rec.before_value,
        after_value=rec.after_value,
        status=rec.status,
        duration_ms=rec.duration_ms,
        error=rec.error,
        created_at=rec.created_at,
    )
