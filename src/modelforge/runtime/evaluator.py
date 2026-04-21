"""runtime.evaluator — 把 handler + dataset + metrics 串起来。

Phase 2 第一版：当前进程执行（无 sandbox），足够本地开发 + unit test。
Docker 沙箱作为独立 backend 后续叠加。

API:

    result = evaluate(
        model_dir="/path/to/repo/checkout",
        dataset_path="/path/to/user/data.csv",  # or .zip for image
        metadata=ModelCardMetadata(...),
    )
    # result.metrics -> {"mape": 0.08, "rmse": ..., ...}
    # result.primary_metric, result.primary_value
    # result.duration_ms, result.error
"""
from __future__ import annotations

import importlib.util
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..schema import ModelCardMetadata
from .metrics import classification as cls_metrics
from .metrics import forecasting as fc_metrics
from .tasks import get_task_handler
from .tasks.base import TaskHandler


@dataclass
class EvaluationResult:
    task: str
    status: str  # "ok" | "error"
    metrics: dict[str, Any] = field(default_factory=dict)
    primary_metric: str | None = None
    primary_value: float | None = None
    duration_ms: int = 0
    error: str | None = None
    error_detail: str | None = None


class HandlerLoadError(Exception):
    """handler.py 缺失或类不合法。"""


def load_handler(model_dir: str | Path, task: str) -> TaskHandler:
    """从 model_dir/handler.py 动态 import Handler，校验继承后实例化。"""
    model_dir = Path(model_dir)
    handler_path = model_dir / "handler.py"
    if not handler_path.is_file():
        raise HandlerLoadError(f"缺少 handler.py：{handler_path}")

    base_cls = get_task_handler(task)

    # 唯一 module 名，避免多 handler 互相覆盖
    mod_name = f"_modelforge_handler_{abs(hash(str(handler_path)))}"
    spec = importlib.util.spec_from_file_location(mod_name, handler_path)
    if spec is None or spec.loader is None:
        raise HandlerLoadError(f"无法加载 handler.py：{handler_path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        raise HandlerLoadError(f"handler.py 导入失败：{e}") from e

    HandlerCls = getattr(module, "Handler", None)
    if HandlerCls is None:
        raise HandlerLoadError("handler.py 必须定义名为 'Handler' 的类")
    if not (isinstance(HandlerCls, type) and issubclass(HandlerCls, base_cls)):
        raise HandlerLoadError(
            f"Handler 必须继承 {base_cls.__name__}（task={task}），"
            f"实际：{HandlerCls!r}"
        )

    return HandlerCls(str(model_dir))


# ---------- per-task evaluators ----------


def _eval_forecasting(
    handler: TaskHandler,
    dataset_path: str | Path,
    metadata: ModelCardMetadata,
) -> tuple[dict, str, float | None]:
    from .datasets import forecasting as fc_ds

    fc_cfg = (metadata.model_extra or {}).get("forecasting", {})
    target_col = fc_cfg.get("target")
    if not target_col:
        raise ValueError("model_card.yaml 的 forecasting.target 未声明")
    required = (fc_cfg.get("features") or {}).get("required") or []

    df = fc_ds.load_forecasting_csv(
        dataset_path, target_col=target_col, required_features=required
    )
    pred_df = handler.predict(df)

    if "timestamp" not in pred_df.columns or "prediction" not in pred_df.columns:
        raise ValueError(
            f"handler.predict 必须返回含 'timestamp' 和 'prediction' 的 DataFrame，"
            f"实际列：{list(pred_df.columns)}"
        )

    import pandas as pd

    pred_df = pred_df.copy()
    pred_df["timestamp"] = pd.to_datetime(pred_df["timestamp"])
    joined = df[["timestamp", target_col]].merge(
        pred_df[["timestamp", "prediction"]], on="timestamp", how="inner"
    )
    if joined.empty:
        raise ValueError("预测结果与真实值无时间重叠，无法计算指标")

    y_true = joined[target_col].tolist()
    y_pred = joined["prediction"].tolist()
    metrics = fc_metrics.compute_all(y_true, y_pred)
    primary = "mape"
    return metrics, primary, metrics.get(primary)


def _eval_image_classification(
    handler: TaskHandler,
    dataset_path: str | Path,
    metadata: ModelCardMetadata,
) -> tuple[dict, str, float | None]:
    from .datasets import image_classification as ic_ds

    p = Path(dataset_path)
    if p.suffix.lower() == ".zip":
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="mf_eval_"))
        root = ic_ds.unpack_zip(p, tmp)
    else:
        root = p

    images, labels = ic_ds.load_image_folder(root)
    predictions = handler.predict(images)

    if len(predictions) != len(images):
        raise ValueError(
            f"handler 返回 {len(predictions)} 条预测，与输入 {len(images)} 张图不匹配"
        )

    top1 = []
    for preds in predictions:
        if not preds:
            top1.append(None)
            continue
        best = max(preds, key=lambda d: d.get("score", 0))
        top1.append(best.get("label"))

    metrics = cls_metrics.compute_all(labels, top1)
    primary = "accuracy"
    return metrics, primary, metrics.get(primary)


_DISPATCH = {
    "time-series-forecasting": _eval_forecasting,
    "image-classification": _eval_image_classification,
}


def evaluate(
    model_dir: str | Path,
    dataset_path: str | Path,
    metadata: ModelCardMetadata,
) -> EvaluationResult:
    """跑一次评估。所有异常都包进 EvaluationResult.error，不抛到外层。"""
    task = metadata.pipeline_tag or ""
    start = time.monotonic()

    if task not in _DISPATCH:
        return EvaluationResult(
            task=task,
            status="error",
            duration_ms=0,
            error=f"pipeline_tag '{task}' 不支持评估",
        )

    try:
        handler = load_handler(model_dir, task)
        handler.warmup()
        metrics, primary, pval = _DISPATCH[task](handler, dataset_path, metadata)
    except Exception as e:  # noqa: BLE001 — 评估层必须兜底
        return EvaluationResult(
            task=task,
            status="error",
            duration_ms=int((time.monotonic() - start) * 1000),
            error=str(e),
            error_detail=traceback.format_exc(),
        )

    return EvaluationResult(
        task=task,
        status="ok",
        metrics=metrics,
        primary_metric=primary,
        primary_value=pval,
        duration_ms=int((time.monotonic() - start) * 1000),
    )
