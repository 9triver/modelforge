"""校准业务逻辑：preview（只算指标）和 fork（生成新仓库）。"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .. import db, repo_reader, storage
from ..runtime.calibration import (
    CalibrationResult,
    generate_calibrated_repo,
)
from ..schema import validate_model_card
from .sandbox import model_sandbox


def run_preview(
    cal_id: int,
    namespace: str,
    name: str,
    revision: str,
    dataset_bytes: bytes,
    dataset_name: str,
    method: str,
) -> None:
    """后台 worker：checkout → calibrate → 只存指标，不建仓库。"""
    db.update_calibration(cal_id, status="running")
    start = time.monotonic()

    try:
        with model_sandbox(namespace, name, revision, prefix="mf_cal_") as (workdir, model_dir):
            readme = (model_dir / "README.md").read_text(encoding="utf-8")
            metadata = validate_model_card(readme)
            fc_cfg = (metadata.model_extra or {}).get("forecasting", {})
            target_col = fc_cfg.get("target")
            if not target_col:
                raise ValueError("model_card.yaml 的 forecasting.target 未声明")

            ds_path = workdir / dataset_name
            ds_path.write_bytes(dataset_bytes)

            from ..runtime.backend import run_calibration

            result = run_calibration(
                model_dir, ds_path, metadata,
                method=method, target_col=target_col,
            )
            if result.status != "ok":
                db.update_calibration(
                    cal_id, status="error", error=result.error,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
                return

            db.update_calibration(
                cal_id,
                status="previewed",
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


def do_fork(
    cal_id: int,
    namespace: str,
    name: str,
    revision: str,
    params: dict,
    before_metrics: dict,
    after_metrics: dict,
    target_namespace: str,
    target_name: str,
) -> None:
    """后台 worker：用已有校准参数组装 fork 仓库并 push。"""
    db.update_calibration(cal_id, status="saving")
    start = time.monotonic()

    try:
        with model_sandbox(namespace, name, revision, with_lfs=False, prefix="mf_fork_") as (workdir, model_dir):
            result = CalibrationResult(
                params=params,
                before_metrics=before_metrics,
                after_metrics=after_metrics,
                before_value=before_metrics.get("mape", 0),
                after_value=after_metrics.get("mape", 0),
            )

            source_repo = f"{namespace}/{name}"
            target_repo = f"{target_namespace}/{target_name}"

            fork_dir = workdir / "fork"
            generate_calibrated_repo(
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
                 f"calibrated from {source_repo}@{revision[:8]} (linear_bias a={params['a']}, b={params['b']})"],
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

            db.update_calibration(
                cal_id, status="ok",
                target_repo=target_repo, target_revision=sha,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
    except Exception as e:  # noqa: BLE001
        db.update_calibration(
            cal_id, status="error", error=f"fork failed: {e}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
