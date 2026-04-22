"""校准 REST API。

POST /api/v1/repos/{ns}/{name}/calibrate   上传校准数据 → fork 新仓库
GET  /api/v1/calibrations/{id}             查状态/结果
"""
from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, UploadFile
from pydantic import BaseModel

from .. import db, repo_reader, storage
from ..client import ModelHub
from ..runtime.calibration import (
    CalibrationResult,
    calibrate_forecasting,
    compute_data_hash,
    generate_calibrated_repo,
)
from ..runtime.evaluator import load_handler
from ..schema import ModelCardError, parse_frontmatter, validate_model_card

router = APIRouter(prefix="/api/v1", tags=["calibrations"])


class CalibrationCreated(BaseModel):
    calibration_id: int
    status: str


class CalibrationStatus(BaseModel):
    id: int
    source_repo: str
    source_revision: str
    target_repo: str | None
    target_revision: str | None
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


def _run_calibration(
    cal_id: int,
    namespace: str,
    name: str,
    revision: str,
    dataset_bytes: bytes,
    dataset_name: str,
    target_namespace: str,
    target_name: str,
) -> None:
    """后台 worker：checkout → calibrate → fork 新仓库。"""
    import pandas as pd

    db.update_calibration(cal_id, status="running")
    start = time.monotonic()
    workdir = Path(tempfile.mkdtemp(prefix="mf_cal_"))

    try:
        model_dir = workdir / "model"
        repo_reader.checkout_to_dir(namespace, name, revision, model_dir)
        repo_reader.materialize_lfs(model_dir)

        readme = (model_dir / "README.md").read_text(encoding="utf-8")
        metadata = validate_model_card(readme)
        fc_cfg = (metadata.model_extra or {}).get("forecasting", {})
        target_col = fc_cfg.get("target")
        if not target_col:
            raise ValueError("model_card.yaml 的 forecasting.target 未声明")

        ds_path = workdir / dataset_name
        ds_path.write_bytes(dataset_bytes)

        from ..runtime.datasets import forecasting as fc_ds
        cal_df = fc_ds.load_forecasting_csv(ds_path, target_col=target_col)

        handler = load_handler(model_dir, "time-series-forecasting")
        handler.warmup()

        result = calibrate_forecasting(handler, cal_df, target_col)
        if result.status != "ok":
            db.update_calibration(
                cal_id, status="error",
                error=result.error,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
            return

        data_hash = compute_data_hash(dataset_bytes)
        source_repo = f"{namespace}/{name}"
        target_repo = f"{target_namespace}/{target_name}"

        fork_dir = workdir / "fork"
        generate_calibrated_repo(
            source_dir=model_dir,
            result=result,
            source_repo=source_repo,
            source_revision=revision,
            target_repo=target_repo,
            data_hash=data_hash,
            dest=fork_dir,
        )

        # 用内部 API 创建 + push fork 仓库
        # 先确保 user 存在（复用 source repo 的 owner）
        source_repo_obj = db.get_repo(namespace, name)
        if not db.get_repo(target_namespace, target_name):
            try:
                storage.create_bare_repo(target_namespace, target_name)
            except storage.RepoStorageError:
                pass
            db.create_repo(
                target_namespace, target_name,
                owner_id=source_repo_obj.owner_id if source_repo_obj else 1,
            )

        # git push fork 内容到裸仓库
        import subprocess
        bare = storage.repo_path(target_namespace, target_name)
        tmp_git = workdir / "git_push"
        subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_git)], check=True)
        subprocess.run(["git", "-C", str(tmp_git), "config", "user.email", "modelforge@local"], check=True)
        subprocess.run(["git", "-C", str(tmp_git), "config", "user.name", "ModelForge"], check=True)
        # copy fork content
        for p in fork_dir.rglob("*"):
            if p.is_file():
                rel = p.relative_to(fork_dir)
                dst = tmp_git / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dst)
        subprocess.run(["git", "-C", str(tmp_git), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(tmp_git), "commit", "-q", "-m",
             f"calibrated from {source_repo}@{revision[:8]} (linear_bias a={result.params['a']}, b={result.params['b']})"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_git), "push", "-q", str(bare), "main"],
            check=True,
        )
        # get commit sha
        sha = subprocess.run(
            ["git", "-C", str(tmp_git), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()

        db.update_calibration(
            cal_id,
            status="ok",
            target_repo=target_repo,
            target_revision=sha,
            params_json=json.dumps(result.params),
            before_metrics_json=json.dumps(result.before_metrics),
            after_metrics_json=json.dumps(result.after_metrics),
            primary_metric=result.primary_metric,
            before_value=result.before_value,
            after_value=result.after_value,
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except Exception as e:  # noqa: BLE001
        db.update_calibration(
            cal_id, status="error", error=str(e),
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@router.post(
    "/repos/{namespace}/{name}/calibrate",
    response_model=CalibrationCreated,
    status_code=202,
)
async def create_calibration(
    namespace: str,
    name: str,
    bg: BackgroundTasks,
    dataset: UploadFile,
    revision: str = Query("main"),
    target_namespace: str = Query(..., description="Fork 目标 namespace"),
    target_name: str = Query(..., description="Fork 目标 name"),
):
    repo = db.get_repo(namespace, name)
    if not repo:
        raise HTTPException(404, f"Repository '{namespace}/{name}' not found")

    try:
        sha = repo_reader.resolve_revision(namespace, name, revision)
    except FileNotFoundError:
        raise HTTPException(400, f"Revision '{revision}' not found")

    payload = await dataset.read()
    ds_name = Path(dataset.filename or "data.csv").name

    record = db.create_calibration(repo.id, sha, "linear_bias")
    bg.add_task(
        _run_calibration, record.id, namespace, name, sha,
        payload, ds_name, target_namespace, target_name,
    )
    return CalibrationCreated(calibration_id=record.id, status="queued")


@router.get("/calibrations/{cal_id}", response_model=CalibrationStatus)
def get_calibration(cal_id: int):
    rec = db.get_calibration(cal_id)
    if not rec:
        raise HTTPException(404, f"Calibration {cal_id} not found")

    source_name = "<deleted>"
    with db.connect() as c:
        row = c.execute(
            "SELECT namespace, name FROM repos WHERE id = ?", (rec.source_repo_id,)
        ).fetchone()
        if row:
            source_name = f"{row['namespace']}/{row['name']}"

    return CalibrationStatus(
        id=rec.id,
        source_repo=source_name,
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
