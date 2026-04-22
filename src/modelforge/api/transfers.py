"""迁移学习 REST API（两阶段：preview → save）。

POST /api/v1/repos/{ns}/{name}/transfer/preview   预览迁移效果（不建仓库）
POST /api/v1/transfers/{id}/save                   满意后 fork 新仓库
GET  /api/v1/transfers/{id}                        查状态/结果
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, UploadFile
from pydantic import BaseModel

from .. import db, repo_reader, storage
from ..runtime.evaluator import load_handler
from ..runtime.transfer import (
    TransferResult,
    compute_data_hash,
    generate_transfer_repo,
    transfer_by_method,
)
from ..schema import validate_model_card

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


# ---------- preview worker ----------

def _run_transfer_preview(
    transfer_id: int,
    namespace: str,
    name: str,
    revision: str,
    dataset_bytes: bytes,
    dataset_name: str,
    method: str,
) -> None:
    db.update_transfer(transfer_id, status="running")
    start = time.monotonic()
    workdir = Path(tempfile.mkdtemp(prefix="mf_transfer_"))

    try:
        model_dir = workdir / "model"
        repo_reader.checkout_to_dir(namespace, name, revision, model_dir)
        repo_reader.materialize_lfs(model_dir)

        ds_path = workdir / dataset_name
        ds_path.write_bytes(dataset_bytes)

        from ..runtime.datasets import image_classification as ic_ds

        p = Path(ds_path)
        if p.suffix.lower() == ".zip":
            tmp_extract = workdir / "extracted"
            root = ic_ds.unpack_zip(p, tmp_extract)
        else:
            root = p

        images, labels = ic_ds.load_image_folder(root)

        handler = load_handler(model_dir, "image-classification")
        handler.warmup()

        result = transfer_by_method(method, handler, images, labels)
        if result.status != "ok":
            db.update_transfer(
                transfer_id, status="error", error=result.error,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
            return

        db.update_transfer(
            transfer_id,
            status="previewed",
            classes_json=json.dumps(result.classes),
            n_classes=len(result.classes),
            n_samples=result.n_samples,
            weights_b64=result.weights_b64,
            after_metrics_json=json.dumps(result.after_metrics),
            primary_metric=result.primary_metric,
            after_value=result.after_value,
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except Exception as e:  # noqa: BLE001
        db.update_transfer(
            transfer_id, status="error", error=str(e),
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ---------- save (fork) ----------

def _do_transfer_fork(
    transfer_id: int,
    namespace: str,
    name: str,
    revision: str,
    result_data: dict,
    target_namespace: str,
    target_name: str,
) -> None:
    db.update_transfer(transfer_id, status="saving")
    start = time.monotonic()
    workdir = Path(tempfile.mkdtemp(prefix="mf_tfork_"))

    try:
        model_dir = workdir / "model"
        repo_reader.checkout_to_dir(namespace, name, revision, model_dir)
        repo_reader.materialize_lfs(model_dir)

        result = TransferResult(
            method=result_data["method"],
            classes=result_data["classes"],
            n_samples=result_data.get("n_samples", 0),
            n_holdout=result_data.get("n_holdout", 0),
            weights_b64=result_data["weights_b64"],
            after_metrics=result_data.get("after_metrics", {}),
            after_value=result_data.get("after_value", 0),
        )

        source_repo = f"{namespace}/{name}"
        target_repo = f"{target_namespace}/{target_name}"

        fork_dir = workdir / "fork"
        generate_transfer_repo(
            source_dir=model_dir,
            result=result,
            source_repo=source_repo,
            source_revision=revision,
            target_repo=target_repo,
            data_hash="preview",
            dest=fork_dir,
        )

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

        bare = storage.repo_path(target_namespace, target_name)
        tmp_git = workdir / "git_push"
        subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_git)], check=True)
        subprocess.run(["git", "-C", str(tmp_git), "config", "user.email", "modelforge@local"], check=True)
        subprocess.run(["git", "-C", str(tmp_git), "config", "user.name", "ModelForge"], check=True)
        for p in fork_dir.rglob("*"):
            if p.is_file():
                rel = p.relative_to(fork_dir)
                dst = tmp_git / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dst)
        subprocess.run(["git", "-C", str(tmp_git), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(tmp_git), "commit", "-q", "-m",
             f"linear probe from {source_repo}@{revision[:8]} → {len(result.classes)} classes"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_git), "push", "-q", str(bare), "main"],
            check=True,
        )
        sha = subprocess.run(
            ["git", "-C", str(tmp_git), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()

        db.update_transfer(
            transfer_id, status="ok",
            target_repo=target_repo, target_revision=sha,
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except Exception as e:  # noqa: BLE001
        db.update_transfer(
            transfer_id, status="error", error=f"fork failed: {e}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


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
    dataset: UploadFile,
    revision: str = Query("main"),
    method: str = Query("linear_probe"),
):
    repo = db.get_repo(namespace, name)
    if not repo:
        raise HTTPException(404, f"Repository '{namespace}/{name}' not found")
    try:
        sha = repo_reader.resolve_revision(namespace, name, revision)
    except FileNotFoundError:
        raise HTTPException(400, f"Revision '{revision}' not found")

    payload = await dataset.read()
    ds_name = Path(dataset.filename or "data.zip").name
    record = db.create_transfer(repo.id, sha, method)
    bg.add_task(_run_transfer_preview, record.id, namespace, name, sha, payload, ds_name, method)
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

    with db.connect() as c:
        row = c.execute(
            "SELECT namespace, name FROM repos WHERE id = ?", (rec.source_repo_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Source repo not found")

    result_data = {
        "method": rec.method,
        "classes": json.loads(rec.classes_json) if rec.classes_json else [],
        "n_samples": rec.n_samples,
        "weights_b64": rec.weights_b64 or "",
        "after_metrics": json.loads(rec.after_metrics_json) if rec.after_metrics_json else {},
        "after_value": rec.after_value,
    }

    bg.add_task(
        _do_transfer_fork, transfer_id,
        row["namespace"], row["name"], rec.source_revision,
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

    source_name = "<deleted>"
    with db.connect() as c:
        row = c.execute(
            "SELECT namespace, name FROM repos WHERE id = ?", (rec.source_repo_id,)
        ).fetchone()
        if row:
            source_name = f"{row['namespace']}/{row['name']}"

    return TransferStatus(
        id=rec.id,
        source_repo=source_name,
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
        status=rec.status,
        duration_ms=rec.duration_ms,
        error=rec.error,
        created_at=rec.created_at,
    )
