"""tabular-regression task。

I/O 契约：
  predict(df) -> list[float]
    df: pandas.DataFrame，含特征列（不含 target）
    返回：每行的预测值列表

model_card.yaml 需声明：
  pipeline_tag: tabular-regression
  tabular:
    target: str           # 目标列名
    features:
      required: [...]
      optional: [...]
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import TaskHandler, register_task

if TYPE_CHECKING:
    import pandas as pd


@register_task
class TabularRegressionHandler(TaskHandler):
    task = "tabular-regression"

    def predict(self, df: "pd.DataFrame") -> list[float]:
        raise NotImplementedError
