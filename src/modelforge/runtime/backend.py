"""Evaluator backend 分发：按配置路由到 inprocess 或 docker。

API 层调这里，不直接调 evaluate() / calibrate_by_method()。
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..config import get_settings
from ..schema import ModelCardMetadata
from .evaluator import EvaluationResult, evaluate

if TYPE_CHECKING:
    from .calibration import CalibrationResult


def run_evaluation(
    model_dir: str | Path,
    dataset_path: str | Path,
    metadata: ModelCardMetadata,
) -> EvaluationResult:
    if get_settings().eval_backend == "docker":
        from .docker_backend import docker_evaluate

        return docker_evaluate(model_dir, dataset_path, metadata)
    return evaluate(model_dir, dataset_path, metadata)


def run_calibration(
    model_dir: str | Path,
    dataset_path: str | Path,
    metadata: ModelCardMetadata,
    *,
    method: str,
    target_col: str,
) -> "CalibrationResult":
    if get_settings().eval_backend == "docker":
        from .docker_backend import docker_calibrate

        return docker_calibrate(
            model_dir, dataset_path, metadata,
            method=method, target_col=target_col,
        )

    from .calibration import CalibrationResult, calibrate_by_method
    from .datasets import forecasting as fc_ds
    from .evaluator import load_handler

    try:
        handler = load_handler(str(model_dir), "time-series-forecasting")
        handler.warmup()
        df = fc_ds.load_forecasting_csv(dataset_path, target_col=target_col)
        return calibrate_by_method(method, handler, df, target_col)
    except Exception as e:
        return CalibrationResult(status="error", error=str(e))
