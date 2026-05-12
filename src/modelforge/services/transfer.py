"""迁移学习业务逻辑：preview（训练+预览指标）和 fork（生成新仓库）。"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .. import db, repo_reader, storage
from ..runtime.evaluator import load_handler
from ..runtime.transfer import (
    TransferResult,
    generate_transfer_repo,
    transfer_by_method,
)
from .sandbox import model_sandbox

_WEIGHTS_CACHE: dict[int, str] = {}


def _persist_weights(src_path: str) -> str:
    """将沙盒内的权重文件复制到独立临时目录，避免沙盒清理后丢失。"""
    persist_dir = tempfile.mkdtemp(prefix="mf_weights_")
    src = Path(src_path)
    dst = Path(persist_dir) / src.name
    shutil.copy2(src, dst)
    return str(dst)


def run_transfer_preview(
    transfer_id: int,
    namespace: str,
    name: str,
    revision: str,
    dataset_bytes: bytes,
    dataset_name: str,
    method: str,
    hparams: dict | None = None,
) -> None:
    db.update_transfer(transfer_id, status="running")
    start = time.monotonic()

    def _progress_cb(epoch: int, total: int, metrics: dict) -> None:
        db.update_transfer(
            transfer_id, status="running",
            current_epoch=epoch, total_epochs=total,
        )

    try:
        with model_sandbox(namespace, name, revision, prefix="mf_transfer_") as (workdir, model_dir):
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

            result = transfer_by_method(
                method, handler, images, labels,
                hparams=hparams,
                progress_cb=_progress_cb if method.startswith("fine_tune") else None,
            )
            if result.status != "ok":
                db.update_transfer(
                    transfer_id, status="error", error=result.error,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
                return

            if result.weights_path:
                _WEIGHTS_CACHE[transfer_id] = _persist_weights(result.weights_path)

            db.update_transfer(
                transfer_id,
                status="previewed",
                classes_json=json.dumps(result.classes),
                n_classes=len(result.classes),
                n_samples=result.n_samples,
                weights_b64=result.weights_b64 or None,
                after_metrics_json=json.dumps(result.after_metrics),
                primary_metric=result.primary_metric,
                after_value=result.after_value,
                hparams_json=json.dumps(result.hparams) if result.hparams else None,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
    except Exception as e:  # noqa: BLE001
        db.update_transfer(
            transfer_id, status="error", error=str(e),
            duration_ms=int((time.monotonic() - start) * 1000),
        )


def do_transfer_fork(
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

    try:
        with model_sandbox(namespace, name, revision, with_lfs=False, prefix="mf_tfork_") as (workdir, model_dir):
            result = TransferResult(
                method=result_data["method"],
                classes=result_data["classes"],
                n_samples=result_data.get("n_samples", 0),
                n_holdout=result_data.get("n_holdout", 0),
                weights_b64=result_data.get("weights_b64", "") or "",
                weights_path=_WEIGHTS_CACHE.get(transfer_id),
                hparams=result_data.get("hparams", {}),
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
                 f"{result.method} from {source_repo}@{revision[:8]} → {len(result.classes)} classes"],
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
        wp = _WEIGHTS_CACHE.pop(transfer_id, None)
        if wp:
            parent = str(Path(wp).parent)
            shutil.rmtree(parent, ignore_errors=True)
