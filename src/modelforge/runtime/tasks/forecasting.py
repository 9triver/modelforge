"""time-series-forecasting task。

I/O 契约：
  predict(df) -> pred_df
    df: pandas.DataFrame，至少含 'timestamp' 列 + model_card 声明的 features
    pred_df: pandas.DataFrame，含 'timestamp' + 'prediction' 列

model_card.yaml 需声明：
  pipeline_tag: time-series-forecasting
  forecasting:
    input_freq: 15min | 1h | 1d
    horizon: int        # 预测步数
    lookback: int       # 所需历史步数
    features:
      required: [...]
      optional: [...]
    target: str
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import TaskHandler, register_task

if TYPE_CHECKING:
    import pandas as pd


@register_task
class ForecastingHandler(TaskHandler):
    task = "time-series-forecasting"

    def predict(self, df: "pd.DataFrame") -> "pd.DataFrame":
        raise NotImplementedError
