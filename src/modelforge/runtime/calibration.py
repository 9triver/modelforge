"""Phase 4 校准：多方法 bias correction for time-series-forecasting。

支持三种方法：
  - linear_bias: 全局 y = a*pred + b
  - segmented: 按小时分 4 段，每段独立 (a, b)
  - stacking: GradientBoostingRegressor 拟合残差
"""
from __future__ import annotations

import base64
import hashlib
import json
import pickle
import shutil
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .evaluator import load_handler
from .metrics import forecasting as fc_metrics
from .tasks.base import TaskHandler

METHODS = ["linear_bias", "segmented", "stacking"]


@dataclass
class CalibrationResult:
    method: str = "linear_bias"
    params: dict[str, Any] = field(default_factory=dict)
    before_metrics: dict[str, Any] = field(default_factory=dict)
    after_metrics: dict[str, Any] = field(default_factory=dict)
    primary_metric: str = "mape"
    before_value: float = 0.0
    after_value: float = 0.0
    status: str = "ok"
    error: str | None = None


# ---------- shared helpers ----------

def _ols_fit(y_true: list[float], y_pred: list[float]) -> tuple[float, float]:
    n = len(y_true)
    if n < 2:
        return 1.0, 0.0
    sum_x = sum(y_pred)
    sum_y = sum(y_true)
    sum_xx = sum(x * x for x in y_pred)
    sum_xy = sum(x * y for x, y in zip(y_pred, y_true))
    denom = n * sum_xx - sum_x * sum_x
    if abs(denom) < 1e-12:
        return 1.0, (sum_y - sum_x) / n if n else 0.0
    a = (n * sum_xy - sum_x * sum_y) / denom
    b = (sum_y - a * sum_x) / n
    return a, b


def _predict_and_join(
    handler: TaskHandler,
    df: pd.DataFrame,
    target_col: str,
) -> pd.DataFrame | str:
    """跑 handler.predict 并 join 真实值。返回 joined df 或 error string。"""
    pred_df = handler.predict(df)
    if "timestamp" not in pred_df.columns or "prediction" not in pred_df.columns:
        return f"handler.predict 返回列不对：{list(pred_df.columns)}"
    pred_df = pred_df.copy()
    pred_df["timestamp"] = pd.to_datetime(pred_df["timestamp"])
    joined = df[["timestamp", target_col]].merge(
        pred_df[["timestamp", "prediction"]], on="timestamp", how="inner"
    )
    if len(joined) < 4:
        return f"有效数据点太少（{len(joined)}），至少需要 4 个"
    joined["hour"] = joined["timestamp"].dt.hour
    joined["dayofweek"] = joined["timestamp"].dt.dayofweek
    joined["month"] = joined["timestamp"].dt.month
    return joined


