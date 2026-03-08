"""Local subprocess implementation of TrainingBackend protocol.

Runs training scripts as local subprocesses, capturing logs in real-time.
This is the refactored version of the original ``runner.py``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_str() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalSubprocessBackend:
    """Runs training jobs as local subprocesses.

    Each job executes a Python script in a version directory,
    captures stdout/stderr, and reports status back via the metadata store.
    """

    def __init__(self, metadata_store: Any) -> None:
        self._store = metadata_store
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}  # job_id -> {thread, process, ...}

    def submit(self, job: dict) -> str:
        """Submit a training job. Returns job_id.

        Expected job keys:
            model_id, base_version, overrides, draft_version,
            pipeline (the pipeline definition dict)
        """
        from fastapi import HTTPException

        model_id = job["model_id"]
        base_version = job["base_version"]
        overrides = job.get("overrides")
        draft_version = job.get("draft_version")
        pipeline = job.get("pipeline")

        if pipeline is None:
            pipeline = self._store.get_pipeline(model_id)
        if pipeline is None:
            raise HTTPException(400, "Pipeline definition not found. Create one first.")

        training = pipeline.get("training", {})
        script = training.get("script")
        if not script:
            raise HTTPException(400, "Pipeline missing training.script field")

        slug = self._store.get_model_slug(model_id)
        base_vdir = self._store._version_dir(slug, base_version).resolve()
        if not base_vdir.exists():
            raise HTTPException(404, f"Base version '{base_version}' not found")

        is_draft = False
        if draft_version:
            from modelforge.adapters.filesystem.yaml_io import YAMLFile

            dv = draft_version if draft_version.startswith("v") else f"v{draft_version}"
            new_vdir = self._store._version_dir(slug, dv).resolve()
            if not new_vdir.exists():
                raise HTTPException(404, f"Draft version '{draft_version}' not found")
            vyaml = new_vdir / "version.yaml"
            if vyaml.exists():
                vdata = YAMLFile.read(vyaml)
                if vdata.get("stage") != "draft":
                    raise HTTPException(
                        400,
                        f"Version '{draft_version}' is not a draft (stage: {vdata.get('stage')})",
                    )
            next_version = dv
            is_draft = True
        else:
            next_version = self._store.next_version(slug, base_version)
            new_vdir = self._store._version_dir(slug, next_version).resolve()

        next_version_display = next_version.lstrip("v")

        run = self._store.create_run(model_id, {
            "base_version": base_version,
            "target_version": next_version_display,
            "pipeline_snapshot": pipeline,
            "overrides": overrides,
        })
        run_id = run["id"]

        t = threading.Thread(
            target=self._execute,
            args=(
                model_id, run_id, slug, base_vdir,
                new_vdir, next_version, pipeline,
                overrides, is_draft,
            ),
            daemon=True,
        )
        t.start()

        with self._lock:
            self._jobs[run_id] = {"thread": t, "run": run}

        return run_id

    def get_status(self, job_id: str) -> dict:
        with self._lock:
            if job_id in self._jobs:
                return self._jobs[job_id].get("run", {})
        return {}

    def get_logs(self, job_id: str, tail: int = 100) -> list[str]:
        # Logs are stored in the run record in metadata store
        return []

    def cancel(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job and "process" in job:
                job["process"].terminate()

    def list_jobs(self, filters: dict | None = None) -> list[dict]:
        with self._lock:
            return [j.get("run", {}) for j in self._jobs.values()]

    # ── Internal ──

    def _execute(
        self,
        model_id: str,
        run_id: str,
        slug: str,
        base_vdir: Path,
        new_vdir: Path,
        next_version: str,
        pipeline: dict,
        overrides: dict | None = None,
        is_draft: bool = False,
    ):
        next_version_display = next_version.lstrip("v")
        log_lines: list[str] = []
        overrides = overrides or {}
        last_flush = time.monotonic()

        def _log(line: str):
            nonlocal last_flush
            log_lines.append(line)
            now = time.monotonic()
            if now - last_flush >= 2.0:
                self._store.update_run(
                    model_id, run_id,
                    {"log": "\n".join(log_lines)},
                )
                last_flush = now

        def _flush_log():
            self._store.update_run(
                model_id, run_id,
                {"log": "\n".join(log_lines)},
            )

        try:
            # 1. Copy base version (skip for draft)
            if is_draft:
                _log(f"[准备] 使用草稿版本目录 {new_vdir.name} (跳过复制)")
            else:
                _log(f"[准备] 复制基础版本 {base_vdir.name} -> {new_vdir.name}")
                shutil.copytree(base_vdir, new_vdir)
                old_vyaml = new_vdir / "version.yaml"
                if old_vyaml.exists():
                    old_vyaml.unlink()

            # 2. Resolve the training script
            training = pipeline.get("training", {})
            script = training["script"]
            script_path = new_vdir / "code" / script

            if not script_path.exists():
                raise FileNotFoundError(f"Training script not found: code/{script}")

            # 3. Build command with CLI args
            cmd = [sys.executable, str(script_path)]

            data_prep = pipeline.get("data_prep", {})
            dataset = overrides.get("dataset") or data_prep.get("dataset")
            feature_config = overrides.get("feature_config") or data_prep.get("feature_config")
            params = overrides.get("params") or training.get("params")

            if dataset:
                cmd += ["--dataset", f"datasets/{dataset}"]
            if feature_config:
                cmd += ["--features", f"features/{feature_config}"]
            if params:
                cmd += ["--params", f"params/{params}"]

            warm_start = overrides.get("warm_start")
            if warm_start:
                cmd += ["--warm-start", f"weights/{warm_start}"]

            output_cfg = pipeline.get("output", {})
            output_format = output_cfg.get("format", "joblib")
            weights_filename = self._find_weights_file(new_vdir, output_format)
            if weights_filename:
                cmd += ["--output", f"weights/{weights_filename}"]

            if overrides:
                _log(f"[准备] 参数覆写: {overrides}")

            _log(f"[执行] 运行命令: {' '.join(cmd)}")
            _log(f"[执行] 工作目录: {new_vdir}")

            # 4. Run subprocess
            proc = subprocess.Popen(
                cmd,
                cwd=str(new_vdir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            with self._lock:
                if run_id in self._jobs:
                    self._jobs[run_id]["process"] = proc

            self._store.update_run(model_id, run_id, {
                "status": "running",
                "pid": proc.pid,
                "log": "\n".join(log_lines),
            })
            last_flush = time.monotonic()

            for line in proc.stdout:
                _log(line.rstrip())

            proc.wait()

            if proc.returncode != 0:
                raise RuntimeError(f"Training script exited with code {proc.returncode}")

            _log("[完成] 训练脚本执行成功")

            # 5. Collect metrics
            metrics = None
            metrics_file = new_vdir / "metrics.json"
            if metrics_file.exists():
                with open(metrics_file) as f:
                    metrics = json.load(f)
                _log(f"[完成] 读取评估指标: {metrics}")

            # 6. Create or finalize version record
            weights_path = self._find_weights_path(new_vdir)
            file_size = weights_path.stat().st_size if weights_path else 0
            fmt = pipeline.get("output", {}).get("format", "joblib")
            w_rel = str(weights_path.relative_to(new_vdir)) if weights_path else None

            if is_draft:
                version_data = self._store.finalize_draft_version(
                    model_id, slug, next_version, new_vdir,
                    metrics=metrics, file_format=fmt,
                    file_size=file_size, weights_rel=w_rel,
                )
            else:
                base_version_id = self._store.get_version_id_by_str(slug, base_vdir.name)
                version_data = self._store.create_version_from_run(
                    model_id, slug, next_version, new_vdir,
                    metrics=metrics, file_format=fmt,
                    file_size=file_size, weights_rel=w_rel,
                    parent_version_id=base_version_id,
                )

            _log(f"[完成] 已创建新版本 {next_version} (id={version_data['id']})")

            self._store.update_run(model_id, run_id, {
                "status": "success",
                "finished_at": _now_str(),
                "result_version_id": version_data["id"],
                "result_version": next_version_display,
                "metrics": metrics,
                "log": "\n".join(log_lines),
            })

        except Exception as e:
            _log(f"[错误] {e}")
            if not is_draft and new_vdir.exists():
                shutil.rmtree(new_vdir, ignore_errors=True)
            _flush_log()
            self._store.update_run(model_id, run_id, {
                "status": "failed",
                "finished_at": _now_str(),
                "error": str(e),
                "log": "\n".join(log_lines),
            })

    def _find_weights_file(self, vdir: Path, fmt: str) -> str | None:
        weights_dir = vdir / "weights"
        if not weights_dir.exists():
            return None
        for f in weights_dir.iterdir():
            if f.is_file() and not f.name.startswith("."):
                return f.name
        return None

    def _find_weights_path(self, vdir: Path) -> Path | None:
        weights_dir = vdir / "weights"
        if not weights_dir.exists():
            return None
        for f in weights_dir.iterdir():
            if f.is_file() and not f.name.startswith("."):
                return f
        return None
