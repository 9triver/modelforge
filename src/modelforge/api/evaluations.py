"""评估 REST API。

POST /api/v1/repos/{ns}/{name}/evaluate    上传数据 → 返回 evaluation_id
GET  /api/v1/evaluations/{id}              查状态/结果
GET  /api/v1/repos/{ns}/{name}/metrics     聚合匿名指标

Phase 2 第一版：异步用 BackgroundTasks 顶着，evaluator 用 in-process backend。
后续换 Docker backend 时只换 evaluator backend，API 不动。
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, UploadFile
from pydantic import BaseModel

from .. import db, repo_reader
from ..schema import ModelCardError, validate_model_card

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


def _read_metadata(namespace: str, name: str, revision: str):
    """从仓库读 README.md frontmatter 校验后返回 (sha, metadata)。"""
    sha = repo_reader.resolve_revision(namespace, name, revision)
    readme = repo_reader.read_file(namespace, name, sha, "README.md")
    if not readme:
        raise HTTPException(404, "README.md 不存在，无法判定 task")
    try:
        return sha, validate_model_card(readme)
    except ModelCardError as e:
        raise HTTPException(400, str(e))


def _run_evaluation(
    eval_id: int,
    namespace: str,
    name: str,
    revision: str,
    dataset_bytes: bytes,
    dataset_name: str,
) -> None:
    """后台 worker：checkout 仓库 + 落盘数据 + 跑 in-process evaluator。"""
    from ..runtime import evaluate

    db.update_evaluation(eval_id, status="running")

    workdir = Path(tempfile.mkdtemp(prefix="mf_eval_"))
    try:
        model_dir = workdir / "model"
        repo_reader.checkout_to_dir(namespace, name, revision, model_dir)

        ds_path = workdir / dataset_name
        ds_path.write_bytes(dataset_bytes)

        readme = (model_dir / "README.md").read_text()
        metadata = validate_model_card(readme)

        result = evaluate(model_dir, ds_path, metadata)

        db.update_evaluation(
            eval_id,
            status=result.status,
            metrics_json=json.dumps(result.metrics) if result.metrics else None,
            primary_metric=result.primary_metric,
            primary_value=result.primary_value,
            duration_ms=result.duration_ms,
            error=result.error,
        )
    except Exception as e:  # noqa: BLE001
        db.update_evaluation(
            eval_id, status="error", error=f"runner crashed: {e}"
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@router.post(
    "/repos/{namespace}/{name}/evaluate",
    response_model=EvaluationCreated,
    status_code=202,
)
async def create_evaluation(
    namespace: str,
    name: str,
    bg: BackgroundTasks,
    dataset: UploadFile,
    revision: str = Query("main"),
):
    repo = db.get_repo(namespace, name)
    if not repo:
        raise HTTPException(404, f"Repository '{namespace}/{name}' not found")

    sha, metadata = _read_metadata(namespace, name, revision)
    if not metadata.pipeline_tag:
        raise HTTPException(400, "model_card.yaml 必须声明 pipeline_tag")

    payload = await dataset.read()
    ds_name = Path(dataset.filename or "data.bin").name

    record = db.create_evaluation(repo.id, sha, metadata.pipeline_tag)
    bg.add_task(_run_evaluation, record.id, namespace, name, sha, payload, ds_name)
    return EvaluationCreated(evaluation_id=record.id, status="queued")


@router.get("/evaluations/{eval_id}", response_model=EvaluationStatus)
def get_evaluation(eval_id: int):
    rec = db.get_evaluation(eval_id)
    if not rec:
        raise HTTPException(404, f"Evaluation {eval_id} not found")

    repo_obj = None
    with db.connect() as c:
        row = c.execute(
            "SELECT namespace, name FROM repos WHERE id = ?", (rec.repo_id,)
        ).fetchone()
        if row:
            repo_obj = f"{row['namespace']}/{row['name']}"

    return EvaluationStatus(
        id=rec.id,
        repo=repo_obj or "<deleted>",
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