def _split(joined: pd.DataFrame, holdout_ratio: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    n = len(joined)
    split = int(n * (1 - holdout_ratio))
    return joined.iloc[:split].copy(), joined.iloc[split:].copy()


# ---------- method 1: linear_bias ----------

def calibrate_linear(
    handler: TaskHandler,
    df: pd.DataFrame,
    target_col: str,
    holdout_ratio: float = 0.3,
) -> CalibrationResult:
    joined = _predict_and_join(handler, df, target_col)
    if isinstance(joined, str):
        return CalibrationResult(method="linear_bias", status="error", error=joined)

    fit, hold = _split(joined, holdout_ratio)
    a, b = _ols_fit(fit[target_col].tolist(), fit["prediction"].tolist())

    y_true = hold[target_col].tolist()
    y_pred = hold["prediction"].tolist()
    y_cal = [a * p + b for p in y_pred]

    before = fc_metrics.compute_all(y_true, y_pred)
    after = fc_metrics.compute_all(y_true, y_cal)
    return CalibrationResult(
        method="linear_bias",
        params={"a": round(a, 6), "b": round(b, 6)},
        before_metrics=before, after_metrics=after,
        primary_metric="mape",
        before_value=before.get("mape") or 0.0,
        after_value=after.get("mape") or 0.0,
    )


# ---------- method 2: segmented ----------

N_SEGMENTS = 4  # 0-5, 6-11, 12-17, 18-23


def _segment_id(hour: int) -> int:
    return min(hour // (24 // N_SEGMENTS), N_SEGMENTS - 1)


def calibrate_segmented(
    handler: TaskHandler,
    df: pd.DataFrame,
    target_col: str,
    holdout_ratio: float = 0.3,
) -> CalibrationResult:
    joined = _predict_and_join(handler, df, target_col)
    if isinstance(joined, str):
        return CalibrationResult(method="segmented", status="error", error=joined)

    joined["seg"] = joined["hour"].apply(_segment_id)
    fit, hold = _split(joined, holdout_ratio)

    segments: dict[str, dict[str, float]] = {}
    for seg in range(N_SEGMENTS):
        seg_fit = fit[fit["seg"] == seg]
        if len(seg_fit) >= 2:
            a, b = _ols_fit(seg_fit[target_col].tolist(), seg_fit["prediction"].tolist())
        else:
            a, b = 1.0, 0.0
        segments[str(seg)] = {"a": round(a, 6), "b": round(b, 6)}

    y_true = hold[target_col].tolist()
    y_pred = hold["prediction"].tolist()
    y_cal = []
    for _, row in hold.iterrows():
        seg = segments.get(str(row["seg"]), {"a": 1.0, "b": 0.0})
        y_cal.append(seg["a"] * row["prediction"] + seg["b"])

    before = fc_metrics.compute_all(y_true, y_pred)
    after = fc_metrics.compute_all(y_true, y_cal)
    return CalibrationResult(
        method="segmented",
        params={"segments": segments, "n_segments": N_SEGMENTS},
        before_metrics=before, after_metrics=after,
        primary_metric="mape",
        before_value=before.get("mape") or 0.0,
        after_value=after.get("mape") or 0.0,
    )


# ---------- method 3: stacking ----------

def calibrate_stacking(
    handler: TaskHandler,
    df: pd.DataFrame,
    target_col: str,
    holdout_ratio: float = 0.3,
) -> CalibrationResult:
    joined = _predict_and_join(handler, df, target_col)
    if isinstance(joined, str):
        return CalibrationResult(method="stacking", status="error", error=joined)

    try:
        from sklearn.ensemble import GradientBoostingRegressor
    except ImportError:
        return CalibrationResult(
            method="stacking", status="error",
            error="stacking 需要 scikit-learn（pip install scikit-learn）",
        )

    fit, hold = _split(joined, holdout_ratio)
    feat_cols = ["prediction", "hour", "dayofweek", "month"]

    residual = (fit[target_col] - fit["prediction"]).values
    X_fit = fit[feat_cols].values

    gbr = GradientBoostingRegressor(n_estimators=50, max_depth=3, random_state=42)
    gbr.fit(X_fit, residual)

    X_hold = hold[feat_cols].values
    residual_hat = gbr.predict(X_hold)

    y_true = hold[target_col].tolist()
    y_pred = hold["prediction"].tolist()
    y_cal = [p + r for p, r in zip(y_pred, residual_hat)]

    model_bytes = pickle.dumps(gbr)
    model_b64 = base64.b64encode(model_bytes).decode("ascii")

    before = fc_metrics.compute_all(y_true, y_pred)
    after = fc_metrics.compute_all(y_true, y_cal)
    return CalibrationResult(
        method="stacking",
        params={"model_b64": model_b64, "feat_cols": feat_cols},
        before_metrics=before, after_metrics=after,
        primary_metric="mape",
        before_value=before.get("mape") or 0.0,
        after_value=after.get("mape") or 0.0,
    )


# ---------- dispatcher ----------

_CALIBRATORS = {
    "linear_bias": calibrate_linear,
    "segmented": calibrate_segmented,
    "stacking": calibrate_stacking,
}


def calibrate_by_method(
    method: str,
    handler: TaskHandler,
    df: pd.DataFrame,
    target_col: str,
    holdout_ratio: float = 0.3,
) -> CalibrationResult:
    fn = _CALIBRATORS.get(method)
    if fn is None:
        return CalibrationResult(
            method=method, status="error",
            error=f"未知校准方法 '{method}'，可选：{sorted(_CALIBRATORS)}",
        )
    return fn(handler, df, target_col, holdout_ratio)


# keep old name as alias
calibrate_forecasting = calibrate_linear


# ---------- handler templates (per method) ----------

HANDLER_TEMPLATE_LINEAR = textwrap.dedent("""\
    import json
    from pathlib import Path
    import pandas as pd
    from modelforge.runtime.evaluator import load_handler
    from modelforge.runtime.tasks import ForecastingHandler

    class Handler(ForecastingHandler):
        def __init__(self, model_dir: str):
            super().__init__(model_dir)
            params = json.loads((Path(model_dir) / "calibration.json").read_text())
            self.a = params["a"]
            self.b = params["b"]
            self.base = load_handler(str(Path(model_dir) / "base_model"), "time-series-forecasting")
        def predict(self, df: pd.DataFrame) -> pd.DataFrame:
            pred = self.base.predict(df)
            pred["prediction"] = self.a * pred["prediction"] + self.b
            return pred
""")

HANDLER_TEMPLATE_SEGMENTED = textwrap.dedent("""\
    import json
    from pathlib import Path
    import pandas as pd
    from modelforge.runtime.evaluator import load_handler
    from modelforge.runtime.tasks import ForecastingHandler

    class Handler(ForecastingHandler):
        def __init__(self, model_dir: str):
            super().__init__(model_dir)
            params = json.loads((Path(model_dir) / "calibration.json").read_text())
            self.segments = params["segments"]
            self.n_segments = params["n_segments"]
            self.base = load_handler(str(Path(model_dir) / "base_model"), "time-series-forecasting")
        def predict(self, df: pd.DataFrame) -> pd.DataFrame:
            pred = self.base.predict(df)
            ts = pd.to_datetime(pred["timestamp"])
            seg_ids = (ts.dt.hour // (24 // self.n_segments)).clip(upper=self.n_segments - 1)
            calibrated = []
            for p, seg in zip(pred["prediction"], seg_ids):
                s = self.segments.get(str(seg), {"a": 1.0, "b": 0.0})
                calibrated.append(s["a"] * p + s["b"])
            pred["prediction"] = calibrated
            return pred
""")

HANDLER_TEMPLATE_STACKING = textwrap.dedent("""\
    import base64, json, pickle
    from pathlib import Path
    import pandas as pd
    from modelforge.runtime.evaluator import load_handler
    from modelforge.runtime.tasks import ForecastingHandler

    class Handler(ForecastingHandler):
        def __init__(self, model_dir: str):
            super().__init__(model_dir)
            params = json.loads((Path(model_dir) / "calibration.json").read_text())
            self.gbr = pickle.loads(base64.b64decode(params["model_b64"]))
            self.feat_cols = params["feat_cols"]
            self.base = load_handler(str(Path(model_dir) / "base_model"), "time-series-forecasting")
        def predict(self, df: pd.DataFrame) -> pd.DataFrame:
            pred = self.base.predict(df)
            ts = pd.to_datetime(pred["timestamp"])
            feat = pd.DataFrame({
                "prediction": pred["prediction"],
                "hour": ts.dt.hour,
                "dayofweek": ts.dt.dayofweek,
                "month": ts.dt.month,
            })
            residual = self.gbr.predict(feat[self.feat_cols].values)
            pred["prediction"] = pred["prediction"] + residual
            return pred
""")

_HANDLER_TEMPLATES = {
    "linear_bias": HANDLER_TEMPLATE_LINEAR,
    "segmented": HANDLER_TEMPLATE_SEGMENTED,
    "stacking": HANDLER_TEMPLATE_STACKING,
}


# ---------- repo generation ----------

def generate_calibrated_repo(
    source_dir: Path,
    result: CalibrationResult,
    source_repo: str,
    source_revision: str,
    target_repo: str,
    data_hash: str,
    dest: Path,
) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, dest / "base_model")

    (dest / "calibration.json").write_text(json.dumps(result.params, indent=2))

    template = _HANDLER_TEMPLATES.get(result.method, HANDLER_TEMPLATE_LINEAR)
    (dest / "handler.py").write_text(template)

    ns, name = target_repo.split("/", 1)
    src_meta = {}
    src_readme = source_dir / "README.md"
    if src_readme.is_file():
        from ..schema import parse_frontmatter
        try:
            src_meta, _ = parse_frontmatter(src_readme.read_text(encoding="utf-8"))
        except Exception:
            pass

    method_tag = result.method.replace("_", "-")
    readme = textwrap.dedent(f"""\
        ---
        license: {src_meta.get('license', 'unknown')}
        library_name: {src_meta.get('library_name', 'unknown')}
        pipeline_tag: time-series-forecasting
        base_model: {source_repo}
        tags:
          - time-series-forecasting
          - calibrated
          - {method_tag}
        calibration:
          method: {result.method}
          source_repo: {source_repo}
          source_revision: {source_revision}
          target_data_hash: "sha256:{data_hash}"
          before_mape: {result.before_value}
          after_mape: {result.after_value}
        ---

        # {ns}/{name}

        Calibrated from [{source_repo}](/{source_repo}) via **{result.method}**.

        | Metric | Before | After |
        |--------|--------|-------|
        | MAPE | {result.before_value:.4f} | {result.after_value:.4f} |
        | RMSE | {result.before_metrics.get('rmse', 'N/A')} | {result.after_metrics.get('rmse', 'N/A')} |
        | MAE | {result.before_metrics.get('mae', 'N/A')} | {result.after_metrics.get('mae', 'N/A')} |
    """)
    (dest / "README.md").write_text(readme)

    gitattr = source_dir / ".gitattributes"
    if gitattr.is_file():
        shutil.copy2(gitattr, dest / ".gitattributes")


def compute_data_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]
