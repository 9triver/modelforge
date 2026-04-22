"""Phase 4 校准：bias correction for time-series-forecasting。

流程：
  1. 用全量校准数据跑 handler.predict → raw predictions
  2. 按时间顺序 split：前 70% fit，后 30% holdout evaluate
  3. OLS 拟合 a, b 使得 a*pred + b ≈ y_true
  4. 在 holdout 上算 before/after metrics
  5. 生成校准后仓库内容（base_model/ + handler.py + calibration.json + README.md）
"""
from __future__ import annotations

import hashlib
import json
import shutil
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .evaluator import load_handler
from .metrics import forecasting as fc_metrics
from .tasks.base import TaskHandler


@dataclass
class CalibrationResult:
    method: str = "linear_bias"
    params: dict[str, float] = field(default_factory=dict)
    before_metrics: dict[str, Any] = field(default_factory=dict)
    after_metrics: dict[str, Any] = field(default_factory=dict)
    primary_metric: str = "mape"
    before_value: float = 0.0
    after_value: float = 0.0
    status: str = "ok"
    error: str | None = None


def _ols_fit(y_true: list[float], y_pred: list[float]) -> tuple[float, float]:
    """最小二乘拟合 y_true = a * y_pred + b，返回 (a, b)。"""
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


def calibrate_forecasting(
    handler: TaskHandler,
    calibration_df: pd.DataFrame,
    target_col: str,
    holdout_ratio: float = 0.3,
) -> CalibrationResult:
    """对 forecasting handler 做线性 bias correction。"""
    pred_df = handler.predict(calibration_df)
    if "timestamp" not in pred_df.columns or "prediction" not in pred_df.columns:
        return CalibrationResult(
            status="error",
            error=f"handler.predict 返回列不对：{list(pred_df.columns)}",
        )

    pred_df = pred_df.copy()
    pred_df["timestamp"] = pd.to_datetime(pred_df["timestamp"])
    joined = calibration_df[["timestamp", target_col]].merge(
        pred_df[["timestamp", "prediction"]], on="timestamp", how="inner"
    )
    if len(joined) < 4:
        return CalibrationResult(
            status="error", error=f"有效数据点太少（{len(joined)}），至少需要 4 个"
        )

    n = len(joined)
    split = int(n * (1 - holdout_ratio))
    fit_part = joined.iloc[:split]
    hold_part = joined.iloc[split:]

    y_fit_true = fit_part[target_col].tolist()
    y_fit_pred = fit_part["prediction"].tolist()
    a, b = _ols_fit(y_fit_true, y_fit_pred)

    y_hold_true = hold_part[target_col].tolist()
    y_hold_pred = hold_part["prediction"].tolist()
    y_hold_cal = [a * p + b for p in y_hold_pred]

    before = fc_metrics.compute_all(y_hold_true, y_hold_pred)
    after = fc_metrics.compute_all(y_hold_true, y_hold_cal)

    return CalibrationResult(
        params={"a": round(a, 6), "b": round(b, 6)},
        before_metrics=before,
        after_metrics=after,
        primary_metric="mape",
        before_value=before.get("mape") or 0.0,
        after_value=after.get("mape") or 0.0,
    )


CALIBRATED_HANDLER_TEMPLATE = textwrap.dedent("""\
    import json
    from pathlib import Path

    import pandas as pd

    from modelforge.runtime.evaluator import load_handler
    from modelforge.runtime.tasks import ForecastingHandler


    class Handler(ForecastingHandler):
        def __init__(self, model_dir: str):
            super().__init__(model_dir)
            base_dir = Path(model_dir) / "base_model"
            params = json.loads((Path(model_dir) / "calibration.json").read_text())
            self.a = params["a"]
            self.b = params["b"]
            self.base = load_handler(str(base_dir), "time-series-forecasting")

        def predict(self, df: pd.DataFrame) -> pd.DataFrame:
            pred = self.base.predict(df)
            pred["prediction"] = self.a * pred["prediction"] + self.b
            return pred
""")


def generate_calibrated_repo(
    source_dir: Path,
    result: CalibrationResult,
    source_repo: str,
    source_revision: str,
    target_repo: str,
    data_hash: str,
    dest: Path,
) -> None:
    """在 dest 目录组装校准后仓库的全部内容。"""
    dest.mkdir(parents=True, exist_ok=True)

    base_dir = dest / "base_model"
    shutil.copytree(source_dir, base_dir)

    (dest / "calibration.json").write_text(
        json.dumps(result.params, indent=2)
    )

    (dest / "handler.py").write_text(CALIBRATED_HANDLER_TEMPLATE)

    ns, name = target_repo.split("/", 1)
    src_meta = {}
    src_readme = source_dir / "README.md"
    if src_readme.is_file():
        from ..schema import parse_frontmatter
        try:
            src_meta, _ = parse_frontmatter(src_readme.read_text(encoding="utf-8"))
        except Exception:
            pass

    readme = textwrap.dedent(f"""\
        ---
        license: {src_meta.get('license', 'unknown')}
        library_name: {src_meta.get('library_name', 'unknown')}
        pipeline_tag: time-series-forecasting
        base_model: {source_repo}
        tags:
          - time-series-forecasting
          - calibrated
          - linear-bias
        calibration:
          method: linear_bias
          source_repo: {source_repo}
          source_revision: {source_revision}
          params:
            a: {result.params['a']}
            b: {result.params['b']}
          target_data_hash: "sha256:{data_hash}"
          before_mape: {result.before_value}
          after_mape: {result.after_value}
        ---

        # {ns}/{name}

        Calibrated from [{source_repo}](/{source_repo}) via linear bias correction.

        | Metric | Before | After |
        |--------|--------|-------|
        | MAPE | {result.before_value:.4f} | {result.after_value:.4f} |
        | RMSE | {result.before_metrics.get('rmse', 'N/A')} | {result.after_metrics.get('rmse', 'N/A')} |
        | MAE | {result.before_metrics.get('mae', 'N/A')} | {result.after_metrics.get('mae', 'N/A')} |

        Calibration parameters: `y = {result.params['a']} * pred + {result.params['b']}`
    """)
    (dest / "README.md").write_text(readme)

    gitattr = source_dir / ".gitattributes"
    if gitattr.is_file():
        shutil.copy2(gitattr, dest / ".gitattributes")


def compute_data_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]
