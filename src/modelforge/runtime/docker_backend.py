"""Docker 沙箱 backend：在容器里跑 evaluate / calibrate。

宿主机负责 checkout + LFS 实化 + 落盘数据，本模块只管：
  1. 写 manifest.json
  2. 构建 docker run 命令
  3. 跑容器、等结果
  4. 读 /output/result.json 反序列化
"""
from __future__ import annotations

import dataclasses
import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..schema import ModelCardMetadata
from .evaluator import EvaluationResult

_TASK_IMAGE = {
    "time-series-forecasting": "timeseries",
    "image-classification": "vision",
    "object-detection": "vision",
}

_GPU_TASKS = {"image-classification", "object-detection"}


def _build_cmd(
    *,
    container_name: str,
    image: str,
    model_dir: Path,
    input_dir: Path,
    dataset_path: Path,
    output_dir: Path,
    task: str,
) -> list[str]:
    cfg = get_settings()
    cmd = [
        "docker", "run", "--rm",
        "--name", container_name,
        "--network", "none",
        "--memory", cfg.docker_memory,
        "--cpus", str(cfg.docker_cpus),
    ]
    if cfg.docker_gpu and task in _GPU_TASKS:
        cmd += ["--gpus", "all"]
    cmd += [
        "-v", f"{model_dir}:/model:ro",
        "-v", f"{input_dir}:/input:ro",
        "-v", f"{dataset_path.parent}:/data:ro",
        "-v", f"{output_dir}:/output",
        image,
    ]
    return cmd


def _write_manifest(dest: Path, manifest: dict[str, Any]) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "manifest.json").write_text(json.dumps(manifest, default=str))


def _read_result(output_dir: Path) -> dict[str, Any]:
    result_path = output_dir / "result.json"
    if not result_path.is_file():
        raise RuntimeError("容器未产出 result.json")
    return json.loads(result_path.read_text())


def _run_container(cmd: list[str], container_name: str, timeout: int) -> str:
    """运行容器，返回 stdout。超时时 kill 容器。"""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        subprocess.run(
            ["docker", "kill", container_name],
            capture_output=True, timeout=10,
        )
        raise
    if proc.returncode != 0:
        raise RuntimeError(
            f"容器退出码 {proc.returncode}\nstderr: {proc.stderr[-2000:]}"
        )
    return proc.stdout


def docker_evaluate(
    model_dir: str | Path,
    dataset_path: str | Path,
    metadata: ModelCardMetadata,
) -> EvaluationResult:
    cfg = get_settings()
    task = metadata.pipeline_tag or ""
    tag = _TASK_IMAGE.get(task, "timeseries")
    image = f"{cfg.docker_image_prefix}:{tag}"
    container_name = f"mf-eval-{uuid.uuid4().hex[:8]}"

    model_dir = Path(model_dir).resolve()
    dataset_path = Path(dataset_path).resolve()
    input_dir = Path(tempfile.mkdtemp(prefix="mf_dock_in_"))
    output_dir = Path(tempfile.mkdtemp(prefix="mf_dock_out_"))

    try:
        _write_manifest(input_dir, {
            "mode": "evaluate",
            "model_dir": "/model",
            "dataset_path": f"/data/{dataset_path.name}",
            "metadata": metadata.model_dump(),
        })

        cmd = _build_cmd(
            container_name=container_name,
            image=image,
            model_dir=model_dir,
            input_dir=input_dir,
            dataset_path=dataset_path,
            output_dir=output_dir,
            task=task,
        )

        _run_container(cmd, container_name, cfg.docker_timeout)
        raw = _read_result(output_dir)
        return EvaluationResult(**raw)

    except subprocess.TimeoutExpired:
        return EvaluationResult(
            task=task, status="error",
            error=f"容器超时（{cfg.docker_timeout}s）",
        )
    except Exception as e:
        return EvaluationResult(
            task=task, status="error", error=f"docker backend: {e}",
        )
    finally:
        shutil.rmtree(input_dir, ignore_errors=True)
        shutil.rmtree(output_dir, ignore_errors=True)


def docker_calibrate(
    model_dir: str | Path,
    dataset_path: str | Path,
    metadata: ModelCardMetadata,
    *,
    method: str,
    target_col: str,
) -> "CalibrationResult":
    from .calibration import CalibrationResult

    cfg = get_settings()
    image = f"{cfg.docker_image_prefix}:timeseries"
    container_name = f"mf-cal-{uuid.uuid4().hex[:8]}"

    model_dir = Path(model_dir).resolve()
    dataset_path = Path(dataset_path).resolve()
    input_dir = Path(tempfile.mkdtemp(prefix="mf_dock_in_"))
    output_dir = Path(tempfile.mkdtemp(prefix="mf_dock_out_"))

    try:
        _write_manifest(input_dir, {
            "mode": "calibrate",
            "model_dir": "/model",
            "dataset_path": f"/data/{dataset_path.name}",
            "metadata": metadata.model_dump(),
            "calibrate_method": method,
            "target_col": target_col,
        })

        cmd = _build_cmd(
            container_name=container_name,
            image=image,
            model_dir=model_dir,
            input_dir=input_dir,
            dataset_path=dataset_path,
            output_dir=output_dir,
            task="time-series-forecasting",
        )

        _run_container(cmd, container_name, cfg.docker_timeout)
        raw = _read_result(output_dir)
        return CalibrationResult(**raw)

    except subprocess.TimeoutExpired:
        return CalibrationResult(
            status="error", error=f"容器超时（{cfg.docker_timeout}s）",
        )
    except Exception as e:
        return CalibrationResult(
            status="error", error=f"docker backend: {e}",
        )
    finally:
        shutil.rmtree(input_dir, ignore_errors=True)
        shutil.rmtree(output_dir, ignore_errors=True)

